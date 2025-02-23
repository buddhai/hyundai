import os
import re
import uuid
import time
import logging

import openai
from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
import uvicorn

# (옵션) 비동기 처리를 위한 asyncio
import asyncio

# .env 파일의 환경 변수를 로드
from dotenv import load_dotenv
load_dotenv()

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 환경변수에서 설정값 불러오기
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ASSISTANT_ID = os.environ.get("ASSISTANT_ID", "default_assistant_id")
VECTOR_STORE_ID = os.environ.get("VECTOR_STORE_ID", "")

if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
openai.api_key = OPENAI_API_KEY

# 상수 정의
ai_icon = "🪷"
user_icon = "🧑🏻‍💻"
ai_persona = "스님 AI"

# FastAPI 앱 생성 & 세션 미들웨어 추가
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="your-secret-key")

# 세션별 대화를 저장할 전역 딕셔너리
conversation_store = {}

def remove_citation_markers(text: str) -> str:
    """인용 마커 제거 (OpenAI Threads 예시)"""
    return re.sub(r'【\d+:\d+†source】', '', text)

def create_thread():
    """beta threads API를 사용하여 새로운 스레드 생성"""
    try:
        thread = openai.beta.threads.create()
        return thread.id
    except Exception as e:
        logger.error(f"Thread creation failed: {e}")
        return None

def init_conversation(session_id: str):
    """세션별 대화 초기화"""
    thread_id = create_thread()
    initial_message = (
        "모든 답은 당신 안에 있습니다. "
        "저는 그 여정을 함께하는 AI입니다. 무엇이 궁금하신가요? 🙏🏻"
    )
    conversation_store[session_id] = {
        "thread_id": thread_id,
        "messages": [{"role": "assistant", "content": initial_message}]
    }

def get_conversation(session_id: str):
    """세션에 따른 대화 가져오기 (없으면 초기화)"""
    if session_id not in conversation_store:
        init_conversation(session_id)
    return conversation_store[session_id]

def get_assistant_reply_thread(thread_id: str, prompt: str) -> str:
    """동기적으로 OpenAI Threads API를 호출하여 답변 생성"""
    try:
        openai.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=f"사용자가 {ai_persona}과 대화하고 있습니다: {prompt}"
        )
        run_params = {"thread_id": thread_id, "assistant_id": ASSISTANT_ID}
        if VECTOR_STORE_ID:
            run_params["tools"] = [{"type": "file_search"}]
        run = openai.beta.threads.runs.create(**run_params)

        while run.status not in ["completed", "failed"]:
            run = openai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run.status == "completed":
                messages = openai.beta.threads.messages.list(thread_id=thread_id)
                return remove_citation_markers(messages.data[0].content[0].text.value)
            elif run.status == "failed":
                return "응답 생성에 실패했습니다. 다시 시도해 주세요."
            time.sleep(0.5)
    except Exception as e:
        logger.error(f"Error in get_assistant_reply_thread: {e}")
        return "오류가 발생했습니다. 다시 시도해 주세요."

