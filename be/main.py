from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging
import time
import json
from utils.tokenStore import set_token


from hitApi import call_chat_api

app = FastAPI(title="Blueverse API Wrapper")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


logging.basicConfig(level=logging.INFO)

class TokenRequest(BaseModel):
    token: str
    
    
# 📦 Request Schema
class ChatRequest(BaseModel):
    type: str
    query: str
    current_code: Optional[str] = None


# 🔧 Helper: Clean LLM Output
def clean_llm_output(raw: str) -> str:
    if not raw:
        return ""

    raw = raw.strip()

    if raw.startswith("```"):
        raw = raw.replace("```json", "").replace("```", "").strip()

    return raw

@app.post("/token1")
def set_primary_token(req: TokenRequest):
    set_token("primary", req.token)
    return {"status": "primary token set"}

@app.post("/token2")
def set_fallback_token(req: TokenRequest):
    set_token("fallback", req.token)
    return {"status": "fallback token set"}

@app.get("/")
def health():
    return {"status": "running"}


@app.post("/chat")
def chat(req: ChatRequest):
    start_time = time.time()

    try:
        final_query = req.query

        if req.current_code:
            final_query += f"\n\nExisting Code:\n{req.current_code}"

        final_query += """
        
STRICTLY return ONLY valid JSON.
DO NOT include markdown, backticks, or extra text.

Format:
{
  "code": "...",
  "explanation": "..."
}
"""

        response = call_chat_api(req.type, final_query)

        if not response.ok:
            raise HTTPException(
                status_code=response.status_code,
                detail=response.text
            )

        # 🧠 Parse outer API response
        try:
            data = response.json()
        except Exception:
            data = {}

        model = data.get("responseSource", "unknown")
        backend_time = data.get("execution_time", None)

        raw_output = data.get("response", "")

        code = raw_output
        explanation = ""  # ALWAYS present

        cleaned_output = clean_llm_output(raw_output)

        try:
            parsed = json.loads(cleaned_output)

            if isinstance(parsed, dict):
                code = parsed.get("code", raw_output)
                explanation = parsed.get("explanation", "")
        except Exception:
            logging.warning("⚠️ Failed to parse LLM JSON, using fallback")

        response_time = round(time.time() - start_time, 3)

        return {
            "status": "success",
            "code": code,
            "explanation": explanation,
            "model": model,
            "response_time": response_time,
            "backend_time": backend_time
        }

    except Exception as e:
        logging.error(f"❌ Internal Error: {str(e)}")

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )