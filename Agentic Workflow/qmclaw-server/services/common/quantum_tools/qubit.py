# SPDX-FileCopyrightText: Copyright (c) 2026 QMClaw. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
量子比特工具

提供量子比特查询和参数设置相关的工具实现。
"""

from typing import Any, Callable, Dict, List, Optional

from .base import ParameterSchema, QuantumTool, QubitInfo, ToolResult, ToolSchema
from .errors import (
    ErrorCode,
    NotFoundError,
    QubitNotFoundError,
    QMClawError,
)


class GetQubitsTool(QuantumTool):
    """获取量子比特列表工具"""

    def __init__(
        self,
        qubit_getter: Callable[[], List[Dict[str, Any]]],
    ):
        """
        Args:
            qubit_getter: 量子比特列表获取函数，签名为 () -> List[Dict]
        """
        self._getter = qubit_getter

    @property
    def name(self) -> str:
        return "get_qubits"

    @property
    def description(self) -> str:
        return """Get list of available qubits with their basic parameters.
Returns qubit names and key parameters like f10, fread, bias_z."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "filter": ParameterSchema(
                    name="filter",
                    type="string",
                    description="Optional filter to search qubit names",
                    required=False,
                ),
            },
        )

    def execute(self, filter: str = None, **kwargs) -> ToolResult[List[Dict[str, Any]]]:
        """获取量子比特列表"""
        try:
            qubits = self._getter()

            if filter:
                filter_lower = filter.lower()
                qubits = [
                    q for q in qubits
                    if filter_lower in q.get("name", "").lower()
                ]

            return ToolResult.ok(data=qubits)

        except Exception as e:
            return ToolResult.err(
                str(e),
                error_code=ErrorCode.INTERNAL_ERROR.value,
            )


class GetQubitParamsTool(QuantumTool):
    """获取量子比特参数工具"""

    def __init__(
        self,
        qubit_getter: Callable[[str], Optional[Dict[str, Any]]],
        qubit_lister: Callable[[], List[Dict[str, Any]]] = None,
    ):
        """
        Args:
            qubit_getter: 单个量子比特参数获取函数，签名为 (name: str) -> Optional[Dict]
            qubit_lister: 量子比特列表获取函数，签名为 () -> List[Dict]
        """
        self._getter = qubit_getter
        self._lister = qubit_lister

    @property
    def name(self) -> str:
        return "get_qubit_params"

    @property
    def description(self) -> str:
        return """Get detailed parameters for a specific qubit.
Returns all parameters including frequency, pulse settings, and readout configuration."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "qubit_name": ParameterSchema(
                    name="qubit_name",
                    type="string",
                    description="Qubit name (e.g., 'q10lu1')",
                    required=True,
                ),
            },
        )

    def execute(self, qubit_name: str, **kwargs) -> ToolResult[Dict[str, Any]]:
        """获取量子比特参数"""
        if not qubit_name:
            return ToolResult.err(
                "qubit_name is required",
                error_code=ErrorCode.VALIDATION_ERROR.value,
            )

        try:
            params = self._getter(qubit_name)

            if params is None:
                # 尝试从列表获取
                available = []
                if self._lister:
                    available = [q.get("name", "") for q in self._lister()]

                return ToolResult.err(
                    f"Qubit '{qubit_name}' not found",
                    error_code=ErrorCode.QUBIT_NOT_FOUND.value,
                    available_qubits=available,
                    hint="Call get_qubits() to see available qubits",
                )

            return ToolResult.ok(data=params)

        except Exception as e:
            return ToolResult.err(
                str(e),
                error_code=ErrorCode.INTERNAL_ERROR.value,
                qubit_name=qubit_name,
            )


class SetQubitParamsTool(QuantumTool):
    """设置量子比特参数工具"""

    def __init__(
        self,
        param_setter: Callable[[str, Dict[str, Any]], Dict[str, Any]],
        qubit_lister: Callable[[], List[Dict[str, Any]]] = None,
    ):
        """
        Args:
            param_setter: 参数设置函数，签名为 (name: str, params: Dict) -> Dict
            qubit_lister: 量子比特列表获取函数，签名为 () -> List[Dict]
        """
        self._setter = param_setter
        self._lister = qubit_lister

    @property
    def name(self) -> str:
        return "set_qubit_params"

    @property
    def description(self) -> str:
        return """Set parameters for a specific qubit.
