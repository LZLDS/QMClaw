# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Experiment discovery via AST parsing."""

import ast
import json
import math
from pathlib import Path
from typing import Optional

from .models import ExperimentSchema, ParameterSpec


def discover_experiments(scripts_dir: Path) -> list[ExperimentSchema]:
    """Discover experiments from Python scripts using AST parsing.

    Scans the scripts directory for Python files and extracts experiment
    schemas without executing any code.

    Args:
        scripts_dir: Directory containing experiment scripts

    Returns:
        List of experiment schemas
    """
    experiments = []

    if not scripts_dir.exists() or not scripts_dir.is_dir():
        return experiments

    for script_path in scripts_dir.glob("*.py"):
        # Skip private files
        if script_path.name.startswith("_"):
            continue

        schema = _extract_schema_from_file(script_path)
        if schema:
            experiments.append(schema)

    return experiments


def get_experiment_schema(name: str, scripts_dir: Path) -> Optional[ExperimentSchema]:
    """Get schema for a specific experiment by name.

    Args:
        name: Experiment name (function name)
        scripts_dir: Directory containing experiment scripts

    Returns:
        Experiment schema or None if not found
    """
    experiments = discover_experiments(scripts_dir)
    for exp in experiments:
        if exp.name == name:
            return exp
    return None


def _extract_schema_from_file(script_path: Path) -> Optional[ExperimentSchema]:
    """Extract experiment schema from a single Python file."""
    try:
        source = script_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return None

    # Find first public top-level function
    func_def = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                func_def = node
                break

    if func_def is None:
        return None

    # Check return type annotation - must be dict
    if func_def.returns:
        return_type = _get_type_name(func_def.returns)
        if return_type != "dict":
            return None
    else:
        return None

    # Extract function details
    func_name = func_def.name
    func_doc = ast.get_docstring(func_def) or ""
    description = func_doc.split("\n")[0] if func_doc else ""

    # Parse parameters
    parameters = _parse_function_parameters(func_def)

    # Skip if no parameters have type hints
    if not any(p for p in parameters):
        return None

    return ExperimentSchema(
        name=func_name,
        description=description,
        parameters=parameters,
        module_path=str(script_path),
    )


def _parse_function_parameters(func_def: ast.FunctionDef) -> list[ParameterSpec]:
    """Parse function parameters from AST."""
    parameters = []

    all_args = list(getattr(func_def.args, "posonlyargs", []) or []) + list(func_def.args.args)

    num_defaults = len(func_def.args.defaults)
    num_args = len(all_args)
    default_offset = num_args - num_defaults

    for i, arg in enumerate(all_args):
        if not arg.annotation:
            continue

        param_name = arg.arg
        type_info = _parse_annotation(arg.annotation)

        has_default = i >= default_offset
        default_value = None
        default_resolved = True
        if has_default:
            default_node = func_def.args.defaults[i - default_offset]
            default_resolved, default_value = _eval_default(default_node)

        parameters.append(
            ParameterSpec(
                name=param_name,
                type=type_info["type"],
                default=default_value,
                default_resolved=default_resolved,
                range=type_info["range"],
                required=not has_default,
            )
        )

    # Handle keyword-only args
    for kwarg, kw_default in zip(func_def.args.kwonlyargs, func_def.args.kw_defaults):
        if not kwarg.annotation:
            continue

        type_info = _parse_annotation(kwarg.annotation)
        if kw_default is None:
            default_resolved, default_value = True, None
        else:
            default_resolved, default_value = _eval_default(kw_default)

        parameters.append(
            ParameterSpec(
                name=kwarg.arg,
                type=type_info["type"],
                default=default_value,
                default_resolved=default_resolved,
                range=type_info["range"],
                required=kw_default is None,
            )
        )

    return parameters


def _parse_annotation(annotation: ast.expr) -> dict:
    """Parse type annotation to extract type and range."""
    result = {"type": "str", "range": None}

    if isinstance(annotation, ast.Subscript):
        base_name = _get_type_name(annotation.value)

        if base_name == "Annotated":
            return _parse_annotated(annotation)
        elif base_name:
            result["type"] = base_name

    elif isinstance(annotation, ast.Name):
        type_map = {
            "float": "float",
            "int": "int",
            "str": "str",
            "bool": "bool",
            "list": "list",
            "dict": "dict",
        }
        result["type"] = type_map.get(annotation.id, "str")

    return result


def _parse_annotated(subscript: ast.Subscript) -> dict:
    """Parse Annotated[type, (min, max)] annotation."""
    result = {"type": "str", "range": None}

    slice_node = subscript.slice
    if hasattr(ast, "Index") and isinstance(slice_node, ast.Index):
        slice_node = slice_node.value

    if not isinstance(slice_node, ast.Tuple):
        return result

    elements = slice_node.elts
    if len(elements) < 2:
        return result

    type_node = elements[0]
    if isinstance(type_node, ast.Name):
        type_map = {
            "float": "float",
            "int": "int",
            "str": "str",
            "bool": "bool",
            "dict": "dict",
        }
        result["type"] = type_map.get(type_node.id, "str")

    constraint_node = elements[1]
    if hasattr(ast, "Index") and isinstance(constraint_node, ast.Index):
        constraint_node = constraint_node.value

    if isinstance(constraint_node, ast.Tuple):
        values = [_eval_literal(el) for el in constraint_node.elts]
        values = [v for v in values if v is not None]

        if len(values) >= 2 and all(isinstance(v, (int, float)) for v in values):
            bounds = [v if math.isfinite(v) else None for v in values[:2]]
            if any(b is not None for b in bounds):
                result["range"] = (bounds[0], bounds[1])

    return result


def _get_type_name(node: ast.expr) -> Optional[str]:
    """Get the type name from an annotation node."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return node.attr
    elif isinstance(node, ast.Subscript):
        return _get_type_name(node.value)
    return None


def _eval_default(node: ast.expr) -> tuple[bool, any]:
    """Evaluate JSON-compatible defaults and distinguish unresolved values."""
    try:
        value = ast.literal_eval(node)
        round_tripped = json.loads(json.dumps(value, allow_nan=False))
        if type(round_tripped) is not type(value) or round_tripped != value:
            return False, None
        return True, value
    except (ValueError, TypeError, json.JSONDecodeError):
        return False, None


def _eval_literal(node: ast.expr) -> Optional[any]:
    """Safely evaluate AST literal to Python value."""
    if node is None:
        return None

    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        operand = _eval_literal(node.operand)
        if operand is not None:
            return -operand
        return None

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd):
        return _eval_literal(node.operand)

    if isinstance(node, ast.List):
        values = [_eval_literal(el) for el in node.elts]
        if None in values:
            return None
        return values

    if isinstance(node, ast.Tuple):
        values = [_eval_literal(el) for el in node.elts]
        if None in values:
            return None
        return tuple(values)

    if isinstance(node, ast.Name):
        if node.id == "True":
            return True
        elif node.id == "False":
            return False
        elif node.id == "None":
            return None

    return None
