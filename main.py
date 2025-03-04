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

# GEMINI_API_KEY 환경 변수 확인 (Google AI Studio에서 발급받은 키)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")

# Gemini API 클라이언트 초기화
from google import genai
client = genai.Client(api_key=GEMINI_API_KEY)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="your-secret-key")

conversation_store = {}

def remove_citation_markers(text: str) -> str:
    return re.sub(r'【\d+:\d+†source】', '', text)

def remove_markdown_bold(text: str) -> str:
    """
    ** 또는 __로 감싸진 굵은 텍스트 마크업 문법을 제거합니다.
    """
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    return text

def convert_newlines_to_br(text: str) -> str:
    # HTML 이스케이프 후 줄바꿈을 <br>로 변환
    escaped = html.escape(text)
    return escaped.replace('\n', '<br>')

def render_chat_interface(conversation) -> str:
    """
    대화 이력 중 "system" 역할 메시지는 UI에 표시하지 않습니다.
    """
    messages_html = ""
    for msg in conversation["messages"]:
        if msg["role"] == "system":
            continue  # 시스템 메시지는 표시하지 않음
        rendered_content = convert_newlines_to_br(msg["content"])

        base_bubble_class = (
            "p-4 md:p-3 rounded-2xl shadow-md transition-all duration-300 animate-fadeIn"
        )

        if msg["role"] == "assistant":
            # 어시스턴트(챗봇) 말풍선: 왼쪽 정렬
            messages_html += f"""
            <div class="chat-message assistant-message flex mb-4 items-start">
                <div class="bubble bg-white/80 border-l-4 border-indigo-400 {base_bubble_class}">
                    {rendered_content}
                </div>
            </div>
            """
        else:
            # 사용자 말풍선: 오른쪽 정렬
            messages_html += f"""
            <div class="chat-message user-message flex justify-end mb-4 items-start">
                <div class="bubble bg-gray-100 border-r-4 border-gray-400 {base_bubble_class}">
                    {rendered_content}
                </div>
            </div>
            """

    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>현대불교신문 AI</title>
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
          /* 불교 사찰 풍경 이미지 */
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
          background-color: rgba(255, 255, 255, 0.35);
          backdrop-filter: blur(10px);
          border-radius: 1rem;
          box-shadow: 0 8px 24px rgba(0,0,0,0.2);
          overflow: hidden;
          border: 1px solid rgba(255,255,255,0.4);
        }}
        #chat-header {{
          position: absolute;
          top: 0;
          left: 0; right: 0;
          height: 60px;
          background-color: rgba(255, 255, 255, 0.3);
          backdrop-filter: blur(6px);
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 1rem;
          border-bottom: 1px solid rgba(255,255,255,0.4);
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
          background-color: rgba(255, 255, 255, 0.3);
          backdrop-filter: blur(6px);
          display: flex;
          align-items: center;
          padding: 0 1rem;
          border-top: 1px solid rgba(255,255,255,0.4);
        }}
      </style>
    </head>
    <body class="h-full flex items-center justify-center">
      <div class="chat-container">
        <!-- 헤더: 텍스트 대신 로고 이미지만 표시 -->
        <div id="chat-header">
          <div class="flex items-center">
            <img 
              src="https://raw.githubusercontent.com/buddhai/hyundai/master/logo5.png" 
              alt="현대불교 로고" 
              class="h-10"
            />
          </div>
          <!-- 대화 초기화 버튼: 아이콘만 -->
          <form action="/reset" method="get" class="flex justify-end">
            <button class="
              bg-gradient-to-r from-gray-900 to-gray-700
              hover:from-gray-700 hover:to-gray-900
              text-white
              py-2 px-4
              rounded-full
              border border-gray-900
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
                   placeholder="메시지"
                   class="
                     flex-1
                     p-3
                     rounded-l-full
                     border border-gray-300
                     focus:outline-none
                     focus:ring-2
                     focus:ring-gray-600
                     text-gray-700
                   "
                   required />
            <!-- 전송 버튼: 아이콘만 -->
            <button type="submit"
                    class="
                      bg-gradient-to-r from-gray-900 to-gray-700
                      hover:from-gray-700 hover:to-gray-900
                      text-white
                      py-2 px-4
                      rounded-r-full
                      border border-gray-900
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
        "모든 답은 당신 안에 있습니다. "
        "저는 그 여정을 함께하는 현대불교신문 AI입니다. 무엇이 궁금하신가요?"
    )
    # Gemini API를 사용하여 채팅 세션 생성 (모델: gemini-2.0-flash)
    chat_session = client.chats.create(model="gemini-2.0-flash")
    conversation_store[session_id] = {
        "chat": chat_session,
        "messages": [
            {"role": "system", "content": system_message}
