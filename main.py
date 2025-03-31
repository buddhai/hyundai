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

# Gemini API 클라이언트 초기화
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
        # 시스템 메시지는 UI에 출력하지 않음
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
      <title>현대불교신문 상담Ai</title>
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
        /* 상단 영역 높이를 140px로 늘려 넉넉한 간격 확보 */
        #chat-header {{
          position: absolute;
          top: 0;
          left: 0; right: 0;
          height: 140px;
          background-color: rgba(255, 255, 255, 0.6);
          backdrop-filter: blur(6px);
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 0.5rem 1rem;
          border-bottom: 1px solid rgba(255,255,255,0.3);
        }}
        /* 채팅 메시지 영역 시작점을 140px로 변경 */
        #chat-messages {{
          position: absolute;
          top: 140px;
          bottom: 70px;
          left: 0; right: 0;
          overflow-y: auto;
          padding: 1rem;
        }}
        /* 하단 입력 영역에서 좌우가 잘리지 않도록 left/right에 여백을 줌 */
        #chat-input {{
          position: absolute;
          bottom: 0;
          left: 0.5rem;
          right: 0.5rem;
          height: 70px;
          background-color: rgba(255, 255, 255, 0.6);
          backdrop-filter: blur(6px);
          display: flex;
          align-items: center;
          padding: 0 1rem;
          border-top: 1px solid rgba(255,255,255,0.3);
        }}
        /* 모바일에서 줄바꿈 간격 최소화 */
        .mobile-break {{
          line-height: 1;
          margin: 0;
        }}
      </style>
    </head>
    <body class="h-full flex items-center justify-center">
      <div class="chat-container">
        <!-- 상단 영역: 로고 + 안내문구 + 리셋버튼 -->
        <div id="chat-header">
          <!-- 로고+리셋 버튼 한 줄 배치 -->
          <div class="flex items-center justify-between w-full">
            <!-- 로고(이미지): 모바일은 h-6, PC는 h-10 -->
            <img 
              src="https://raw.githubusercontent.com/buddhai/hyundai/master/logo01.png"
              alt="현대불교신문 Ai상담봇 해심이 로고"
              class="h-7 md:h-10"
            />
            <!-- 새로고침 버튼 -->
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
          <!-- 안내 문구 -->
          <div class="text-gray-500 text-xs text-center mt-2">
            AI상담봇은 데이터 기반의 정보를 제공하므로
            <span class="md:hidden mobile-break"><br></span>
            일부 부정확한 답변이 제시될 수 있습니다.
          </div>
        </div>

        <!-- 채팅 메시지 영역 -->
        <div id="chat-messages">
          {messages_html}
        </div>

        <!-- 하단 입력창 -->
        <div id="chat-input">
          <form id="chat-form"
                hx-post="/message?phase=init"
                hx-target="#chat-messages"
                hx-swap="beforeend"
                onsubmit="setTimeout(() => this.reset(), 0)"
                class="flex w-full">
            <!-- 왼쪽만 둥글게 -->
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
            <!-- 오른쪽만 둥글게 + 크게 보이도록 패딩 조정 -->
            <button type="submit"
                    class="
                      bg-gradient-to-r from-gray-900 to-gray-700
                      hover:from-gray-700 hover:to-gray-900
                      text-white
                      py-3 px-5
                      rounded-r-full
                      border-0
                      shadow-md
                      hover:shadow-xl
                      transition-all
                      duration-300
                      flex items-center
                    ">
              >
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
        "시스템 안내: 당신은 한마음선원 현대불교신문의 Ai입니다. "
        "항상 친근하고 예의바르게, 그 신문의 명예와 위상을 높이는 답변을 제공하며, "
        "사용자의 질문에 대해 상세하고 정확하게, 그리고 매우 호의적으로 응답합니다."
    )
    initial_message = (
        "모든 답은 당신 안에 있습니다. 저는 그 여정을 함께하는\n"
        "현대불교신문 Ai상담봇 해심이입니다.\n"
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
        # 1) Google 검색 그라운딩 도구 구성하여 사실 기반 답변 생성
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
        
        # 2) 최종 답변으로 부드럽게 재작성
        rephrase_prompt = (
            "Please rewrite the following answer in a friendly and conversational tone in Korean. "
            "Provide a single final answer that is balanced in length—not too brief and not overly detailed—similar to a normal chatbot response.\n\n"
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
    
    # 대화 기록에 Ai 응답 업데이트
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
