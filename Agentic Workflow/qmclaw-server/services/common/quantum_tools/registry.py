# SPDX-FileCopyrightText: Copyright (c) 2026 QMClaw. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
统一工具注册中心

提供工具注册、发现和执行的统一接口。
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

from .base import QuantumTool, ToolResult, ToolSchema
from .errors import ErrorCode, QMClawError


class ToolRegistry:
    """统一工具注册中心

    单例模式，用于注册和管理所有量子测控工具。
    提供统一的工具发现和执行接口。

    使用示例:
        registry = ToolRegistry.get_instance()
        registry.register_tool(MyTool())
        tools = registry.get_definitions()
        result = registry.execute("my_tool", {"arg1": "value"})
    """

    _instance: Optional['ToolRegistry'] = None

    def __init__(self):
        self._tools: Dict[str, QuantumTool] = {}
        self._execution_stats: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def get_instance(cls) -> 'ToolRegistry':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """重置单例实例（用于测试）"""
        cls._instance = None

    def register_tool(self, tool: QuantumTool) -> None:
        """注册工具

        Args:
            tool: 量子工具实例
        """
        if not isinstance(tool, QuantumTool):
            raise TypeError(f"Tool must be a QuantumTool instance, got {type(tool)}")

        self._tools[tool.name] = tool

    def unregister_tool(self, name: str) -> bool:
        """注销工具

        Args:
            name: 工具名称

        Returns:
            True if tool was removed, False if not found
        """
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get_tool(self, name: str) -> Optional[QuantumTool]:
        """获取工具实例

        Args:
            name: 工具名称

        Returns:
            工具实例，如果不存在返回 None
        """
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        """检查工具是否存在"""
        return name in self._tools

    def list_tools(self) -> List[str]:
        """列出所有已注册的工具名称"""
        return list(self._tools.keys())

    def get_definitions(self) -> List[Dict[str, Any]]:
        """获取所有工具的 OpenAI function calling 定义

        Returns:
            工具定义列表，每个元素包含 type 和 function
        """
        return [tool.get_openai_definition() for tool in self._tools.values()]

    def get_schema(self, name: str) -> Optional[Dict[str, Any]]:
        """获取工具的 schema

        Args:
            name: 工具名称

        Returns:
            工具 schema 字典，如果不存在返回 None
        """
        tool = self._tools.get(name)
        if tool is None:
            return None
        return tool.schema.to_openai_schema()

    def execute(self, name: str, args: Dict[str, Any]) -> ToolResult:
        """执行工具

        Args:
            name: 工具名称
            args: 工具参数

        Returns:
            ToolResult 执行结果
        """
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult.err(
                f"Tool '{name}' not found",
                error_code=ErrorCode.NOT_FOUND.value,
                available_tools=self.list_tools(),
                hint="Call list_tools() to see available tools"
            )

        # 记录开始时间
        start_time = datetime.now(timezone.utc)

        try:
            result = tool.execute(**args)

            # 记录执行统计
            self._record_execution(
                name,
                success=result.success,
                duration=(datetime.now(timezone.utc) - start_time).total_seconds()
            )

            return result

        except QMClawError as e:
            self._record_execution(
                name,
                success=False,
                duration=(datetime.now(timezone.utc) - start_time).total_seconds(),
                error=str(e)
            )
            return ToolResult.err(
                error=e.message,
                error_code=e.error_code.value,
                **e.details
            )

        except Exception as e:
            self._record_execution(
                name,
                success=False,
                duration=(datetime.now(timezone.utc) - start_time).total_seconds(),
                error=str(e)
            )
            return ToolResult.err(
                error=str(e),
                error_code=ErrorCode.INTERNAL_ERROR.value,
                tool=name
            )

    def _record_execution(
        self,
        tool_name: str,
        success: bool,
        duration: float,
        error: Optional[str] = None
    ) -> None:
        """记录工具执行统计"""
        if tool_name not in self._execution_stats:
            self._execution_stats[tool_name] = {
                "total_calls": 0,
                "successful_calls": 0,
                "failed_calls": 0,
                "total_duration": 0.0,
                "last_called": None,
                "last_error": None,
            }

        stats = self._execution_stats[tool_name]
        stats["total_calls"] += 1
        if success:
            stats["successful_calls"] += 1
        else:
            stats["failed_calls"] += 1
        stats["total_duration"] += duration
        stats["last_called"] = datetime.now(timezone.utc).isoformat()
        if error:
            stats["last_error"] = error

    def get_stats(self, tool_name: Optional[str] = None) -> Dict[str, Any]:
        """获取工具执行统计

        Args:
            tool_name: 工具名称，如果为 None 则返回所有工具的统计
        """
        if tool_name:
            stats = self._execution_stats.get(tool_name, {})
            if stats:
                stats = dict(stats)
                stats["success_rate"] = (
                    stats["successful_calls"] / stats["total_calls"]
                    if stats["total_calls"] > 0 else 0
                )
                stats["avg_duration"] = (
                    stats["total_duration"] / stats["total_calls"]
                    if stats["total_calls"] > 0 else 0
                )
            return stats
        else:
            return {
                name: self.get_stats(name)
                for name in self._execution_stats.keys()
            }

    def get_info(self) -> Dict[str, Any]:
        """获取注册中心信息"""
        return {
            "tool_count": len(self._tools),
            "tools": self.list_tools(),
            "stats": self.get_stats(),
        }

    def create_api_executor(self) -> 'APIExecutor':
        """创建 API 执行器

        返回的执行器可以将请求路由到对应的工具。
        """
        return APIExecutor(self)