def render_chat_interface(conversation) -> str:
    """HTMX + TailwindCSS 기반 채팅 UI (우디 + 차분한 무드 + 짙은 버튼색)"""
    messages_html = ""
    for msg in conversation["messages"]:
        if msg["role"] == "assistant":
            # 왼쪽 정렬 (AI)
            messages_html += f"""
            <div class="chat-message assistant-message flex mb-4 opacity-0 animate-fadeIn">
                <div class="avatar text-3xl mr-3">{ai_icon}</div>
                <div class="bubble bg-[#E3D5C9] border-l-4 border-[#B8A595] p-3 rounded-lg shadow-sm">
                    {msg['content']}
                </div>
            </div>
            """
        else:
            # 오른쪽 정렬 (사용자)
            messages_html += f"""
            <div class="chat-message user-message flex justify-end mb-4 opacity-0 animate-fadeIn">
                <div class="bubble bg-[#F6F2EB] border-l-4 border-[#B8A595] p-3 rounded-lg shadow-sm mr-3">
                    {msg['content']}
                </div>
                <div class="avatar text-3xl">{user_icon}</div>
            </div>
            """

    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
      <meta charset="UTF-8">
      <title>{ai_persona}</title>
      <!-- HTMX -->
      <script src="https://unpkg.com/htmx.org@1.7.0"></script>
      <!-- Tailwind CSS -->
      <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
      <style>
        /* 배경: 우드 텍스처 + 반투명 오버레이 */
        body {{
          font-family: 'Noto Sans KR', sans-serif;
          background: url('https://picsum.photos/id/1062/1200/800') no-repeat center center fixed;
          background-size: cover;
          background-color: rgba(246, 242, 235, 0.8);
          background-blend-mode: lighten;
        }}
        .chat-container {{
          max-width: 800px;
          margin: 2rem auto;
          background-color: rgba(255, 255, 255, 0.7);
          border-radius: 0.75rem;
          box-shadow: 0 8px 16px rgba(0,0,0,0.15);
          backdrop-filter: blur(4px);
        }}
        /* 새 말풍선 서서히 나타나는 애니메이션 */
        @keyframes fadeIn {{
          0% {{ opacity: 0; transform: translateY(10px); }}
          100% {{ opacity: 1; transform: translateY(0); }}
        }}
        .animate-fadeIn {{
          animation: fadeIn 0.4s ease-in-out forwards;
        }}
      </style>
    </head>
    <body class="min-h-screen flex flex-col">
      <!-- 상단 헤더/바 -->
      <div class="w-full py-4 px-6 flex justify-between items-center">
        <div class="text-xl font-bold text-[#3F3A36]">
          🪷 {ai_persona} 챗봇
        </div>
        <!-- 대화 초기화 버튼 (오른쪽 정렬) -->
        <form action="/reset" method="get" class="flex justify-end">
          <button 
            class="bg-amber-700 hover:bg-amber-600 text-white font-bold py-2 px-4 
                  rounded-lg border border-amber-900 shadow-lg hover:shadow-xl 
                  transition-all duration-300 opacity-100">
            대화 초기화
          </button>










        </form>
      </div>

      <!-- 채팅 컨테이너 -->
      <div class="chat-container p-6 flex flex-col flex-grow">
        <!-- 메시지 표시 영역 -->
        <div id="chat-messages" class="flex-grow mb-4">
          {messages_html}
        </div>

        <!-- 사용자 입력 폼 -->
        <!-- 단순 POST -> (이 예시에서는) phase=init로 사용자/placeholder 동시에 -->
        <form id="chat-form"
              hx-post="/message?phase=init"
              hx-target="#chat-messages"
              hx-swap="beforeend"
              onsubmit="setTimeout(() => this.reset(), 0)"
              class="mt-4">
          <div class="flex">
            <input type="text"
                   name="message"
                   placeholder="스님 AI에게 질문하세요"
                   class="flex-1 p-3 rounded-l-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-[#875f3c]"
                   required />
            <button type="submit"
              class="bg-amber-700 hover:bg-amber-600 text-white font-bold p-3 
                    rounded-r-lg border border-amber-900 shadow-lg hover:shadow-xl 
                    transition-all duration-300 opacity-100">
              전송
            </button>

          </div>
        </form>
      </div>
    </body>
    </html>
    """

@app.get("/", response_class=HTMLResponse)
async def get_chat(request: Request):
    session_id = request.session.get("session_id", str(uuid.uuid4()))
    request.session["session_id"] = session_id
    return HTMLResponse(content=render_chat_interface(get_conversation(session_id)))

@app.post("/message", response_class=HTMLResponse)
async def message_init(
    request: Request,
    message: str = Form(...),
    phase: str = Query(None)
):
    """
    phase=init -> 사용자 메시지 + '답변 생성 중...' 말풍선 (+ hx-get=... 로 자동 2단계 요청)
    phase=answer -> 실제 답변 생성 후 placeholder 교체
    """
    session_id = request.session.get("session_id", str(uuid.uuid4()))
    request.session["session_id"] = session_id
    conv = get_conversation(session_id)

    # 사용자 메시지 추가
    if phase == "init":
        # 1) 사용자 말풍선
        conv["messages"].append({"role": "user", "content": message})

        # 2) placeholder '답변 생성 중...'
        placeholder_id = str(uuid.uuid4())
        conv["messages"].append({"role": "assistant", "content": "답변 생성 중..."})

        # 사용자 말풍선 HTML
        user_message_html = f"""
        <div class="chat-message user-message flex justify-end mb-4 opacity-0 animate-fadeIn">
            <div class="bubble bg-[#F6F2EB] border-l-4 border-[#B8A595] p-3 rounded-lg shadow-sm mr-3">
                {message}
            </div>
            <div class="avatar text-3xl">{user_icon}</div>
        </div>
        """
        # AI placeholder 말풍선 (자동 GET phase=answer)
        placeholder_html = f"""
        <div class="chat-message assistant-message flex mb-4 opacity-0 animate-fadeIn" id="assistant-block-{placeholder_id}">
            <div class="avatar text-3xl mr-3">{ai_icon}</div>
            <div class="bubble bg-[#E3D5C9] border-l-4 border-[#B8A595] p-3 rounded-lg shadow-sm"
                 id="ai-msg-{placeholder_id}"
                 hx-get="/message?phase=answer&placeholder_id={placeholder_id}"
                 hx-trigger="load"
                 hx-target="#assistant-block-{placeholder_id}"
                 hx-swap="outerHTML">
                답변 생성 중...
            </div>
        </div>
        """
        return HTMLResponse(content=user_message_html + placeholder_html)

    # phase 값이 없거나 잘못된 경우
    return HTMLResponse("Invalid phase", status_code=400)

@app.get("/message", response_class=HTMLResponse)
async def message_answer(
    request: Request,
    placeholder_id: str = Query(None),
    phase: str = Query(None)
):
    """
    phase=answer -> AI 실제 답변 생성 후 placeholder 교체
    """
    if phase != "answer":
        return HTMLResponse("Invalid phase", status_code=400)

    session_id = request.session.get("session_id")
    if not session_id:
        return HTMLResponse("Session not found", status_code=400)

    conv = get_conversation(session_id)

    # 마지막 user 메시지 찾기
    user_messages = [m for m in conv["messages"] if m["role"] == "user"]
    if not user_messages:
        return HTMLResponse("No user message found", status_code=400)

    last_user_message = user_messages[-1]["content"]

    # AI 최종 답변 생성
    ai_reply = get_assistant_reply_thread(conv["thread_id"], last_user_message)

    # conv의 마지막 assistant를 최종 답변으로 수정
    if conv["messages"] and conv["messages"][-1]["role"] == "assistant":
        conv["messages"][-1]["content"] = ai_reply
    else:
        conv["messages"].append({"role": "assistant", "content": ai_reply})

    # 최종 답변 말풍선 HTML -> placeholder 교체
    final_ai_html = f"""
    <div class="chat-message assistant-message flex mb-4 opacity-0 animate-fadeIn" id="assistant-block-{placeholder_id}">
        <div class="avatar text-3xl mr-3">{ai_icon}</div>
        <div class="bubble bg-[#E3D5C9] border-l-4 border-[#B8A595] p-3 rounded-lg shadow-sm">
            {ai_reply}
        </div>
    </div>
    """
    return HTMLResponse(content=final_ai_html)

@app.get("/reset")
async def reset_conversation(request: Request):
    session_id = request.session.get("session_id")
    if session_id and session_id in conversation_store:
        del conversation_store[session_id]
    return RedirectResponse(url="/", status_code=302)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
