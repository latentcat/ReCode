"""FastAPI 服务 - ReCode+ WebSocket 和 REST API"""

from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 导入 ReCode 的 AsyncLLM
import sys
from pathlib import Path
recode_path = Path(__file__).parent.parent
sys.path.insert(0, str(recode_path))

from utils.llm import AsyncLLM
from recode_plus.mediator import MediatorAgent
from recode_plus.visualizer import Visualizer


# 会话管理
sessions: dict[str, MediatorAgent] = {}
visualizers: dict[str, Visualizer] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    print("🚀 ReCode+ 服务启动")
    yield
    print("👋 ReCode+ 服务关闭")


app = FastAPI(
    title="ReCode+ API",
    description="融合 ReCode、Pydantic AI 和人机协作的 Agent 框架",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ Pydantic 模型 ============

class CreateSessionRequest(BaseModel):
    """创建会话请求"""
    session_id: str
    project_id: str = "default"
    llm_profile: str = "default"


class ApprovalRequest(BaseModel):
    """审批请求"""
    session_id: str
    tool_call_id: str
    approved: bool


class UserMessage(BaseModel):
    """用户消息"""
    content: str


# ============ REST API ============

@app.get("/")
async def root():
    """根路径"""
    return {
        "name": "ReCode+ API",
        "version": "0.1.0",
        "websocket": "/ws/{session_id}",
        "docs": "/docs",
    }


@app.post("/sessions")
async def create_session(request: CreateSessionRequest):
    """创建新会话"""
    if request.session_id in sessions:
        raise HTTPException(status_code=400, detail="会话已存在")
    
    # 创建 LLM
    llm = AsyncLLM(request.llm_profile)
    
    # 创建 MediatorAgent
    mediator = MediatorAgent(llm, request.project_id)
    sessions[request.session_id] = mediator
    
    # 创建 Visualizer
    visualizer = Visualizer(mediator.tree)
    visualizers[request.session_id] = visualizer
    
    return {
        "session_id": request.session_id,
        "status": "created",
    }


@app.get("/sessions/{session_id}/tree")
async def get_tree(session_id: str):
    """获取节点树状态"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    mediator = sessions[session_id]
    return mediator.get_tree_snapshot()


@app.get("/sessions/{session_id}/visualize")
async def visualize_tree(session_id: str):
    """获取可视化数据"""
    if session_id not in visualizers:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    visualizer = visualizers[session_id]
    return visualizer.render_tree_json()


@app.post("/sessions/{session_id}/approve")
async def approve_tool(session_id: str, request: ApprovalRequest):
    """批准工具调用"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    mediator = sessions[session_id]
    
    if request.approved:
        success = await mediator.approve_tool(request.tool_call_id)
    else:
        success = await mediator.reject_tool(request.tool_call_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="工具调用不存在或已处理")
    
    return {"status": "approved" if request.approved else "rejected"}


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除会话"""
    if session_id in sessions:
        del sessions[session_id]
    if session_id in visualizers:
        del visualizers[session_id]
    
    return {"status": "deleted"}


# ============ WebSocket ============

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket 连接"""
    await websocket.accept()
    
    # 检查会话是否存在
    if session_id not in sessions:
        await websocket.send_json({
            "type": "error",
            "content": "会话不存在，请先创建会话"
        })
        await websocket.close()
        return
    
    mediator = sessions[session_id]
    visualizer = visualizers.get(session_id)
    
    # 订阅可视化更新
    if visualizer:
        visualizer.subscribe(websocket)
    
    try:
        # 发送欢迎消息
        await websocket.send_json({
            "type": "connected",
            "content": {
                "session_id": session_id,
                "message": "连接成功！发送消息开始对话。"
            }
        })
        
        while True:
            # 接收用户消息
            data = await websocket.receive_json()
            
            message_type = data.get("type")
            
            if message_type == "user_message":
                # 用户消息
                user_message = data.get("content", "")
                
                # 流式处理
                async for event in mediator.chat_stream(user_message):
                    await websocket.send_json(event.to_dict())
            
            elif message_type == "approval_response":
                # 审批响应
                tool_call_id = data.get("tool_call_id")
                approved = data.get("approved", False)
                
                if approved:
                    await mediator.approve_tool(tool_call_id)
                else:
                    await mediator.reject_tool(tool_call_id)
                
                await websocket.send_json({
                    "type": "approval_processed",
                    "content": {
                        "tool_call_id": tool_call_id,
                        "approved": approved,
                    }
                })
            
            elif message_type == "ping":
                # 心跳
                await websocket.send_json({"type": "pong"})
            
            else:
                await websocket.send_json({
                    "type": "error",
                    "content": f"未知消息类型: {message_type}"
                })
    
    except WebSocketDisconnect:
        print(f"WebSocket 断开: {session_id}")
        if visualizer:
            visualizer.unsubscribe(websocket)
    
    except Exception as e:
        print(f"WebSocket 错误: {e}")
        await websocket.send_json({
            "type": "error",
            "content": str(e)
        })
        await websocket.close()


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )

