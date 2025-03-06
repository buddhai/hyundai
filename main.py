import os
import re
import uuid
import logging
import asyncio
import uvicorn
import html

from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# GEMINI_API_KEY 환경 변수 확인
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")

# Gemini API 클라이언트 초기화 및 도구 임포트 (공식 가이드 방식)
from google import genai
from google.genai import types
client = genai.Client(api_key=GEMINI_API_KEY)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="your-secret-key")

# 대화 기록 저장 (세션 별)
conversation_store = {}
BASE_BUBBLE_CLASS = "p-4 md:p-3 rounded-2xl shadow-md transition-all duration-300 animate-fadeIn"

def remove_markdown_bold(text: str) -> str:
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    return text

def convert_newlines_to_br(text: str) -> str:
    escaped = html.escape(text)
    return escaped.replace('\n', '<br>')

def render_chat_interface(conversation) -> str:
    messages_html = ""
    for msg in conversation["messages"]:
        # 시스템 메시지는 UI에 출력하지 않습니다.
        if msg["role"] == "system":
            continue
        rendered_content = convert_newlines_to_br(msg["content"])
        if msg["role"] == "assistant":
            messages_html += f"""
            <div class="chat-message assistant-message flex mb-4 items-start">
                <div class="bubble bg-gray-200 border-l-2 border-teal-400 {BASE_BUBBLE_CLASS}" style="max-width:70%;">
                    {rendered_content}
                </div>
            </div>
            """
        else:
            messages_html += f"""
            <div class="chat-message user-message flex justify-end mb-4 items-start">
                <div class="bubble bg-gray-100 border-r-2 border-gray-300 {BASE_BUBBLE_CLASS}" style="max-width:70%;">
                    {rendered_content}
                </div>
            </div>
            """
    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
      <meta charset="UTF-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <title>현대불교신문 AI</title>
      <!-- HTMX -->
      <script src="https://unpkg.com/htmx.org@1.7.0"></script>
      <!-- Tailwind CSS -->
      <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet" />
      <style>
        html, body {{
          margin: 0; padding: 0; height: 100%;
        }}
        body {{
          font-family: 'Noto Sans KR', sans-serif;
          background: url('https://source.unsplash.com/1600x900/?buddhism,temple') no-repeat center center;
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
        .chat-container {{
          position: relative;
          width: 100%;
          max-width: 800px;
          height: 90vh;
          margin: auto;
          background-color: rgba(255, 255, 255, 0.8);
          backdrop-filter: blur(10px);
          border-radius: 1rem;
          box-shadow: 0 8px 24px rgba(0,0,0,0.2);
          overflow: hidden;
          border: 1px solid rgba(255,255,255,0.3);
        }}
        #chat-header {{
          position: absolute;
          top: 0;
          left: 0; right: 0;
          height: 60px;
          background-color: rgba(255, 255, 255, 0.6);
          backdrop-filter: blur(6px);
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 1rem;
          border-bottom: 1px solid rgba(255,255,255,0.3);
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
          background-color: rgba(255, 255, 255, 0.6);
          backdrop-filter: blur(6px);
          display: flex;
          align-items: center;
          padding: 0 1rem;
          border-top: 1px solid rgba(255,255,255,0.3);
        }}
      </style>
    </head>
    <body class="h-full flex items-center justify-center">
      <div class="chat-container">
        <div id="chat-header">
          <div class="flex items-center">
            <img 
              src="https://raw.githubusercontent.com/buddhai/hyundai/master/logo5.png"
              alt="현대불교 로고"
              class="h-10"
            />
          </div>
          <form action="/reset" method="get" class="flex justify-end">
            <button class="
              bg-gradient-to-r from-gray-900 to-gray-700
              hover:from-gray-700 hover:to-gray-900
              text-white
              py-2 px-4
              rounded-full
              border-0
              shadow-md
              hover:shadow-xl
              transition-all
              duration-300
              flex items-center
            ">
              ↻
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
            <input type="text"
                   name="message"
                   placeholder="메시지"
                   class="
                     flex-1
                     p-3
                     rounded-l-full
                     bg-white
                     border border-gray-300
                     focus:ring-2
                     focus:ring-gray-400
                     focus:outline-none
                     text-gray-700
                   "
                   required />
            <button type="submit"
                    class="
                      bg-gradient-to-r from-gray-900 to-gray-700
                      hover:from-gray-700 hover:to-gray-900
                      text-white
                      py-2 px-4
                      rounded-r-full
                      border-0
                      shadow-md
                      hover:shadow-xl
                      transition-all
                      duration-300
                      flex items-center
                    ">
              →
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

