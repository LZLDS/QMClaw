# SPDX-FileCopyrightText: Copyright (c) 2026 QMClaw. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
数据查询工具

提供实验历史和数据查询相关的工具实现。
"""

from typing import Any, Callable, Dict, List, Optional

from .base import ParameterSchema, QuantumTool, ToolResult, ToolSchema
from .errors import ErrorCode, NotFoundError


class ListHistoryTool(QuantumTool):
    """查询实验历史工具"""

    def __init__(
        self,
        history_lister: Callable[[int, Optional[str]], List[Dict[str, Any]]],
    ):
        """
        Args:
            history_lister: 历史列表获取函数，签名为 (last_n: int, type: str) -> List[Dict]
        """
        self._lister = history_lister

    @property
    def name(self) -> str:
        return "list_history"

    @property
    def description(self) -> str:
        return """Query experiment history.
Returns list of past experiments with their IDs, types, and timestamps."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "last_n": ParameterSchema(
                    name="last_n",
                    type="number",
                    description="Number of recent experiments to return",
                    required=False,
                    default=20,
                    minimum=1,
                    maximum=1000,
                ),
                "type": ParameterSchema(
                    name="type",
                    type="string",
                    description="Filter by experiment type (e.g., 't1', 'ramsey_df')",
                    required=False,
                ),
            },
        )

    def execute(
        self,
        last_n: int = 20,
        type: str = None,
        **kwargs,
    ) -> ToolResult[List[Dict[str, Any]]]:
        """查询实验历史"""
        try:
            history = self._lister(last_n, type)
            return ToolResult.ok(data=history)

        except Exception as e:
            return ToolResult.err(
                str(e),
                error_code=ErrorCode.INTERNAL_ERROR.value,
            )


class GetExperimentDataTool(QuantumTool):
    """获取实验数据工具"""

    def __init__(
        self,
        experiment_loader: Callable[[str], Optional[Dict[str, Any]]],
        array_lister: Callable[[str], List[str]] = None,
    ):
        """
        Args:
            experiment_loader: 实验数据加载函数，签名为 (id: str) -> Optional[Dict]
            array_lister: 数组列表获取函数，签名为 (id: str) -> List[str]
        """
        self._loader = experiment_loader
        self._array_lister = array_lister

    @property
    def name(self) -> str:
        return "get_experiment_data"

    @property
    def description(self) -> str:
        return """Get detailed data for a specific experiment.
Returns experiment parameters, results, and array data."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "experiment_id": ParameterSchema(
                    name="experiment_id",
                    type="string",
                    description="Experiment ID to retrieve",
                    required=True,
                ),
            },
        )

    def execute(self, experiment_id: str, **kwargs) -> ToolResult[Dict[str, Any]]:
        """获取实验数据"""
        if not experiment_id:
            return ToolResult.err(
                "experiment_id is required",
                error_code=ErrorCode.VALIDATION_ERROR.value,
            )

        try:
            data = self._loader(experiment_id)

            if data is None:
                return ToolResult.err(
                    f"Experiment '{experiment_id}' not found",
                    error_code=ErrorCode.NOT_FOUND.value,
                    experiment_id=experiment_id,
                    hint="Call list_history() to see available experiments",
                )

            return ToolResult.ok(data=data)

        except Exception as e:
            return ToolResult.err(
                str(e),
                error_code=ErrorCode.INTERNAL_ERROR.value,
                experiment_id=experiment_id,
            )


class GetArrayDataTool(QuantumTool):
    """获取数组数据工具"""

    def __init__(
        self,
        array_getter: Callable[[str, str, Optional[int], Optional[int]], Optional[List[float]]],
        array_lister: Callable[[str], List[str]] = None,
    ):
        """
        Args:
            array_getter: 数组数据获取函数，签名为 (exp_id: str, name: str, start: int, end: int) -> Optional[List]
            array_lister: 数组列表获取函数，签名为 (exp_id: str) -> List[str]
        """
        self._getter = array_getter
        self._array_lister = array_lister

    @property
    def name(self) -> str:
        return "get_array_data"

    @property
    def description(self) -> str:
        return """Get array data from an experiment.
