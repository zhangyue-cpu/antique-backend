import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn
import aiohttp
import asyncio
import random
import uuid
import gc
from datetime import datetime, timedelta
from typing import Optional, Dict, List

# 加载 .env 文件中的环境变量
load_dotenv()

# 百练 API 配置
BAICHUAN_API_KEY = os.getenv("BAICHUAN_API_KEY")

if not BAICHUAN_API_KEY:
    print("❌ 未找到百练 API 密钥，请在 .env 文件中设置 BAICHUAN_API_KEY")
else:
    print("✅ 百练 API 密钥加载成功")

# 只使用百练 API
PROXIES = [
    {
        "url": "https://api.baichuan-ai.com/v1/chat/completions",
        "headers": {
            "Authorization": f"Bearer {BAICHUAN_API_KEY}",
            "Content-Type": "application/json"
        }
    }
]

SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))
DEBUG_MODE = os.getenv("DEBUG_MODE", "False").lower() == "true"

print("🤖 AI模式: 百练官方 API")
print("🔗 模型: Baichuan3-Turbo")

# 请求数据模型
class ChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = None

class ChatResponse(BaseModel):
    success: bool
    response: str
    source: Optional[str] = None

# 会话管理类
class UserSession:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.messages: List[dict] = []
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
    
    def add_message(self, role: str, content: str):
        """添加消息到会话历史"""
        self.messages.append({"role": role, "content": content})
        self.last_activity = datetime.now()
        
        # 保持最近6条消息的上下文（3轮对话）
        if len(self.messages) > 6:
            self.messages = self.messages[-6:]

# 全局会话存储
user_sessions: Dict[str, UserSession] = {}

# 服务器启动时间
start_time = datetime.now()

# 创建 FastAPI 应用
app = FastAPI(
    title="文鉴通助手API",
    description="基于FastAPI的专业文物鉴定问答助手",
    version="1.0.0"
)

# CORS 配置 - 允许前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "*"  # 开发环境允许所有来源
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 根路径返回前端页面
@app.get("/")
async def read_index():
    return FileResponse("../frontend/index.html")

# 健康检查
@app.get("/api/health")
async def health_check():
    return {
        "status": "OK", 
        "message": "FastAPI 文鉴通助手服务运行正常",
        "framework": "FastAPI",
        "version": "1.0.0",
        "ai_provider": "百练 Baichuan"
    }

# API 状态检查
@app.get("/api/ai-status")
async def ai_status():
    """检查百练 API 状态"""
    if not BAICHUAN_API_KEY:
        return {
            "status": "error",
            "message": "百练 API 密钥未配置",
            "provider": "百练 Baichuan"
        }
    
    test_message = "你好，请简单回复'测试成功'"
    
    try:
        proxy = PROXIES[0]  # 百练 API
        headers = proxy["headers"]
        
        payload = {
            "model": "Baichuan3-Turbo",
            "messages": [{"role": "user", "content": test_message}],
            "max_tokens": 50,
            "temperature": 0.7
        }
        
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(proxy["url"], headers=headers, json=payload) as response:
                if response.status == 200:
                    return {
                        "status": "connected",
                        "message": "百练 API 连接正常",
                        "provider": "百练 Baichuan",
                        "model": "Baichuan3-Turbo"
                    }
                else:
                    error_text = await response.text()
                    return {
                        "status": "error", 
                        "message": f"百练 API 响应错误: {response.status}",
                        "details": error_text[:200],
                        "provider": "百练 Baichuan"
                    }
                    
    except Exception as e:
        return {
            "status": "error",
            "message": f"百练 API 连接失败: {str(e)}",
            "provider": "百练 Baichuan"
        }

