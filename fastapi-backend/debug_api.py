import aiohttp
import asyncio
import json

async def debug_deepseek():
    API_KEY = "sk-6391f3e0e01e426ca56771c3a5152c86"
    API_URL = "https://api.deepseek.com/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "user",
                "content": "Hello"
            }
        ],
        "max_tokens": 50
    }
    
    print("🔍 开始 DeepSeek API 调试...")
    print(f"🔑 API Key: {API_KEY[:15]}...")
    print(f"🌐 API URL: {API_URL}")
    
    try:
        async with aiohttp.ClientSession() as session:
            print("📡 发送请求...")
            async with session.post(API_URL, headers=headers, json=payload, timeout=30) as response:
                print(f"📊 响应状态: {response.status}")
                print(f"📋 响应头: {dict(response.headers)}")
                
                response_text = await response.text()
                print(f"📝 响应内容: {response_text}")
                
                if response.status == 200:
                    data = json.loads(response_text)
                    print("🎉 API 调用成功!")
                    print(f"🤖 AI回复: {data['choices'][0]['message']['content']}")
                else:
                    print("❌ API 调用失败")
                    
    except Exception as e:
        print(f"💥 异常: {e}")

if __name__ == "__main__":
    asyncio.run(debug_deepseek())