Returns the array values as a list of numbers, with optional slicing."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "experiment_id": ParameterSchema(
                    name="experiment_id",
                    type="string",
                    description="Experiment ID",
                    required=True,
                ),
                "array_name": ParameterSchema(
                    name="array_name",
                    type="string",
                    description="Array name to retrieve",
                    required=True,
                ),
                "slice_start": ParameterSchema(
                    name="slice_start",
                    type="number",
                    description="Start index for array slice",
                    required=False,
                ),
                "slice_end": ParameterSchema(
                    name="slice_end",
                    type="number",
                    description="End index for array slice",
                    required=False,
                ),
            },
        )

    def execute(
        self,
        experiment_id: str,
        array_name: str,
        slice_start: int = None,
        slice_end: int = None,
        **kwargs,
    ) -> ToolResult[Dict[str, Any]]:
        """获取数组数据"""
        if not experiment_id:
            return ToolResult.err(
                "experiment_id is required",
                error_code=ErrorCode.VALIDATION_ERROR.value,
            )

        if not array_name:
            return ToolResult.err(
                "array_name is required",
                error_code=ErrorCode.VALIDATION_ERROR.value,
            )

        try:
            data = self._getter(experiment_id, array_name, slice_start, slice_end)

            if data is None:
                # 尝试获取可用数组列表
                available = []
                if self._array_lister:
                    available = self._array_lister(experiment_id) or []

                return ToolResult.err(
                    f"Array '{array_name}' not found in experiment '{experiment_id}'",
                    error_code=ErrorCode.NOT_FOUND.value,
                    available_arrays=available,
                    hint="Use list_arrays to see available arrays" if available else None,
                )

            return ToolResult.ok(
                data={
                    "experiment_id": experiment_id,
                    "array_name": array_name,
                    "data": data,
                    "length": len(data),
                    "slice": (
                        f"{slice_start or 0}:{slice_end or len(data)}"
                        if slice_start is not None or slice_end is not None
                        else "full"
                    ),
                }
            )

        except Exception as e:
            return ToolResult.err(
                str(e),
                error_code=ErrorCode.INTERNAL_ERROR.value,
                experiment_id=experiment_id,
                array_name=array_name,
            )


class GetStatsTool(QuantumTool):
    """获取统计数据工具"""

    def __init__(
        self,
        stats_getter: Callable[[str, str], Optional[Dict[str, float]]],
        array_lister: Callable[[str], List[str]] = None,
    ):
        """
        Args:
            stats_getter: 统计获取函数，签名为 (exp_id: str, name: str) -> Optional[Dict]
            array_lister: 数组列表获取函数，签名为 (exp_id: str) -> List[str]
        """
        self._getter = stats_getter
        self._array_lister = array_lister

    @property
    def name(self) -> str:
        return "get_stats"

    @property
    def description(self) -> str:
        return """Get statistical summary of an array in an experiment.
Returns min, max, mean, std, and other statistics."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "experiment_id": ParameterSchema(
                    name="experiment_id",
                    type="string",
                    description="Experiment ID",
                    required=True,
                ),
                "array_name": ParameterSchema(
                    name="array_name",
                    type="string",
                    description="Array name to get statistics for",
                    required=True,
                ),
            },
        )

    def execute(
        self,
        experiment_id: str,
        array_name: str,
        **kwargs,
    ) -> ToolResult[Dict[str, float]]:
        """获取统计数据"""
        if not experiment_id:
            return ToolResult.err(
                "experiment_id is required",
                error_code=ErrorCode.VALIDATION_ERROR.value,
            )

        if not array_name:
            return ToolResult.err(
                "array_name is required",
                error_code=ErrorCode.VALIDATION_ERROR.value,
            )

        try:
            stats = self._getter(experiment_id, array_name)

            if stats is None:
                # 尝试获取可用数组列表
                available = []
                if self._array_lister:
                    available = self._array_lister(experiment_id) or []

                return ToolResult.err(
                    f"Array '{array_name}' not found in experiment '{experiment_id}'",
                    error_code=ErrorCode.NOT_FOUND.value,
                    available_arrays=available,
                )

            return ToolResult.ok(
                data={
                    "experiment_id": experiment_id,
                    "array_name": array_name,
                    "stats": stats,
                }
            )

        except Exception as e:
            return ToolResult.err(
                str(e),
                error_code=ErrorCode.INTERNAL_ERROR.value,
                experiment_id=experiment_id,
                array_name=array_name,
            )


class ListArraysTool(QuantumTool):
    """列出实验数组工具"""

    def __init__(
        self,
        array_lister: Callable[[str], Optional[List[str]]],
    ):
        """
        Args:
            array_lister: 数组列表获取函数，签名为 (exp_id: str) -> Optional[List[str]]
        """
        self._lister = array_lister

    @property
    def name(self) -> str:
        return "list_arrays"

    @property
    def description(self) -> str:
        return "List all available arrays in an experiment."

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "experiment_id": ParameterSchema(
                    name="experiment_id",
                    type="string",
                    description="Experiment ID",
                    required=True,
                ),
            },
        )

    def execute(self, experiment_id: str, **kwargs) -> ToolResult[List[str]]:
        """列出数组"""
        if not experiment_id:
            return ToolResult.err(
                "experiment_id is required",
                error_code=ErrorCode.VALIDATION_ERROR.value,
            )

        try:
            arrays = self._lister(experiment_id)

            if arrays is None:
                return ToolResult.err(
                    f"Experiment '{experiment_id}' not found",
                    error_code=ErrorCode.NOT_FOUND.value,
                    experiment_id=experiment_id,
                )

            return ToolResult.ok(data=arrays)

        except Exception as e:
            return ToolResult.err(
                str(e),
                error_code=ErrorCode.INTERNAL_ERROR.value,
                experiment_id=experiment_id,
            )
