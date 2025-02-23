import os
import re
import uuid
import logging
import asyncio
import openai
import uvicorn

from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
import html

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ASSISTANT_ID = os.environ.get("ASSISTANT_ID", "default_assistant_id")
VECTOR_STORE_ID = os.environ.get("VECTOR_STORE_ID", "")

if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
openai.api_key = OPENAI_API_KEY

# 아이콘 및 페르소나 설정
ai_icon = "🪷"
user_icon = "🧑🏻‍💻"
ai_persona = "스님 AI 챗봇"

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="your-secret-key")

conversation_store = {}

def remove_citation_markers(text: str) -> str:
    return re.sub(r'【\d+:\d+†source】', '', text)

def create_thread():
    try:
        thread = openai.beta.threads.create()
        return thread.id
    except Exception as e:
        logger.error(f"Thread creation failed: {e}")
        return None

def init_conversation(session_id: str):
    thread_id = create_thread()
    initial_message = (
        "모든 답은 당신 안에 있습니다. "
        "저는 그 여정을 함께하는 스님 AI입니다. 무엇이 궁금하신가요? 🙏🏻"
    )
    conversation_store[session_id] = {
        "thread_id": thread_id,
        "messages": [{"role": "assistant", "content": initial_message}]
    }

def get_conversation(session_id: str):
    if session_id not in conversation_store:
        init_conversation(session_id)
    return conversation_store[session_id]

async def get_assistant_reply_thread(thread_id: str, prompt: str) -> str:
    try:
        await asyncio.to_thread(
            openai.beta.threads.messages.create,
            thread_id=thread_id,
            role="user",
            content=f"사용자가 {ai_persona}과 대화하고 있습니다: {prompt}"
        )
        run_params = {"thread_id": thread_id, "assistant_id": ASSISTANT_ID}
        if VECTOR_STORE_ID:
            run_params["tools"] = [{"type": "file_search"}]
        run = await asyncio.to_thread(openai.beta.threads.runs.create, **run_params)
        
        while run.status not in ["completed", "failed"]:
            run = await asyncio.to_thread(
                openai.beta.threads.runs.retrieve,
                thread_id=thread_id,
                run_id=run.id
            )
            if run.status == "completed":
                messages = await asyncio.to_thread(
                    openai.beta.threads.messages.list,
                    thread_id=thread_id
                )
                return remove_citation_markers(messages.data[0].content[0].text.value)
            elif run.status == "failed":
                return "응답 생성에 실패했습니다. 다시 시도해 주세요."
            await asyncio.sleep(0.5)
    except Exception as e:
        logger.error(f"Error in get_assistant_reply_thread: {e}")
        return "오류가 발생했습니다. 다시 시도해 주세요."

def convert_newlines_to_br(text: str) -> str:
    escaped = html.escape(text)
    return escaped.replace('\n', '<br>')

def render_chat_interface(conversation) -> str:
    """
    - static 폴더 없이 외부 이미지만 사용
    - 말풍
