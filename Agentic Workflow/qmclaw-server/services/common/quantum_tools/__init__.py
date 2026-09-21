# SPDX-FileCopyrightText: Copyright (c) 2026 QMClaw. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
统一量子测控工具集

提供一致的量子测控工具定义、注册和执行接口，供 agent_service、qca_service、hermes_service 使用。

核心组件:
- ToolResult: 统一返回格式
- QuantumTool: 工具基类
- ToolRegistry: 工具注册中心
- 核心工具实现

使用示例:
    from common.quantum_tools import ToolRegistry, ToolResult

    registry = ToolRegistry.get_instance()
    tools = registry.get_definitions()
    result = registry.execute("run_experiment", {"code": "sq.iqraw()"})
"""

from .base import (
    ToolResult,
    ToolSchema,
    ParameterSchema,
    ReturnSchema,
    QuantumTool,
)
from .registry import ToolRegistry
from .errors import (
    ErrorCode,
    QMClawError,
    ValidationError,
    NotFoundError,
    ExperimentNotFoundError,
    QubitNotFoundError,
    TimeoutError,
    LabRADError,
    ExecutionError,
)
from .execution import (
    RunExperimentTool,
    RunCodeTool,
    ListExperimentsTool,
    GetExperimentSchemaTool,
)
from .qubit import (
    GetQubitsTool,
    GetQubitParamsTool,
    SetQubitParamsTool,
)
from .data import (
    ListHistoryTool,
    GetExperimentDataTool,
    GetArrayDataTool,
    GetStatsTool,
    ListArraysTool,
)

__all__ = [
    # 基础类
    "ToolResult",
    "ToolSchema",
    "ParameterSchema",
    "ReturnSchema",
    "QuantumTool",
    # 注册中心
    "ToolRegistry",
    # 错误
    "ErrorCode",
    "QMClawError",
    "ValidationError",
    "NotFoundError",
    "ExperimentNotFoundError",
    "QubitNotFoundError",
    "TimeoutError",
    "LabRADError",
    "ExecutionError",
    # 实验工具
    "RunExperimentTool",
    "RunCodeTool",
    "ListExperimentsTool",
    "GetExperimentSchemaTool",
    # 量子比特工具
    "GetQubitsTool",
    "GetQubitParamsTool",
    "SetQubitParamsTool",
    # 数据工具
    "ListHistoryTool",
    "GetExperimentDataTool",
    "GetArrayDataTool",
    "GetStatsTool",
    "ListArraysTool",
]
