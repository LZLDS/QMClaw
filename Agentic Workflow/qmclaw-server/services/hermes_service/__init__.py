"""
services/hermes_service/ - Hermes Agent 微服务

提供 Hermes Agent 功能：
- AI 对话
- 工具调用
- SSE 流式输出
- 会话管理
"""

from .server import HermesService, main

__all__ = ["HermesService", "main"]