def init_conversation(session_id: str):
    system_message = (
        "시스템 안내: 당신은 한마음선원 현대불교신문의 AI입니다. "
        "항상 친근하고 예의바르게, 그 신문의 명예와 위상을 높이는 답변을 제공하며, "
        "사용자의 질문에 대해 상세하고 정확하게, 그리고 매우 호의적으로 응답합니다."
    )
    initial_message = (
        "모든 답은 당신 안에 있습니다.\n"
        "저는 그 여정을 함께하는 현대불교신문 AI입니다.\n"
        "무엇이 궁금하신가요?"
    )
    # 대화 기록 초기화
    conversation_store[session_id] = {
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "assistant", "content": initial_message}
        ]
    }

def get_conversation(session_id: str):
    if session_id not in conversation_store:
        init_conversation(session_id)
    return conversation_store[session_id]

def build_prompt(conversation) -> str:
    """
    대화 기록을 기반으로 프롬프트 문자열을 구성합니다.
    각 메시지를 "System:", "User:", "Assistant:" 형식으로 이어붙이고,
    마지막 줄에 "Assistant:"를 추가하여 응답 생성을 유도합니다.
    """
    prompt_lines = []
    for msg in conversation["messages"]:
        if msg["role"] == "system":
            prompt_lines.append("System: " + msg["content"])
        elif msg["role"] == "user":
            prompt_lines.append("User: " + msg["content"])
        elif msg["role"] == "assistant":
            prompt_lines.append("Assistant: " + msg["content"])
    prompt_lines.append("Assistant:")
    return "\n".join(prompt_lines)

async def get_assistant_reply(conversation) -> str:
    prompt = build_prompt(conversation)
    try:
        # 첫 번째 단계: Google 검색 그라운딩 도구 구성하여 사실 기반 답변 생성
        google_search_tool = types.Tool(
            google_search=types.GoogleSearch()
        )
        config = types.GenerateContentConfig(
            tools=[google_search_tool],
            response_modalities=["TEXT"]
        )
        response = await asyncio.to_thread(
            client.models.generate_content,
            model='gemini-2.0-flash',
            contents=prompt,
            config=config
        )
        initial_answer = remove_markdown_bold(response.text)
        
        # 두 번째 단계: 한 가지 최종 답변만, 그러나 좀 더 "자세하게" 대화체로 재작성
        rephrase_prompt = (
            "Please rewrite the following answer in a friendly and conversational tone in Korean. "
            "Provide a single, detailed final answer without multiple options or breakdowns.\n\n"
            f"{initial_answer}\n\n"
            "답변:"
        )
        rephrase_response = await asyncio.to_thread(
            client.models.generate_content,
            model='gemini-2.0-flash',
            contents=rephrase_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT"]
            )
        )
        final_answer = remove_markdown_bold(rephrase_response.text)
        return final_answer
    except Exception as e:
        logger.error("Error in generate_content: " + str(e))
        return "죄송합니다. 답변 생성 중 오류가 발생했습니다."

@app.get("/", response_class=HTMLResponse)
async def get_chat(request: Request):
    session_id = request.session.get("session_id", str(uuid.uuid4()))
    request.session["session_id"] = session_id
    conv = get_conversation(session_id)
    return HTMLResponse(content=render_chat_interface(conv))

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
        # 임시 메시지 추가
        conv["messages"].append({"role": "assistant", "content": "답변 생성 중..."})
        
        user_message_html = f"""
        <div class="chat-message user-message flex justify-end mb-4 items-start animate-fadeIn">
            <div class="bubble bg-gray-100 border-r-2 border-gray-300 {BASE_BUBBLE_CLASS}" style="max-width:70%;">
                {convert_newlines_to_br(message)}
            </div>
        </div>
        """
        placeholder_html = f"""
        <div class="chat-message assistant-message flex mb-4 items-start animate-fadeIn" id="assistant-block-{placeholder_id}">
            <div class="bubble bg-gray-200 border-l-2 border-teal-400 {BASE_BUBBLE_CLASS}" style="max-width:70%;"
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
    ai_reply = await get_assistant_reply(conv)
    
    # 대화 기록에 AI 응답 업데이트
    if conv["messages"] and conv["messages"][-1]["role"] == "assistant":
        conv["messages"][-1]["content"] = ai_reply
    else:
        conv["messages"].append({"role": "assistant", "content": ai_reply})
    
    final_ai_html = f"""
    <div class="chat-message assistant-message flex mb-4 items-start animate-fadeIn" id="assistant-block-{placeholder_id}">
        <div class="bubble bg-gray-200 border-l-2 border-teal-400 {BASE_BUBBLE_CLASS}" style="max-width:70%;">
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
