import os
import re
import uuid
import logging
import html
import asyncio
import httpx
from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

load_dotenv()

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 환경 변수에서 API 키 로드 (Railway Shared Variables 활용)
PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY")
if not PERPLEXITY_API_KEY:
    logger.error("PERPLEXITY_API_KEY 환경 변수가 설정되지 않았습니다.")

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
MODEL_NAME = os.environ.get("MODEL_NAME", "sonar")

# FastAPI 설정
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SECRET_KEY", "your-secret-key"))

# 대화 저장소
conversation_store = {}

# 유틸리티 함수
def remove_citation_markers(text: str) -> str:
    return re.sub(r'【\d+:\d+†source】', '', text)

def convert_newlines_to_br(text: str) -> str:
    return html.escape(text).replace('\n', '<br>')

async def get_perplexity_reply(messages) -> str:
    """
    Perplexity API를 호출하여 대화 기록(messages)에 대한 AI 응답을 생성합니다.
    불필요한 값(None)은 payload에서 제외하고, 마지막 메시지가 "답변 생성 중..."이면 제거 후 요청합니다.
    """
    if messages and messages[-1]["role"] == "assistant" and messages[-1]["content"] == "답변 생성 중...":
        messages_for_api = messages[:-1]  # 마지막 placeholder 제거
    else:
        messages_for_api = messages

    payload = {
        "model": MODEL_NAME,
        "messages": messages_for_api,
        "max_tokens": 200,
        "temperature": 0.2,
        "top_p": 0.9,
        "top_k": 0,
        "stream": False,
        "presence_penalty": 0,
        "frequency_penalty": 1,
    }
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(PERPLEXITY_API_URL, json=payload, headers=headers)
            if response.status_code != 200:
                logger.error(f"Perplexity API 오류 {response.status_code}: {response.text}")
                return "응답 생성에 실패했습니다. 다시 시도해 주세요."
            data = response.json()
            if "choices" not in data:
                logger.error(f"응답 데이터 형식 오류: {data}")
                return "응답 생성에 실패했습니다. 다시 시도해 주세요."
            reply = data["choices"][0]["message"]["content"]
            return remove_citation_markers(reply)
    except Exception as e:
        logger.error(f"Perplexity API 호출 오류: {e}")
        return "응답 생성에 실패했습니다. 다시 시도해 주세요."

@app.get("/", response_class=HTMLResponse)
async def get_chat(request: Request):
    """ 대화 인터페이스 렌더링 """
    session_id = request.session.get("session_id", str(uuid.uuid4()))
    request.session["session_id"] = session_id

    if session_id not in conversation_store:
        conversation_store[session_id] = {
            "messages": [{"role": "assistant", "content": "모든 답은 당신 안에 있습니다. 🙏🏻 무엇이 궁금하신가요?"}]
        }

    return HTMLResponse(content=render_chat_interface(conversation_store[session_id]))

@app.post("/message", response_class=HTMLResponse)
async def message_init(request: Request, message: str = Form(...), phase: str = Query(None)):
    """ 사용자 메시지를 저장하고, AI 응답을 위한 자리 표시 메시지를 추가 """
    session_id = request.session.get("session_id", str(uuid.uuid4()))
    request.session["session_id"] = session_id

    if session_id not in conversation_store:
        conversation_store[session_id] = {"messages": []}
    conv = conversation_store[session_id]

    # 사용자 메시지 저장
    conv["messages"].append({"role": "user", "content": message})
    placeholder_id = str(uuid.uuid4())

    conv["messages"].append({"role": "assistant", "content": "답변 생성 중..."})

    user_msg_html = f"""
    <div class="chat-message user-message flex justify-end mb-4">
        <div class="bubble bg-white border-gray-400 p-3 rounded-lg shadow-sm mr-3">
            {convert_newlines_to_br(message)}
        </div>
        <div class="avatar text-3xl">🧑🏻‍💻</div>
    </div>
    """
    placeholder_html = f"""
    <div class="chat-message assistant-message flex mb-4" id="assistant-block-{placeholder_id}">
        <div class="avatar text-3xl mr-3">🪷</div>
        <div class="bubble bg-slate-100 border-slate-400 p-3 rounded-lg shadow-sm"
             id="ai-msg-{placeholder_id}"
             hx-get="/message?phase=answer&placeholder_id={placeholder_id}"
             hx-trigger="load"
             hx-target="#assistant-block-{placeholder_id}"
             hx-swap="outerHTML">
            답변 생성 중...
        </div>
    </div>
    """
    return HTMLResponse(content=user_msg_html + placeholder_html)

@app.get("/message", response_class=HTMLResponse)
async def message_answer(request: Request, placeholder_id: str = Query(None), phase: str = Query(None)):
    """ Perplexity API에서 AI 응답을 받아와 UI에 반영 """
    if phase != "answer":
        return HTMLResponse("Invalid phase", status_code=400)

    session_id = request.session.get("session_id")
    if not session_id or session_id not in conversation_store:
        return HTMLResponse("Session not found", status_code=400)

    conv = conversation_store[session_id]
    ai_reply = await get_perplexity_reply(conv["messages"])

    # 마지막 AI 메시지 업데이트
    if conv["messages"] and conv["messages"][-1]["role"] == "assistant":
        conv["messages"][-1]["content"] = ai_reply
    else:
        conv["messages"].append({"role": "assistant", "content": ai_reply})

    final_html = f"""
    <div class="chat-message assistant-message flex mb-4" id="assistant-block-{placeholder_id}">
        <div class
