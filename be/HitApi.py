import os
import requests
import json
import logging

from utils.GetBearer import get_bearer_token, invalidate_token
from utils.config import CHAT_API, SPACE_NAME, FLOW_ID, AUTH_STATE_PATH
from utils.tokenStore import get_token
from GetState import refresh_session

logging.basicConfig(level=logging.INFO)


# 🔧 Generic request (used by BOTH agents)
def _make_request(token, query_type, query, space_name, flow_id):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    payload = {
        "query": json.dumps({
            "type": query_type,
            "content": query
        }),
        "space_name": space_name,
        "flowId": flow_id
    }

    return requests.post(CHAT_API, headers=headers, json=payload, timeout=15)


# 🔥 PRIMARY TOKEN (token1 → else automation)
def _get_primary_token():
    frontend_token = get_token("primary")

    if frontend_token:
        logging.info("✅ Using frontend primary token")
        return frontend_token

    logging.info("⚙️ No frontend token → using automation")

    if not os.path.exists(AUTH_STATE_PATH):
        logging.warning("⚠️ auth.json not found → login flow")
        refresh_session()

        if not os.path.exists(AUTH_STATE_PATH):
            raise Exception("❌ Failed to generate auth.json")

    try:
        return get_bearer_token()
    except Exception:
        logging.warning("⚠️ Token fetch failed → regenerating session")
        refresh_session()
        return get_bearer_token(force_refresh=True)


# 🔥 FALLBACK TOKEN (token2 ONLY)
def _get_fallback_token():
    token = get_token("fallback")

    if token:
        logging.info("✅ Using fallback token (Agent 2)")
        return token

    return None


# 🚀 MAIN FUNCTION
def call_chat_api(query_type: str, query: str):

    # 🔹 STEP 1: PRIMARY AGENT
    try:
        token = _get_primary_token()

        response = _make_request(
            token,
            query_type,
            query,
            SPACE_NAME,
            FLOW_ID
        )

        if response.ok and response.status_code != 401:
            logging.info("✅ Primary agent success")
            return response

        logging.warning("⚠️ Primary agent failed")

        # Retry ONLY if automation token
        if response.status_code == 401 and not get_token("primary"):
            invalidate_token()
            token = get_bearer_token(force_refresh=True)

            response = _make_request(
                token,
                query_type,
                query,
                SPACE_NAME,
                FLOW_ID
            )

            if response.ok:
                logging.info("✅ Primary retry success")
                return response

    except Exception as e:
        logging.warning(f"⚠️ Primary agent error: {e}")

    # 🔹 STEP 2: FALLBACK AGENT
    fallback_token = _get_fallback_token()

    if fallback_token:
        try:
            logging.info("🔁 Switching to Agent 2")

            response = _make_request(
                fallback_token,
                query_type,
                query,
                "BackupAgent_d8544a5f",     # 🔥 Agent 2 space
                "69d3bae8ea80f1bdfe45e207"  # 🔥 Agent 2 flow
            )

            if response.ok:
                logging.info("✅ Fallback agent success")
                return response

            logging.error(f"❌ Agent 2 failed: {response.status_code}")

        except Exception as e:
            logging.error(f"❌ Agent 2 error: {e}")

    # 🔹 FINAL FAILURE
    raise Exception("❌ Both agents failed or fallback token not provided")