Parameters use dot notation for nested values, e.g., 'PiGate.amp', 'ReadIn.power'."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "qubit_name": ParameterSchema(
                    name="qubit_name",
                    type="string",
                    description="Qubit name (e.g., 'q10lu1')",
                    required=True,
                ),
                "params": ParameterSchema(
                    name="params",
                    type="object",
                    description="Parameters to set as key-value pairs. Use dot notation for nested values.",
                    required=True,
                ),
            },
        )

    def execute(
        self,
        qubit_name: str,
        params: Dict[str, Any],
        **kwargs,
    ) -> ToolResult[Dict[str, Any]]:
        """设置量子比特参数"""
        if not qubit_name:
            return ToolResult.err(
                "qubit_name is required",
                error_code=ErrorCode.VALIDATION_ERROR.value,
            )

        if not params:
            return ToolResult.err(
                "params is required and cannot be empty",
                error_code=ErrorCode.VALIDATION_ERROR.value,
            )

        try:
            result = self._setter(qubit_name, params)

            if not result.get("success"):
                return ToolResult.err(
                    result.get("error", "Failed to set parameters"),
                    error_code=ErrorCode.EXECUTION_ERROR.value,
                    updated=result.get("updated", []),
                    errors=result.get("errors", []),
                )

            return ToolResult.ok(
                data={
                    "success": True,
                    "qubit_name": qubit_name,
                    "updated": result.get("updated", []),
                    "errors": result.get("errors", []),
                },
            )

        except Exception as e:
            return ToolResult.err(
                str(e),
                error_code=ErrorCode.INTERNAL_ERROR.value,
                qubit_name=qubit_name,
                params=params,
            )


class ListQubitParamsTool(QuantumTool):
    """列出量子比特参数名工具

    获取指定量子比特所有可设置的参数名称列表。
    """

    def __init__(
        self,
        param_lister: Callable[[str], List[str]] = None,
    ):
        """
        Args:
            param_lister: 参数列表获取函数，签名为 (name: str) -> List[str]
        """
        self._param_lister = param_lister

    @property
    def name(self) -> str:
        return "list_qubit_params"

    @property
    def description(self) -> str:
        return """List all configurable parameter names for a qubit.
Use these parameter names with set_qubit_params."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "qubit_name": ParameterSchema(
                    name="qubit_name",
                    type="string",
                    description="Qubit name",
                    required=True,
                ),
            },
        )

    def execute(self, qubit_name: str, **kwargs) -> ToolResult[List[str]]:
        """列出量子比特参数名"""
        if not qubit_name:
            return ToolResult.err(
                "qubit_name is required",
                error_code=ErrorCode.VALIDATION_ERROR.value,
            )

        # 默认参数列表
        default_params = [
            # 基础参数
            "f10", "fread", "fc", "f21", "bias_z",
            # PiGate 参数
            "PiGate.amp", "PiGate.length", "PiGate.alpha", "PiGate.zpa",
            # PiHalf 参数
            "PiHalf.amp", "PiHalf.length", "PiHalf.alpha", "PiHalf.zpa",
            # ReadIn 参数
            "ReadIn.power", "ReadIn.length", "ReadIn.ring_power", "ReadIn.ring_length", "ReadIn.zpa",
            # ReadOut 参数
            "ReadOut.amp", "ReadOut.length", "ReadOut.window_type",
            # 判别器参数
            "discriminator.center0", "discriminator.center1",
            "discriminator.measure_f0", "discriminator.measure_f1",
            "discriminator.method", "discriminator.radius0", "discriminator.threshold",
        ]

        if self._param_lister:
            try:
                params = self._param_lister(qubit_name)
                if params:
                    return ToolResult.ok(data=params)
            except Exception:
                pass

        return ToolResult.ok(data=default_params)
