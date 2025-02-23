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

# 추가: 마크다운 변환용
from markdown import markdown

load_dotenv()

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 환경 변수 설정
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ASSISTANT_ID = os.environ.get("ASSISTANT_ID", "default_assistant_id")
VECTOR_STORE_ID = os.environ.get("VECTOR_STORE_ID", "")

if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")
openai.api_key = OPENAI_API_KEY

# 아이콘 및 페르소나 설정
ai_icon = "🪷"
user_icon = "🧑🏻‍💻"
ai_persona = "현대불교신문 AI"

# FastAPI 앱 생성 및 세션 미들웨어 추가
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="your-secret-key")

# 세션별 대화를 저장할 전역 딕셔너리
conversation_store = {}

def remove_citation_markers(text: str) -> str:
    """인용 마커 제거 (예: OpenAI Threads API 결과)"""
    return re.sub(r'【\d+:\d+†source】', '', text)

def create_thread():
    """새 스레드 생성 (OpenAI beta Threads API 사용)"""
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
        "저는 그 여정을 함께하는 현대불교신문 AI입니다. 무엇이 궁금하신가요? 🙏🏻"
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

async def get_assistant_reply_thread(thread_id: str, prompt: str) -> str:
    """
    OpenAI Threads API를 비동기로 호출하여 답변 생성.
    동기 API 호출은 asyncio.to_thread로 감싸 이벤트 루프의 블로킹을 최소화합니다.
    """
    try:
        # 사용자 메시지 전송
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
        
        # 응답 완료될 때까지 폴링
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

def markdown_to_html(text: str) -> str:
    """
    마크다운 텍스트 -> HTML 변환.
    extensions:
      - 'extra': fenced code blocks, tables, 등 확장 문법
      - 'nl2br': 단순 줄바꿈도 <br>로 처리
    """
    return markdown(text, extensions=["extra", "nl2br"])

