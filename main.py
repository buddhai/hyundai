import os
import asyncio
from fastapi import FastAPI, Request, Form
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

# 환경 변수 로드 및 API 키 설정
load_dotenv()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Gemini API 클라이언트 초기화 (공식 가이드 방식)
from google import genai
from google.genai import types
client = genai.Client(api_key=GEMINI_API_KEY)

app = FastAPI()

@app.post("/stream", response_class=StreamingResponse)
async def stream_response(request: Request, message: str = Form(...)):
    # 사용자의 메시지를 프롬프트로 사용 (필요시 multi-turn 대화 기록을 추가할 수 있음)
    prompt = message
    
    # 스트리밍 설정: 예시로 Google 검색 그라운딩 도구 포함 (원하는 도구를 추가 가능)
    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        response_modalities=["TEXT"]
    )
    
    # 스트리밍 메서드 호출: streamGenerateContent는 응답 청크들을 순차적으로 반환합니다.
    stream_iterator = client.models.streamGenerateContent(
        model='gemini-2.0-flash',
        contents=prompt,
        config=config
    )
    
    async def stream_generator():
        # stream_iterator는 동기 이터레이터일 수 있으므로, to_thread를 사용하거나 직접 순회합니다.
        # 여기서는 간단히 for 루프로 순회하며 각 청크의 텍스트를 전송합니다.
        for chunk in stream_iterator:
            # 각 청크의 응답 텍스트를 클라이언트에 전송 (필요시 후처리 가능)
            yield chunk.text + "\n"
            # 다른 작업으로 제어권을 넘김
            await asyncio.sleep(0)
    
    return StreamingResponse(stream_generator(), media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