class APIExecutor:
    """API 执行器

    用于处理 API 请求，将请求路由到对应的工具。
    """

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def execute_tool(self, name: str, args: Dict[str, Any], request_id: Optional[str] = None) -> Dict[str, Any]:
        """执行工具并返回 API 响应格式

        Args:
            name: 工具名称
            args: 工具参数
            request_id: 请求 ID

        Returns:
            API 响应格式的字典
        """
        if request_id is None:
            request_id = f"req_{uuid.uuid4().hex[:12]}"

        result = self.registry.execute(name, args)
        return result.to_api_response(request_id=request_id)

    def list_routes(self) -> List[Dict[str, Any]]:
        """列出所有可用的 API 路由"""
        routes = []
        for tool_name in self.registry.list_tools():
            schema = self.registry.get_schema(tool_name)
            if schema:
                routes.append({
                    "path": f"/api/v1/tools/{tool_name}",
                    "method": "POST",
                    "tool": tool_name,
                    "schema": schema,
                })
        return routes


def create_tool_from_function(
    name: str,
    description: str,
    func: Callable,
    param_schemas: Dict[str, Any]
) -> QuantumTool:
    """从普通函数创建量子工具

    这是一个便捷函数，用于快速将普通函数包装为 QuantumTool。

    Args:
        name: 工具名称
        description: 工具描述
        func: 执行函数
        param_schemas: 参数 schema 字典

    Returns:
        QuantumTool 实例
    """
    from .base import ParameterSchema, ToolSchema

    class FunctionTool(QuantumTool):
        def __init__(self, fn):
            self._fn = fn
            self._name = name
            self._description = description
            self._param_schemas = {
                k: ParameterSchema(**v) if isinstance(k, dict) else k
                for k, v in param_schemas.items()
            }

        @property
        def name(self) -> str:
            return self._name

        @property
        def description(self) -> str:
            return self._description

        @property
        def schema(self) -> ToolSchema:
            return ToolSchema(
                name=self._name,
                description=self._description,
                parameters=self._param_schemas,
            )

        def execute(self, **kwargs) -> ToolResult:
            try:
                result = self._fn(**kwargs)
                return ToolResult.ok(result)
            except Exception as e:
                return ToolResult.err(str(e))

    return FunctionTool(func)