def render_chat_interface(conversation) -> str:
    """
    HTMX + Tailwind CSS 기반 채팅 UI (레이어 분리 + 마크다운/줄바꿈 지원)
    - 상단 헤더
    - 채팅 메시지 영역 (스크롤 가능, 헤더와 입력창 사이)
    - 입력창은 항상 하단에 고정
    - 마크다운 파싱 -> HTML 변환
    - 새로운 메시지가 추가되면 자동 스크롤
    """
    messages_html = ""
    for msg in conversation["messages"]:
        # 마크다운 파싱 후 HTML 변환
        rendered_content = markdown_to_html(msg["content"])

        if msg["role"] == "assistant":
            messages_html += f"""
            <div class="chat-message assistant-message flex mb-4 opacity-0 animate-fadeIn">
                <div class="avatar text-3xl mr-3">{ai_icon}</div>
                <div class="bubble bg-[#E3D5C9] border-l-4 border-[#B8A595] p-3 rounded-lg shadow-sm">
                    {rendered_content}
                </div>
            </div>
            """
        else:
            messages_html += f"""
            <div class="chat-message user-message flex justify-end mb-4 opacity-0 animate-fadeIn">
                <div class="bubble bg-[#F6F2EB] border-l-4 border-[#B8A595] p-3 rounded-lg shadow-sm mr-3">
                    {rendered_content}
                </div>
                <div class="avatar text-3xl">{user_icon}</div>
            </div>
            """

    # HTML 전체 구조
    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>{ai_persona}</title>
      <!-- HTMX -->
      <script src="https://unpkg.com/htmx.org@1.7.0"></script>
      <!-- Tailwind CSS -->
      <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
      <style>
        html, body {{
          height: 100%;
          margin: 0;
          padding: 0;
        }}
        body {{
          font-family: 'Noto Sans KR', sans-serif;
          background: url('https://picsum.photos/id/1062/1200/800') no-repeat center center;
          background-size: cover;
          background-color: rgba(246, 242, 235, 0.8);
          background-blend-mode: lighten;
        }}
        @keyframes fadeIn {{
          0% {{ opacity: 0; transform: translateY(10px); }}
          100% {{ opacity: 1; transform: translateY(0); }}
        }}
        .animate-fadeIn {{
          animation: fadeIn 0.4s ease-in-out forwards;
        }}
        /* 채팅 메시지 영역은 헤더와 입력창 사이에 위치 */
        #chat-messages {{
          position: absolute;
          top: 60px; /* 헤더 높이에 맞춰 조절 */
          bottom: 70px; /* 입력창 높이 + 여백 */
          left: 0;
          right: 0;
          overflow-y: auto;
          padding: 1rem;
        }}
        /* 입력창 컨테이너는 항상 하단에 고정 */
        #chat-input {{
          position: fixed;
          bottom: 0;
          left: 0;
          right: 0;
          background-color: white;
          border-top: 1px solid #ddd;
          padding: 0.5rem 1rem;
        }}
      </style>
    </head>
    <body>
      <!-- 상단 헤더 -->
      <div class="flex-shrink-0 w-full py-2 px-4 flex justify-between items-center bg-white bg-opacity-70">
        <div class="text-xl font-bold text-[#3F3A36]">
          🪷 {ai_persona} 챗봇
        </div>
        <form action="/reset" method="get" class="flex justify-end">
          <button class="bg-amber-700 hover:bg-amber-600 text-white font-bold py-2 px-4 rounded-lg border border-amber-900 shadow-lg hover:shadow-xl transition-all duration-300">
            대화 초기화
          </button>
        </form>
      </div>
      
      <!-- 채팅 메시지 영역 -->
      <div id="chat-messages">
        {messages_html}
      </div>
      
      <!-- 입력창 (항상 하단 고정) -->
      <div id="chat-input">
        <form id="chat-form"
              hx-post="/message?phase=init"
              hx-target="#chat-messages"
              hx-swap="beforeend"
              onsubmit="setTimeout(() => this.reset(), 0)"
              class="flex">
          <input type="text"
                 name="message"
                 placeholder="스님 AI에게 질문하세요"
                 class="flex-1 p-3 rounded-l-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-[#875f3c]"
                 required />
          <button type="submit"
                  class="bg-amber-700 hover:bg-amber-600 text-white font-bold p-3 rounded-r-lg border border-amber-900 shadow-lg hover:shadow-xl transition-all duration-300">
            전송
          </button>
        </form>
      </div>
      
      <!-- 자동 스크롤 스크립트 -->
      <script>
        function scrollToBottom() {{
          var chatMessages = document.getElementById("chat-messages");
          chatMessages.scrollTop = chatMessages.scrollHeight;
        }}
        document.addEventListener("htmx:afterSwap", (event) => {{
          if (event.detail.target.id === "chat-messages") {{
            scrollToBottom();
          }}
        }});
        window.addEventListener("load", scrollToBottom);
      </script>
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
    phase=init: 사용자 메시지 전송 후 placeholder 추가
    phase=answer: 실제 AI 답변을 받아 placeholder 교체
    """
    session_id = request.session.get("session_id", str(uuid.uuid4()))
    request.session["session_id"] = session_id
    conv = get_conversation(session_id)
    
    if phase == "init":
        # 사용자 메시지 저장
        conv["messages"].append({"role": "user", "content": message})
        # AI 답변 placeholder 추가
        placeholder_id = str(uuid.uuid4())
        conv["messages"].append({"role": "assistant", "content": "답변 생성 중..."})
        
        user_message_html = f"""
        <div class="chat-message user-message flex justify-end mb-4 opacity-0 animate-fadeIn">
            <div class="bubble bg-[#F6F2EB] border-l-4 border-[#B8A595] p-3 rounded-lg shadow-sm mr-3">
                {markdown_to_html(message)}
            </div>
            <div class="avatar text-3xl">{user_icon}</div>
        </div>
        """
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
    
    return HTMLResponse("Invalid phase", status_code=400)

@app.get("/message", response_class=HTMLResponse)
async def message_answer(
    request: Request,
    placeholder_id: str = Query(None),
    phase: str = Query(None)
):
    if phase != "answer":
        return HTMLResponse("Invalid phase", status_code=400)
    
    session_id = request.session.get("session_id")
    if not session_id:
        return HTMLResponse("Session not found", status_code=400)
    
    conv = get_conversation(session_id)
    user_messages = [m for m in conv["messages"] if m["role"] == "user"]
    if not user_messages:
        return HTMLResponse("No user message found", status_code=400)
    
    last_user_message = user_messages[-1]["content"]
    ai_reply = await get_assistant_reply_thread(conv["thread_id"], last_user_message)
    
    # AI 메시지 덮어쓰기 (placeholder 교체)
    if conv["messages"] and conv["messages"][-1]["role"] == "assistant":
        conv["messages"][-1]["content"] = ai_reply
    else:
        conv["messages"].append({"role": "assistant", "content": ai_reply})
    
    final_ai_html = f"""
    <div class="chat-message assistant-message flex mb-4 opacity-0 animate-fadeIn" id="assistant-block-{placeholder_id}">
        <div class="avatar text-3xl mr-3">{ai_icon}</div>
        <div class="bubble bg-[#E3D5C9] border-l-4 border-[#B8A595] p-3 rounded-lg shadow-sm">
            {markdown_to_html(ai_reply)}
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
