import os
import requests
import json
import logging

from utils.GetBearer import get_bearer_token, invalidate_token
from utils.config import CHAT_API, SPACE_NAME, FLOW_ID, AUTH_STATE_PATH
from utils.tokenStore import get_token
from GetState import refresh_session

logging.basicConfig(level=logging.INFO)

AGENT2_SPACE = "BackupAgent_d8544a5f"
AGENT2_FLOW = "69d3bae8ea80f1bdfe45e207"

TIMEOUT = 30


# ✅ ---------------- TOKEN VALIDATION ----------------
def _is_valid_token(token: str) -> bool:
    if not token:
        return False

    token = token.strip()

    if token.lower() in ["null", "undefined", ""]:
        return False

    # Remove Bearer prefix if present
    if token.startswith("Bearer "):
        token = token[7:]

    # Basic JWT structure check
    parts = token.split(".")
    if len(parts) != 3:
        return False

    return True


# ✅ ---------------- AUTH HEADER BUILDER ----------------
def _build_auth_header(token: str) -> str:
    token = token.strip()

    if token.startswith("Bearer "):
        return token  # already correct

    return f"Bearer {token}"


# 🔧 ---------------- GENERIC REQUEST ----------------
def _make_request(token, query_type, query, space_name, flow_id):
    headers = {
        "Content-Type": "application/json",
        "Authorization": _build_auth_header(token)
    }

    payload = {
        "query": json.dumps({
            "type": query_type,
            "content": query
        }),
        "space_name": space_name,
        "flowId": flow_id
    }

    logging.info(f"📤 Payload: {json.dumps(payload)[:200]}")
    logging.info(f"🔐 Token (first 30 chars): {token[:30]}...")

    try:
        response = requests.post(
            CHAT_API,
            headers=headers,
            json=payload,
            timeout=TIMEOUT
        )

        logging.info(f"📥 {response.status_code} from space={space_name}")

        if not response.ok:
            logging.warning(f"⚠️ Response body: {response.text[:300]}")

        return response

    except requests.Timeout:
        logging.error("⏳ Request timed out")
        raise


# 🔑 ---------------- TOKEN RESOLUTION ----------------
def _resolve_token(agent_type: str) -> str | None:
    frontend_token = get_token(agent_type)

    logging.info(f"[DEBUG] Raw frontend {agent_type} token: {repr(frontend_token)}")

    if _is_valid_token(frontend_token):
        logging.info(f"✅ Using frontend {agent_type} token")
        return frontend_token

    logging.info(f"⚠️ Invalid/missing frontend {agent_type} token")

    # Only primary falls back to automation
    if agent_type == "primary":
        logging.info("⚙️ Falling back to automation bearer")

        if not os.path.exists(AUTH_STATE_PATH):
            logging.warning("⚠️ auth.json missing → starting login flow")
            refresh_session()

            if not os.path.exists(AUTH_STATE_PATH):
                raise Exception("❌ Failed to generate auth.json")

        return get_bearer_token()

    return None


# 🚀 ---------------- MAIN FUNCTION ----------------
def call_chat_api(query_type: str, query: str):

    # 🔹 PRIMARY AGENT
    try:
        token = _resolve_token("primary")

        response = _make_request(token, query_type, query, SPACE_NAME, FLOW_ID)

        if response.ok:
            logging.info("✅ Primary agent success")
            return response

        # Retry only if using automation token
        if response.status_code == 401 and not _is_valid_token(get_token("primary")):
            logging.info("🔄 401 on automation token → refreshing once")

            invalidate_token()
            token = get_bearer_token(force_refresh=True)

            response = _make_request(token, query_type, query, SPACE_NAME, FLOW_ID)

            if response.ok:
                logging.info("✅ Primary refresh success")
                return response

        logging.warning(f"⚠️ Primary failed: {response.status_code}")

    except Exception as e:
        logging.warning(f"⚠️ Primary error: {type(e).__name__}: {e}")

    # 🔹 FALLBACK AGENT
    try:
        fallback_token = _resolve_token("fallback")

        if not _is_valid_token(fallback_token):
            raise Exception("No valid fallback token provided")

        logging.info("🔁 Switching to Agent 2")

        # Retry once for timeout
        for attempt in range(2):
            try:
                response = _make_request(
                    fallback_token,
                    query_type,
                    query,
                    AGENT2_SPACE,
                    AGENT2_FLOW
                )

                if response.ok:
                    logging.info("✅ Fallback agent success")
                    return response

                logging.error(f"❌ Agent 2 failed: {response.status_code}")
                break

            except requests.Timeout:
                logging.warning(f"⏳ Retry {attempt+1} for Agent 2...")

        raise Exception("Fallback agent timeout/failure")

    except Exception as e:
        logging.error(f"❌ Agent 2 error: {type(e).__name__}: {e}")

    raise Exception("❌ Both agents failed")