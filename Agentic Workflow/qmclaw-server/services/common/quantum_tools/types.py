# SPDX-FileCopyrightText: Copyright (c) 2026 QMClaw. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
数据类型定义

提供量子测控相关的额外数据类型定义。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ExperimentType(str, Enum):
    """实验类型枚举"""
    SPECTROSCOPY = "spectroscopy"
    S21 = "s21"
    IQRAW = "iqraw"
    T1 = "t1"
    RAMSEY = "ramsey"
    RAMSEY_DF = "ramsey_df"
    PIAMP = "piamp"
    SINGLE_SHOT = "single_shot"
    ALLXY = "allxy"
    XEB = "xeb"
    SWAP = "swap"
    DRAG = "drag_calibrate"
    CUSTOM = "custom"


class QubitType(str, Enum):
    """量子比特类型枚举"""
    TRANSMON = "transmon"
    FLUXONIUM = "fluxonium"
    UNKNOWN = "unknown"


@dataclass
class SessionInfo:
    """会话信息"""
    name: str
    path: List[str]
    host: str = ""
    port: int = 0
    user: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "host": self.host,
            "port": self.port,
            "user": self.user,
        }


@dataclass
class ConnectionStatus:
    """连接状态"""
    connected: bool
    initialized: bool
    session_path: Optional[List[str]] = None
    qubit_count: int = 0
    last_error: Optional[str] = None
    mode: str = "online"  # online, offline, auto

    def to_dict(self) -> Dict[str, Any]:
        return {
            "connected": self.connected,
            "initialized": self.initialized,
            "session_path": self.session_path,
            "qubit_count": self.qubit_count,
            "last_error": self.last_error,
            "mode": self.mode,
        }


@dataclass
class ToolCall:
    """工具调用记录"""
    tool_name: str
    args: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    duration: float = 0
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "args": self.args,
            "result": self.result,
            "error": self.error,
            "duration": self.duration,
            "timestamp": self.timestamp,
        }


@dataclass
class AgentMessage:
    """Agent 消息"""
    role: str  # system, user, assistant, tool
    content: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "timestamp": self.timestamp,
        }


@dataclass
class ExperimentSchema:
    """实验 Schema 定义"""
    name: str
    description: str
    module_path: str = ""
    parameters: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "module_path": self.module_path,
            "parameters": self.parameters,
        }


@dataclass
class QubitParams:
    """量子比特参数"""
    # 频率参数
    f10: Optional[float] = None  # |0> -> |1> 频率
    fread: Optional[float] = None  # 读取频率
    fc: Optional[float] = None  # 腔体频率
    f21: Optional[float] = None  # |1> -> |2> 频率
    bias_z: Optional[float] = None  # Z 偏置

    # PiGate 参数
    pi_amp: Optional[float] = None
    pi_length: Optional[float] = None
    pi_alpha: Optional[float] = None
    pi_zpa: Optional[float] = None

    # ReadIn 参数
    readin_power: Optional[float] = None
    readin_length: Optional[float] = None
    readin_ring_power: Optional[float] = None
    readin_ring_length: Optional[float] = None

    # ReadOut 参数
    readout_amp: Optional[float] = None
    readout_length: Optional[float] = None
    readout_window_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "f10": self.f10,
            "fread": self.fread,
            "fc": self.fc,
            "f21": self.f21,
            "bias_z": self.bias_z,
            "pi_amp": self.pi_amp,
            "pi_length": self.pi_length,
            "pi_alpha": self.pi_alpha,
            "pi_zpa": self.pi_zpa,
            "readin_power": self.readin_power,
            "readin_length": self.readin_length,
            "readin_ring_power": self.readin_ring_power,
            "readin_ring_length": self.readin_ring_length,
            "readout_amp": self.readout_amp,
            "readout_length": self.readout_length,
            "readout_window_type": self.readout_window_type,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QubitParams':
        """从字典创建"""
        params = cls()
        for key, value in data.items():
            if hasattr(params, key):
                setattr(params, key, value)
        return params


@dataclass
class ExecutionContext:
    """代码执行上下文"""
    cxn: Any = None  # LabRAD 连接
    s: Any = None  # Session 管理器
    sq: Any = None  # 实验模块
    data: Any = None  # DataLab
    qter: Any = None  # QubitUpdater
    qubits: Dict[str, Any] = field(default_factory=dict)
    couplers: Dict[str, Any] = field(default_factory=dict)

    def to_globals(self) -> Dict[str, Any]:
        """转换为 exec() 的全局变量字典"""
        globals_dict = {
            "__name__": "__agent__",
            "__builtins__": __builtins__,
        }

        if self.cnx is not None:
            globals_dict["cxn"] = self.cnx
        if self.s is not None:
            globals_dict["s"] = self.s
        if self.sq is not None:
            globals_dict["sq"] = self.sq
        if self.data is not None:
            globals_dict["data"] = self.data
        if self.qter is not None:
            globals_dict["qter"] = self.qter

        # 添加量子比特和耦合器
        for name, obj in self.qubits.items():
            globals_dict[name] = obj
        for name, obj in self.couplers.items():
            globals_dict[name] = obj

        return globals_dict


@dataclass
class APIResponse:
    """统一 API 响应"""
    success: bool
    data: Any = None
    error: Optional[Dict[str, Any]] = None
    request_id: str = ""
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "success": self.success,
        }
        if self.success:
            result["data"] = self.data
        else:
            result["error"] = self.error
        if self.request_id:
            result["request_id"] = self.request_id
        if self.timestamp:
            result["timestamp"] = self.timestamp
        return result