# 系统健康检查
@app.get("/api/system/health")
async def system_health():
    """系统健康检查端点"""
    try:
        # 计算会话统计
        now = datetime.now()
        active_sessions = len(user_sessions)
        recent_sessions = sum(1 for s in user_sessions.values() 
                             if now - s.last_activity < timedelta(minutes=30))
        
        return {
            "status": "healthy",
            "timestamp": now.isoformat(),
            "active_sessions": active_sessions,
            "recent_sessions": recent_sessions,
            "server_uptime": str(now - start_time).split('.')[0],  # 去除微秒
            "ai_provider": "百练 Baichuan",
            "features": ["真正AI回复", "对话记忆", "会话清理", "系统监控"]
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 调试信息
@app.get("/api/debug")
async def debug_info():
    """调试信息接口"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_sessions": len(user_sessions),
        "ai_provider": "百练 Baichuan",
        "api_configured": bool(BAICHUAN_API_KEY)
    }

# 测试接口
@app.get("/api/test")
async def test_endpoint():
    return {
        "success": True, 
        "message": "FastAPI 文鉴通助手后端服务测试成功",
        "ai_provider": "百练 Baichuan"
    }

async def get_ai_response_with_memory(message: str, message_history: List[dict]) -> str:
    """调用百练 API - 带对话记忆"""
    
    if not BAICHUAN_API_KEY:
        return None
    
    # 构建带历史的消息 - 修改为文物鉴定主题
    messages = [
        {
            "role": "system",
            "content": """你是一个专业、严谨、知识渊博的文物鉴定助手-文鉴通助手。你具有以下特点：

文物知识领域：
1. 文物历史背景和年代鉴定专业知识
2. 各类文物材质、工艺技术分析（陶瓷、书画、青铜器、玉器等）
3. 文物真伪鉴别要点和方法
4. 文物收藏价值和市场行情分析
5. 文物保护与修复专业知识
6. 相关法律法规和文物政策

专业服务风格：
1. 回答要专业严谨，基于历史事实和专业知识
2. 对于需要实物鉴定的情况，明确说明局限性并建议寻求专业机构
3. 适当使用专业术语但要解释清楚
4. 保持客观中立，不夸大文物价值
5. 强调文物保护的重要性

注意事项：
- 如果用户问非文物相关问题，可以友好引导回文物话题
- 对于价值评估要谨慎，强调市场波动性和专业鉴定必要性
- 涉及法律法规要准确引用

请用中文回复，保持专业、严谨、有帮助的态度。"""
        }
    ]
    
    # 添加历史消息
    messages.extend(message_history)
    
    # 添加当前消息
    messages.append({"role": "user", "content": message})
    
    payload = {
        "model": "Baichuan3-Turbo",
        "messages": messages,
        "max_tokens": 1500,
        "temperature": 0.7,
        "stream": False
    }
    
    try:
        proxy = PROXIES[0]  # 百练 API
        print(f"🔗 使用百练 API")
        
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(proxy["url"], headers=proxy["headers"], json=payload) as response:
                
                if response.status == 200:
                    data = await response.json()
                    print(f"🔍 百练 API 原始响应: {data}")  # 打印完整响应用于调试
                    
                    # 多种可能的响应格式处理
                    ai_response = None
                    
                    # 1. 标准 OpenAI 格式
                    if "choices" in data and len(data["choices"]) > 0:
                        choice = data["choices"][0]
                        if "message" in choice and "content" in choice["message"]:
                            ai_response = choice["message"]["content"]
                        elif "text" in choice:
                            ai_response = choice["text"]
                    
                    # 2. 直接 content 字段
                    elif "content" in data:
                        ai_response = data["content"]
                    
                    # 3. 其他可能的格式
                    elif "data" in data:
                        if "choices" in data["data"] and data["data"]["choices"]:
                            choice = data["data"]["choices"][0]
                            if "message" in choice and "content" in choice["message"]:
                                ai_response = choice["message"]["content"]
                    
                    # 4. 输出字段格式
                    elif "output" in data:
                        if isinstance(data["output"], str):
                            ai_response = data["output"]
                        elif "text" in data["output"]:
                            ai_response = data["output"]["text"]
                    
                    if ai_response:
                        print(f"✅ 百练 API 调用成功")
                        print(f"🤖 AI回复: {ai_response[:100]}...")  # 只显示前100字符
                        return ai_response
                    else:
                        print(f"❌ 百练响应格式无法解析: {data}")
                        # 返回原始数据用于调试
                        return f"响应格式不识别，原始数据: {str(data)[:300]}"
                
                else:
                    error_text = await response.text()
                    print(f"❌ 百练 API 错误: {response.status} - {error_text}")
                    return None
                    
    except asyncio.TimeoutError:
        print(f"⏰ 百练 API 超时")
        return None
    except Exception as e:
        print(f"❌ 百练 API 异常: {str(e)}")
        return None

def get_smart_response(message: str, original_message: str) -> str:
    """智能回复函数 - 百练 API 不可用时使用"""
    user_msg = message.lower().strip()
    
    # 问候类
    if any(word in user_msg for word in ['你好', '您好', '嗨', 'hello', 'hi']):
        return random.choice([
            "您好！🏺 我是文鉴通助手，专注于文物鉴定和收藏知识。有什么文物相关的问题吗？",
            "欢迎！🔍 我是您的文物鉴定顾问，可以帮您了解各类文物的鉴别方法和历史背景。",
            "您好！📜 文鉴通助手为您服务，我们专注于文物鉴定、收藏和保护知识咨询。"
        ])
    
    # 文物相关关键词
    antique_keywords = {
        '陶瓷': "陶瓷鉴定需要观察胎质、釉色、纹饰等特征。不同朝代有独特的工艺特点，比如唐三彩、宋瓷、明清青花等各有特色。",
        '青铜器': "青铜器鉴定要看器型、纹饰、铭文和锈色。真品青铜器的锈色自然牢固，器型符合时代特征。",
        '书画': "书画鉴定涉及笔墨风格、题跋印章、纸张材质等多方面。需要对比画家不同时期的作品特征。",
        '玉器': "玉器鉴定要看玉质、工艺、沁色和包浆。不同历史时期的玉器在造型和雕工上各有特点。",
        '鉴定': "文物鉴定是一门专业学问，需要综合考虑历史、艺术、科技等多方面因素。建议重要文物找专业机构鉴定。",
        '收藏': "文物收藏要注意真伪鉴别、保存条件和法律法规。建议从基础学起，逐步积累经验。"
    }
    for keyword, response in antique_keywords.items():
        if keyword in user_msg:
            return response
    
    # 默认回复
    return f"🏺 关于『{original_message}』，我作为文物鉴定助手可以帮您：\n\n• 文物年代和背景知识\n• 材质工艺鉴别要点\n• 真伪辨别方法\n• 收藏保养建议\n• 相关法律法规\n\n请提供更具体的信息，我会尽力为您解答。对于重要文物，建议咨询专业鉴定机构."

# 修改后的聊天接口 - 支持对话记忆
@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    try:
        # 使用前端传递的 user_id 或生成新的
        user_id = request.user_id or str(uuid.uuid4())[:8]
        
        if user_id not in user_sessions:
            user_sessions[user_id] = UserSession(user_id)
        
        session = user_sessions[user_id]
        
        print(f"🏺 用户 {user_id} 发送消息: {request.message}")
        print(f"📝 会话历史: {len(session.messages)} 条消息")
        
        # 首先尝试百练 API 回复
        ai_response = await get_ai_response_with_memory(request.message, session.messages)
        
        if ai_response:
            # 保存用户消息和AI回复到会话历史
            session.add_message("user", request.message)
            session.add_message("assistant", ai_response)
            
            print(f"🤖 百练回复: {ai_response}")
            return ChatResponse(
                success=True,
                response=ai_response,
                source="baichuan"
            )
        
        # 百练 API 不可用时使用智能规则回复
        rule_response = get_smart_response(request.message.lower(), request.message)
        
        # 保存到会话历史
        session.add_message("user", request.message)
        session.add_message("assistant", rule_response)
        
        print(f"🤖 规则回复: {rule_response}")
        
        return ChatResponse(
            success=True,
            response=rule_response,
            source="rule_based"
        )
        
    except Exception as e:
        print(f"❌ 处理错误: {e}")
        return ChatResponse(
            success=False,
            response="抱歉，服务暂时不可用，请稍后重试"
        )

# 会话清理后台任务
async def cleanup_sessions():
    """定期清理过期会话"""
    while True:
        await asyncio.sleep(300)  # 5分钟清理一次
        try:
            now = datetime.now()
            expired_users = [
                user_id for user_id, session in user_sessions.items()
                if now - session.last_activity > timedelta(hours=1)  # 1小时无活动
            ]
            
            if expired_users:
                for user_id in expired_users:
                    del user_sessions[user_id]
                print(f"🧹 清理了 {len(expired_users)} 个过期会话")
                
            # 触发垃圾回收
            gc.collect()
            
        except Exception as e:
            print(f"清理会话错误: {e}")

# 启动清理任务
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_sessions())
    print("🔄 会话清理任务已启动")

# 静态文件服务放在最后，避免覆盖API路由
app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")

# 启动服务器
if __name__ == "__main__":
    print("🚀 启动 FastAPI 文鉴通助手服务器...")
    print("📍 文档地址: http://localhost:8000/docs")
    print("🔍 健康检查: http://localhost:8000/api/health")
    print("🤖 AI状态检查: http://localhost:8000/api/ai-status")
    print("🖥️  系统监控: http://localhost:8000/api/system/health")
    print("💬 聊天接口: http://localhost:8000/api/chat")
    print("🤖 AI模式: 百练官方 API")
    print("🔗 模型: Baichuan3-Turbo")
    print("🔄 功能: 真正AI回复 | 对话记忆 | 自动清理 | 系统监控")
    print("=" * 50)
    
    uvicorn.run(
        "main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=DEBUG_MODE
    )