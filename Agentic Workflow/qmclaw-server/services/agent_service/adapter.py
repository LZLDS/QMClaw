# SPDX-FileCopyrightText: Copyright (c) 2026 QMClaw. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Agent Service 适配器

将现有的自定义 Tool 类适配到统一的 ToolRegistry。
通过 HTTP 调用 quantum_service 执行实验，实现与设备的解耦。
"""

import json
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

from ..common.quantum_tools import (
    GetQubitParamsTool,
    GetQubitsTool,
    ListExperimentsTool,
    RunCodeTool,
    RunExperimentTool,
    ListHistoryTool,
    ToolRegistry,
    ToolResult,
)


# quantum_service 地址
QUANTUM_SERVICE_URL = "http://localhost:3003"


def _http_call(url: str, data: dict = None, method: str = "GET") -> dict:
    """发送 HTTP 请求到 quantum_service"""
    try:
        if method == "GET":
            req = urllib.request.Request(url)
        else:
            payload = json.dumps(data or {}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method=method
            )

        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def setup_agent_tools(
    registry: ToolRegistry,
    quantum_service_url: str = QUANTUM_SERVICE_URL
) -> ToolRegistry:
    """设置 agent_service 的工具到注册中心

    通过 HTTP 调用 quantum_service 执行实验，实现与设备的解耦。

    Args:
        registry: 工具注册中心实例
        quantum_service_url: quantum_service 地址

    Returns:
        注册了工具的 ToolRegistry 实例
    """

    def is_connected() -> bool:
        """检查 quantum_service 是否可用"""
        result = _http_call(f"{quantum_service_url}/health")
        return result.get("labrad_connected", False) or result.get("status") == "healthy"

    def get_qubits() -> List[Dict[str, Any]]:
        """获取量子比特列表"""
        result = _http_call(f"{quantum_service_url}/qubits")
        if "qubits" in result:
            return result["qubits"]
        return []

    def get_qubit_params(name: str) -> Optional[Dict[str, Any]]:
        """获取量子比特参数"""
        result = _http_call(
            f"{quantum_service_url}/qubit/params",
            {"name": name},
            "POST"
        )
        if "params" in result:
            return result["params"]
        return None

    def list_experiments() -> List[Dict[str, str]]:
        """列出实验"""
        result = _http_call(f"{quantum_service_url}/experiments")
        if "experiments" in result:
            return result["experiments"]
        return []

    def execute_code(code: str) -> Dict[str, Any]:
        """执行代码"""
        result = _http_call(
            f"{quantum_service_url}/execute",
            {"code": code},
            "POST"
        )
        if result.get("status") == "success":
            return result
        return {"error": result.get("error", "Unknown error")}

    def run_experiment(name: str, params: Dict, notes: str = "") -> Dict[str, Any]:
        """执行命名实验"""
        # 构建代码
        func_name = f"sq.{name}"
        param_str = ", ".join(f"{k}={repr(v)}" for k, v in params.items())
        code = f"{func_name}({param_str})"

        result = _http_call(
            f"{quantum_service_url}/execute",
            {"code": code},
            "POST"
        )

        # 包装结果
        return {
            "id": result.get("task_id", ""),
            "status": result.get("status", "failed"),
            "results": result.get("result", {}),
            "error": result.get("error"),
        }

    def list_history(last_n: int, type: str = None) -> List[Dict[str, Any]]:
        """查询实验历史"""
        # 通过 quantum_service 获取
        return []

    # 注册工具
    registry.register_tool(GetQubitsTool(get_qubits))
    registry.register_tool(GetQubitParamsTool(get_qubit_params, get_qubits))
    registry.register_tool(ListExperimentsTool(list_experiments))
    registry.register_tool(RunCodeTool(execute_code, is_connected))
    registry.register_tool(RunExperimentTool(
        lambda name, params: run_experiment(name, params),
        execute_code,
        is_connected=is_connected
    ))
    registry.register_tool(ListHistoryTool(list_history))

    return registry


class AgentServiceAdapter:
    """Agent Service 适配器

    将 agent_service 工具适配到统一的 ToolRegistry。
    通过 HTTP 调用 quantum_service。
    """

    def __init__(self, quantum_service_url: str = QUANTUM_SERVICE_URL):
        """
        Args:
            quantum_service_url: quantum_service 地址
        """
        self._quantum_service_url = quantum_service_url
        self._registry = ToolRegistry()
        self._setup_tools()

    def _setup_tools(self):
        """设置工具"""
        setup_agent_tools(self._registry, self._quantum_service_url)

    def set_quantum_service_url(self, url: str):
        """设置 quantum_service 地址"""
        self._quantum_service_url = url
        self._registry = ToolRegistry()
        self._setup_tools()

    def execute_tool(self, name: str, args: Dict[str, Any]) -> ToolResult:
        """执行工具"""
        return self._registry.execute(name, args)

    def get_tools(self) -> List[Dict[str, Any]]:
        """获取工具定义列表"""
        return self._registry.get_definitions()

    def get_registry(self) -> ToolRegistry:
        """获取注册中心"""
        return self._registry
