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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 환경 변수 및 API 설정 (Railway의 Shared Variables에 설정)
PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY")
if not PERPLEXITY_API_KEY:
    logger.error("PERPLEXITY_API_KEY 환경 변수가 설정되지 않았습니다.")

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
MODEL_NAME = os.environ.get("MODEL_NAME", "sonar")  # 필요에 따라 "sonar-pro" 등으로 변경 가능

# 아이콘 및 페르소나
ai_icon = "🪷"
user_icon = "🧑🏻‍💻"

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SECRET_KEY", "your-secret-key"))

# 대화 저장소 (간단한 메모리 기반)
conversation_store = {}

def remove_citation_markers(text: str) -> str:
    return re.sub(r'【\d+:\d+†source】', '', text)

def convert_newlines_to_br(text: str) -> str:
    return html.escape(text).replace('\n', '<br>')

def render_chat_interface(conversation) -> str:
    messages_html = ""
    for msg in conversation["messages"]:
        rendered = convert_newlines_to_br(msg["content"])
        if msg["role"] == "assistant":
            messages_html += f"""
            <div class="chat-message assistant-message flex mb-4 animate-fadeIn">
                <div class="avatar text-3xl mr-3">{ai_icon}</div>
                <div class="bubble bg-slate-100 border-l-4 border-slate-400 p-3 rounded-lg shadow-sm">
                    {rendered}
                </div>
            </div>
            """
        else:
            messages_html += f"""
            <div class="chat-message user-message flex justify-end mb-4 animate-fadeIn">
                <div class="bubble bg-white border-l-4 border-gray-400 p-3 rounded-lg shadow-sm mr-3">
                    {rendered}
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
      <script src="https://unpkg.com/htmx.org@1.7.0"></script>
      <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
      <style>
        html, body {{ margin: 0; padding: 0; height: 100%; }}
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
        .animate-fadeIn {{ animation: fadeIn 0.4s ease-in-out forwards; }}
        .chat-container {{
          position: relative;
          width: 100%;
          max-width: 800px;
          height: 90vh;
          margin: auto;
          background-color: rgba(255, 255, 255, 0.8);
          backdrop-filter: blur(4px);
          border-radius: 0.75rem;
          box-shadow: 0 8px 16px rgba(0,0,0,0.15);
          overflow: hidden;
        }}
        #chat-header {{
          position: absolute;
          top: 0; left: 0; right: 0;
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
          top: 60px; bottom: 70px;
          left: 0; right: 0;
          overflow-y: auto;
          padding: 1rem;
        }}
        #chat-input {{
          position: absolute;
          bottom: 0; left: 0; right: 0;
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
      <div class="chat-container">
        <div id="chat-header">
          <div class="flex items-center">
            <img src="https://raw.githubusercontent.com/buddhai/hyundai/master/logo2.PNG" alt="현대불교 로고" class="h-10 mr-2"/>
          </div>
          <form action="/reset" method="get" class="flex justify-end">
            <button class="bg-blue-700 hover:bg-blue-600 text-white font-bold py-1 px-2 text-sm sm:py-2 sm:px-4 sm:text-base rounded-lg border border-blue-900 shadow-lg hover:shadow-xl transition-all duration-300">
              대화 초기화
            </button>
          </form>
        </div>
        <div id="chat-messages">
          {messages_html}
        </div>
        <div id="chat-input">
          <form id="chat-form"
                hx-post="/message?phase=init"
                hx-target="#chat-messages"
                hx-swap="beforeend"
                onsubmit="setTimeout(() => this.reset(), 0)"
                class="flex w-full">
            <input type="text" name="message" placeholder="스님 AI에게 질문하세요"
                   class="flex-1 p-3 rounded-l-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-400" required />
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
    if session_id not in conversation_store:
        conversation_store[session_id] = {
            "messages": [
                {"role": "assistant", "content": "모든 답은 당신 안에 있습니다. 저는 그 여정을 함께하는 스님 AI입니다. 무엇이 궁금하신가요? 🙏🏻"}
            ]
        }
    return HTMLResponse(content=render_chat_interface(conversation_store[session_id]))

async def get_perplexity_reply(messages) -> str:
    """
    Perplexity API를 호출하여 대화 기록(messages)에 대한 AI 응답을 생성합니다.
    불필요한 값(None)은 payload에서 제외합니다.
    """
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
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
            data = response.json()
            reply = data["choices"][0]["message"]["content"]
            return remove_citation_markers(reply)
    except Exception as e:
        logger.error(f"Perplexity API 호출 오류: {e}")
        return "응답 생성에 실패했습니다. 다시 시도해 주세요."

@app.post("/message", response_class=HTMLResponse)
async def message_init(request: Request, message: str = Form(...), phase: str = Query(None)):
    session_id = request.session.get("session_id", str(uuid.uuid4()))
    request.session["session_id"] = session_id
    if session_id not in conversation_store:
        conversation_store[session_id] = {"messages": []}
    conv = conversation_store[session_id]

    # 사용자 메시지 저장
    conv["messages"].append({"role": "user", "content": message})
    # 자리 표시 응답 추가
    placeholder_id = str(uuid.uuid4())
    conv["messages"].append({"role": "assistant", "content": "답변 생성 중..."})
    
    user_msg_html = f"""
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
    return HTMLResponse(content=user_msg_html + placeholder_html)

@app.get("/message", response_class=HTMLResponse)
async def message_answer(request: Request, placeholder_id: str = Query(None), phase: str = Query(None)):
    if phase != "answer":
        return HTMLResponse("Invalid phase", status_code=400)
    session_id = request.session.get("session_id")
    if not session_id or session_id not in conversation_store:
        return HTMLResponse("Session not found", status_code=400)
    conv = conversation_store[session_id]
    
    # Perplexity API를 호출하여 전체 대화 기록 기반 응답 생성
    ai_reply = await get_perplexity_reply(conv["messages"])
    # 마지막 AI 메시지를 실제 응답으로 업데이트
    if conv["messages"] and conv["messages"][-1]["role"] == "assistant":
        conv["messages"][-1]["content"] = ai_reply
    else:
        conv["messages"].append({"role": "assistant", "content": ai_reply})
    
    final_html = f"""
    <div class="chat-message assistant-message flex mb-4 animate-fadeIn" id="assistant-block-{placeholder_id}">
        <div class="avatar text-3xl mr-3">{ai_icon}</div>
        <div class="bubble bg-slate-100 border-l-4 border-slate-400 p-3 rounded-lg shadow-sm">
            {convert_newlines_to_br(ai_reply)}
        </div>
    </div>
    """
    return HTMLResponse(content=final_html)

@app.get("/reset")
async def reset_conversation(request: Request):
    session_id = request.session.get("session_id")
    if session_id in conversation_store:
        del conversation_store[session_id]
    return RedirectResponse(url="/", status_code=302)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
