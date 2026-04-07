import os
import requests
import json
import logging

from utils.GetBearer import get_bearer_token, invalidate_token
from utils.config import CHAT_API, SPACE_NAME, FLOW_ID, AUTH_STATE_PATH
from utils.tokenStore import get_token
from GetState import refresh_session

logging.basicConfig(level=logging.INFO)


# 🔧 Common request function
def _make_request(token, query_type, query):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    payload = {
        "query": json.dumps({
            "type": query_type,
            "content": query
        }),
        "space_name": SPACE_NAME,
        "flowId": FLOW_ID
    }

    return requests.post(CHAT_API, headers=headers, json=payload, timeout=15)


# 🔥 PRIMARY TOKEN RESOLUTION
def _get_primary_token():
    # ✅ 1. Check frontend token
    frontend_token = get_token("primary")
    if frontend_token:
        logging.info("✅ Using frontend primary token")
        return frontend_token

    # ✅ 2. Fallback to automation
    logging.info("⚙️ No frontend token → using automation")

    if not os.path.exists(AUTH_STATE_PATH):
        logging.warning("⚠️ auth.json not found. Starting login flow...")
        refresh_session()

        if not os.path.exists(AUTH_STATE_PATH):
            raise Exception("❌ Failed to generate auth.json after login")

    try:
        return get_bearer_token()
    except Exception as e:
        logging.warning(f"⚠️ Token fetch failed: {e}")

        logging.info("🔄 Regenerating session...")
        refresh_session()

        return get_bearer_token(force_refresh=True)


# 🔥 FALLBACK TOKEN (STRICT: NO AUTOMATION)
def _get_fallback_token():
    fallback_token = get_token("fallback")

    if fallback_token:
        logging.info("✅ Using fallback token (frontend)")
        return fallback_token

    raise Exception("❌ No fallback token available")


# 🚀 MAIN API FUNCTION
def call_chat_api(query_type: str, query: str):

    # 🔹 STEP 1: PRIMARY AGENT
    try:
        token = _get_primary_token()

        response = _make_request(token, query_type, query)

        # ✅ Success case
        if response.ok and response.status_code != 401:
            logging.info("✅ Primary agent success")
            return response

        logging.warning("⚠️ Primary agent failed (401/Bad response)")

        # Handle token expiry ONLY if automation token
        if response.status_code == 401 and not get_token("primary"):
            logging.info("🔄 Attempting token refresh (automation only)")

            invalidate_token()

            try:
                token = get_bearer_token(force_refresh=True)
                response = _make_request(token, query_type, query)

                if response.ok:
                    logging.info("✅ Primary retry success")
                    return response

            except Exception:
                logging.warning("⚠️ Token refresh failed → will fallback")

    except Exception as e:
        logging.warning(f"⚠️ Primary agent error: {e}")

    # 🔹 STEP 2: FALLBACK AGENT
    try:
        fallback_token = _get_fallback_token()

        response = _make_request(fallback_token, query_type, query)

        if response.ok:
            logging.info("✅ Fallback agent success")
            return response

        logging.error(f"❌ Fallback failed: {response.status_code}")

    except Exception as e:
        logging.error(f"❌ Fallback agent error: {e}")

    # 🔹 FINAL FAILURE
    raise Exception("❌ Both primary and fallback agents failed")