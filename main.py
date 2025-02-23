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
ai_persona = "스님 AI 챗봇"  # 내부적으로만 사용 (헤더에는 표시하지 않음)

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
    """
    OpenAI Threads API를 비동기로 호출하여 답변 생성.
    """
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
    # HTML 이스케이프 + 줄바꿈 -> <br>
    escaped = html.escape(text)
    return escaped.replace('\n', '<br>')

def render_chat_interface(conversation) -> str:
    """
    - 배경: 전체 화면 (body)
    - 컨테이너(.chat-container): 반투명 박스
    - 헤더: 로고만 표시 (제목 제거)
    - 말풍선: bg-slate-100 / bg-white
    - 버튼: 파란색 계열
    """
    messages_html = ""
    for msg in conversation["messages"]:
        rendered_content = convert_newlines_to_br(msg["content"])
        if msg["role"] == "assistant":
            messages_html += f"""
            <div class="chat-message assistant-message flex mb-4 animate-fadeIn">
                <div class="avatar text-3xl mr-3">{ai_icon}</div>
                <div class="bubble bg-slate-100 border-l-4 border-slate-400 p-3 rounded-lg shadow-sm">
                    {rendered_content}
                </div>
            </div>
            """
        else:
            messages_html += f"""
            <div class="chat-message user-message flex justify-end mb-4 animate-fadeIn">
                <div class="bubble bg-white border-l-4 border-gray-400 p-3 rounded-lg shadow-sm mr-3">
                    {rendered_content}
                </div>
                <div class="avatar text-3xl">{user_icon}</div>
            </div>
            """

    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>스님 AI</title>
      <!-- HTMX -->
      <script src="https://unpkg.com/htmx.org@1.7.0"></script>
      <!-- Tailwind CSS -->
      <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
      <style>
        html, body {{
          margin: 0; padding: 0; height: 100%;
        }}
        body {{
          font-family: 'Noto Sans KR', sans-serif;
          /* 배경 이미지 */
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
        /* 전체 컨테이너: 반투명 화이트 박스 */
        .chat-container {{
          position: relative;
          width: 100%;
          max-width: 800px;
          height: 90vh; /* 높이 90% */
          margin: auto;
          background-color: rgba(255, 255, 255, 0.8); /* 반투명 화이트 */
          backdrop-filter: blur(4px);
          border-radius: 0.75rem;
          box-shadow: 0 8px 16px rgba(0,0,0,0.15);
          overflow: hidden;
        }}
        /* 헤더, 메시지, 입력창은 chat-container 내부에서 절대 배치 */
        #chat-header {{
          position: absolute;
          top: 0;
          left: 0; right: 0;
          height: 60px;
          background-color: rgba(255, 255, 255, 0.7);
          backdrop-filter: blur(4px);
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 1rem;
        }}
        #chat-messages {{
          position: absolute;
          top: 60px;
          bottom: 70px;
          left: 0; right: 0;
          overflow-y: auto;
          padding: 1rem;
        }}
        #chat-input {{
          position: absolute;
          bottom: 0;
          left: 0; right: 0;
          height: 70px;
          background-color: rgba(255, 255, 255, 0.7);
          backdrop-filter: blur(4px);
          display: flex;
          align-items: center;
          padding: 0 1rem;
          border-top: 1px solid #ddd;
        }}
      </style>
    </head>
    <body class="h-full flex items-center justify-center">
      <!-- 반투명 화이트 박스 컨테이너 -->
      <div class="chat-container">
        <!-- 헤더 (제목 제거, 로고만) -->
        <div id="chat-header">
          <div class="flex items-center">
            <!-- 로고 -->
            <img 
              src="https://github.com/buddhai/hyundai/raw/master/%ED%98%84%EB%8C%80%EB%B6%88%EA%B5%90%20%EB%A1%9C%EA%B3%A0.png" 
              alt="현대불교 로고" 
              class="h-10 mr-2"
            />
          </div>
          <form action="/reset" method="get" class="flex justify-end">
            <button class="bg-blue-700 hover:bg-blue-600 text-white font-bold py-2 px-4 rounded-lg border border-blue-900 shadow-lg hover:shadow-xl transition-all duration-300">
              대화 초기화
            </button>
          </form>
        </div>

        <!-- 메시지 표시 영역 -->
        <div id="chat-messages">
          {messages_html}
        </div>

        <!-- 입력창 -->
        <div id="chat-input">
          <form id="chat-form"
                hx-post="/message?phase=init"
                hx-target="#chat-messages"
                hx-swap="beforeend"
                onsubmit="setTimeout(() => this.reset(), 0)"
                class="flex w-full">
            <input type="text"
                   name="message"
                   placeholder="스님 AI에게 질문하세요"
                   class="flex-1 p-3 rounded-l-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-400"
                   required />
            <button type="submit"
                    class="bg-blue-700 hover:bg-blue-600 text-white font-bold p-3 rounded-r-lg border border-blue-900 shadow-lg hover:shadow-xl transition-all duration-300">
              전송
            </button>
          </form>
        </div>
      </div>

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
    session_id = request.session.get("session_id", str(uuid.uuid4()))
    request.session["session_id"] = session_id
    conv = get_conversation(session_id)
    
    if phase == "init":
        conv["messages"].append({"role": "user", "content": message})
        placeholder_id = str(uuid.uuid4())
        conv["messages"].append({"role": "assistant", "content": "답변 생성 중..."})
        
        user_message_html = f"""
        <div class="chat-message user-message flex justify-end mb-4 animate-fadeIn">
            <div class="bubble bg-white border-l-4 border-gray-400 p-3 rounded-lg shadow-sm mr-3">
                {convert_newlines_to_br(message)}
            </div>
            <div class="avatar text-3xl">{user_icon}</div>
        </div>
        """
        placeholder_html = f"""
        <div class="chat-message assistant-message flex mb-4 animate-fadeIn" id="assistant-block-{placeholder_id}">
            <div class="avatar text-3xl mr-3">{ai_icon}</div>
            <div class="bubble bg-slate-100 border-l-4 border-slate-400 p-3 rounded-lg shadow-sm"
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
    
    if conv["messages"] and conv["messages"][-1]["role"] == "assistant":
        conv["messages"][-1]["content"] = ai_reply
    else:
        conv["messages"].append({"role": "assistant", "content": ai_reply})
    
    final_ai_html = f"""
    <div class="chat-message assistant-message flex mb-4 animate-fadeIn" id="assistant-block-{placeholder_id}">
        <div class="avatar text-3xl mr-3">{ai_icon}</div>
        <div class="bubble bg-slate-100 border-l-4 border-slate-400 p-3 rounded-lg shadow-sm">
            {convert_newlines_to_br(ai_reply)}
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
