# SPDX-FileCopyrightText: Copyright (c) 2026 QMClaw. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
统一错误码定义

定义所有量子测控工具使用的错误码。
"""

from enum import Enum
from typing import Any, Dict, Optional


class ErrorCode(str, Enum):
    """错误码枚举"""
    # 成功
    SUCCESS = "SUCCESS"

    # 客户端错误 (4xx)
    VALIDATION_ERROR = "VALIDATION_ERROR"  # 参数验证失败
    UNAUTHORIZED = "UNAUTHORIZED"  # 未认证
    FORBIDDEN = "FORBIDDEN"  # 无权限
    NOT_FOUND = "NOT_FOUND"  # 资源不存在
    EXPERIMENT_NOT_FOUND = "EXPERIMENT_NOT_FOUND"  # 实验不存在
    QUBIT_NOT_FOUND = "QUBIT_NOT_FOUND"  # 量子比特不存在
    DATASET_NOT_FOUND = "DATASET_NOT_FOUND"  # 数据集不存在
    CONFLICT = "CONFLICT"  # 资源冲突

    # 服务器错误 (5xx)
    TIMEOUT = "TIMEOUT"  # 执行超时
    LABRAD_ERROR = "LABRAD_ERROR"  # LabRAD 连接或执行错误
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"  # 服务不可用
    INTERNAL_ERROR = "INTERNAL_ERROR"  # 内部错误

    # 工具特定错误
    TOOL_ERROR = "TOOL_ERROR"  # 工具执行错误
    EXECUTION_ERROR = "EXECUTION_ERROR"  # 代码执行错误
    PARAM_VALIDATION_ERROR = "PARAM_VALIDATION_ERROR"  # 参数验证错误

    # 业务错误
    BUSY = "BUSY"  # 服务忙（正在执行其他任务）
    DEGRADED = "DEGRADED"  # 降级模式
    OFFLINE_MODE = "OFFLINE_MODE"  # 离线模式


class QMClawError(Exception):
    """量子测控工具异常基类"""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        details: Optional[Dict[str, Any]] = None,
        hint: str = "",
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.hint = hint

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "code": self.error_code.value,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        if self.hint:
            result["hint"] = self.hint
        return result

    def to_result_dict(self) -> Dict[str, Any]:
        """转换为 ToolResult.to_dict() 格式"""
        return {
            "success": False,
            "error": self.message,
            "error_code": self.error_code.value,
            "details": self.details,
            "hint": self.hint,
        }


class ValidationError(QMClawError):
    """参数验证错误"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, hint: str = ""):
        super().__init__(
            message,
            error_code=ErrorCode.VALIDATION_ERROR,
            details=details,
            hint=hint,
        )


class NotFoundError(QMClawError):
    """资源不存在错误"""

    def __init__(self, message: str, resource_type: str = "", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message,
            error_code=ErrorCode.NOT_FOUND,
            details=details,
        )
        self.resource_type = resource_type


class ExperimentNotFoundError(NotFoundError):
    """实验不存在错误"""

    def __init__(self, experiment_name: str, available: list = None):
        details = {}
        if available:
            details["available_experiments"] = available
        super().__init__(
            f"Experiment '{experiment_name}' not found",
            resource_type="experiment",
            details=details,
            hint="Call list_experiments to see available experiments",
        )
        self.experiment_name = experiment_name


class QubitNotFoundError(NotFoundError):
    """量子比特不存在错误"""

    def __init__(self, qubit_name: str, available: list = None):
        details = {}
        if available:
            details["available_qubits"] = available
        super().__init__(
            f"Qubit '{qubit_name}' not found",
            resource_type="qubit",
            details=details,
            hint="Call get_qubits to see available qubits",
        )
        self.qubit_name = qubit_name


class TimeoutError(QMClawError):
    """执行超时错误"""

    def __init__(self, message: str = "Execution timed out", timeout: int = 0):
        super().__init__(
            message,
            error_code=ErrorCode.TIMEOUT,
            details={"timeout": timeout} if timeout else {},
            hint="Try reducing the number of iterations or increase the timeout",
        )


class LabRADError(QMClawError):
    """LabRAD 错误"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message,
            error_code=ErrorCode.LABRAD_ERROR,
            details=details,
            hint="Check if LabRAD server is running and accessible",
        )


class ExecutionError(QMClawError):
    """代码执行错误"""

    def __init__(self, message: str, code: str = "", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message,
            error_code=ErrorCode.EXECUTION_ERROR,
            details=details,
            hint="Check the code syntax and variable names",
        )
        self.code = code


def get_error_message(error_code: ErrorCode) -> str:
    """获取错误码对应的默认消息"""
    messages = {
        ErrorCode.SUCCESS: "Success",
        ErrorCode.VALIDATION_ERROR: "Invalid parameters",
        ErrorCode.UNAUTHORIZED: "Unauthorized access",
        ErrorCode.FORBIDDEN: "Access forbidden",
        ErrorCode.NOT_FOUND: "Resource not found",
        ErrorCode.EXPERIMENT_NOT_FOUND: "Experiment not found",
        ErrorCode.QUBIT_NOT_FOUND: "Qubit not found",
        ErrorCode.DATASET_NOT_FOUND: "Dataset not found",
        ErrorCode.CONFLICT: "Resource conflict",
        ErrorCode.TIMEOUT: "Operation timed out",
        ErrorCode.LABRAD_ERROR: "LabRAD error",
        ErrorCode.SERVICE_UNAVAILABLE: "Service unavailable",
        ErrorCode.INTERNAL_ERROR: "Internal error",
        ErrorCode.TOOL_ERROR: "Tool execution error",
        ErrorCode.EXECUTION_ERROR: "Execution error",
        ErrorCode.PARAM_VALIDATION_ERROR: "Parameter validation error",
        ErrorCode.BUSY: "Service is busy",
        ErrorCode.DEGRADED: "Service in degraded mode",
        ErrorCode.OFFLINE_MODE: "Operating in offline mode",
    }
    return messages.get(error_code, "Unknown error")


def is_retryable(error_code: ErrorCode) -> bool:
    """判断错误是否可重试"""
    retryable_codes = {
        ErrorCode.TIMEOUT,
        ErrorCode.LABRAD_ERROR,
        ErrorCode.SERVICE_UNAVAILABLE,
        ErrorCode.BUSY,
        ErrorCode.DEGRADED,
    }
    return error_code in retryable_codes
