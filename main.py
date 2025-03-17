def render_chat_interface(conversation) -> str:
    messages_html = ""
    for msg in conversation["messages"]:
        # 시스템 메시지는 출력하지 않음
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
              py-2 px-4 sm:py-1 sm:px-2
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
                      py-2 px-4 sm:py-1 sm:px-2
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
        <!-- 추가 안내 문구 (회색, 작게) -->
        <div class="absolute bottom-2 w-full text-center text-gray-500 text-xs">
          현대불교신문 AI는 실수를 할 수 있습니다. 중요한 정보는 재차 확인하세요.
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
