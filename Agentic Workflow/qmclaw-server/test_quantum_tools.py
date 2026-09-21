#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试脚本：验证三个智能体服务的测控实验调用能力

使用方法:
    python test_quantum_tools.py

前提条件:
    1. quantum_service 必须在 localhost:3003 运行
    2. agent_service 必须在 localhost:3005 运行
    3. qca_service 必须在 localhost:3011 运行
    4. hermes_service 必须在 localhost:3012 运行
"""

import json
import urllib.request
import urllib.error
import sys
from typing import Any, Dict, Optional


# 服务地址
QUANTUM_SERVICE = "http://localhost:3003"
AGENT_SERVICE = "http://localhost:3005"
QCA_SERVICE = "http://localhost:3011"
HERMES_SERVICE = "http://localhost:3012"


def http_get(url: str) -> dict:
    """发送 GET 请求"""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


def http_post(url: str, data: dict) -> dict:
    """发送 POST 请求"""
    try:
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def print_header(title: str):
    """打印标题"""
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_result(name: str, result: dict, success: bool = True):
    """打印测试结果"""
    status = "[PASS]" if success else "[FAIL]"
    print(f"  {status} {name}")
    if "error" in result:
        print(f"        Error: {result['error']}")


def test_quantum_service_health():
    """测试 quantum_service 健康状态"""
    print_header("1. quantum_service 健康检查")

    result = http_get(f"{QUANTUM_SERVICE}/health")
    print_result("GET /health", result, "error" not in result)

    if "status" in result:
        print(f"        Status: {result.get('status')}")
        print(f"        LabRAD: {result.get('labrad_connected', 'N/A')}")

    return result


def test_quantum_service_tools():
    """测试 quantum_service 的工具端点"""
    print_header("2. quantum_service 工具列表")

    # 获取量子比特
    result = http_get(f"{QUANTUM_SERVICE}/qubits")
    print_result("GET /qubits", result, "qubits" in result)
    if "qubits" in result:
        print(f"        Qubit count: {len(result['qubits'])}")
        if result["qubits"]:
            print(f"        First qubit: {result['qubits'][0].get('name', 'N/A')}")

    # 获取实验列表
    result = http_get(f"{QUANTUM_SERVICE}/experiments")
    print_result("GET /experiments", result, "experiments" in result)
    if "experiments" in result:
        print(f"        Experiment count: {len(result['experiments'])}")

    return result


def test_agent_service():
    """测试 agent_service"""
    print_header("3. agent_service 统一 API")

    # 测试 /api/v1/tools
    result = http_get(f"{AGENT_SERVICE}/api/v1/tools")
    print_result("GET /api/v1/tools", result, "data" in result or "error" not in result)
    if "data" in result:
        print(f"        Tool count: {len(result['data'])}")
        for tool in result["data"]:
            print(f"        - {tool['function']['name']}")

    # 测试 /api/v1/qubits
    result = http_post(f"{AGENT_SERVICE}/api/v1/tools/get_qubits", {})
    print_result("POST /api/v1/tools/get_qubits", result, result.get("success") or "error" not in result)
    if result.get("data"):
        print(f"        Qubit count: {len(result['data'])}")

    # 测试 /api/v1/experiments
    result = http_post(f"{AGENT_SERVICE}/api/v1/tools/list_experiments", {})
    print_result("POST /api/v1/tools/list_experiments", result, result.get("success") or "error" not in result)

    # 测试 /health
    result = http_get(f"{AGENT_SERVICE}/health")
    print_result("GET /health", result, "status" in result)
    if "status" in result:
        print(f"        Status: {result.get('status')}")

    return result


def test_qca_service():
    """测试 qca_service"""
    print_header("4. qca_service 工具端点")

    # 测试 /health
    result = http_get(f"{QCA_SERVICE}/health")
    print_result("GET /health", result, "status" in result)
    if "status" in result:
        print(f"        Status: {result.get('status')}")

    # 测试 /capabilities
    result = http_get(f"{QCA_SERVICE}/capabilities")
    print_result("GET /capabilities", result, "experiments" in result or "error" not in result)
    if "experiments" in result:
        print(f"        Experiment count: {len(result['experiments'])}")

    # 测试 /schema/t1_measurement
    result = http_get(f"{QCA_SERVICE}/schema/t1_measurement")
    print_result("GET /schema/t1_measurement", result, "name" in result or "error" not in result)

    return result


def test_hermes_service():
    """测试 hermes_service"""
    print_header("5. hermes_service 量子工具端点")

    # 测试 /health
    result = http_get(f"{HERMES_SERVICE}/health")
    print_result("GET /health", result, "status" in result)
    if "status" in result:
        print(f"        Status: {result.get('status')}")

    # 测试 /quantum-tools
    result = http_get(f"{HERMES_SERVICE}/quantum-tools")
    print_result("GET /quantum-tools", result, "data" in result or "error" not in result)
    if "data" in result:
        print(f"        Tool count: {result['data'].get('tool_count', 0)}")

    # 测试 /models
    result = http_get(f"{HERMES_SERVICE}/models")
    print_result("GET /models", result, "models" in result or "error" not in result)
    if "models" in result:
        print(f"        Model count: {len(result['models'])}")

    return result


def test_response_format():
    """测试响应格式一致性"""
    print_header("6. 响应格式一致性测试")

    # 从三个服务获取 qubits
    services = {
        "quantum_service": f"{QUANTUM_SERVICE}/qubits",
        "agent_service": f"{AGENT_SERVICE}/api/v1/tools/get_qubits",
    }

    formats = {}
    for name, url in services.items():
        if "api/v1" in url:
            result = http_post(url, {})
        else:
            result = http_get(url)

        if "qubits" in result:
            formats[name] = "quantum_format"  # {qubits: [...]}
        elif result.get("success") and "data" in result:
            formats[name] = "unified_format"  # {success, data: [...]}
        else:
            formats[name] = "unknown"

        print(f"  {name}: {formats[name]}")

    # 检查格式是否一致
    unique_formats = set(formats.values())
    if len(unique_formats) == 1:
        print(f"  [OK] All services use consistent format: {unique_formats.pop()}")
    else:
        print(f"  [WARN] Services use different formats: {formats}")


def main():
    """主测试函数"""
    print()
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 10 + "QMClaw 量子工具测试套件" + " " * 17 + "║")
    print("╚" + "═" * 58 + "╝")

    print()
    print("测试前提条件:")
    print("  1. quantum_service 必须在 localhost:3003 运行")
    print("  2. agent_service 必须在 localhost:3005 运行")
    print("  3. qca_service 必须在 localhost:3011 运行")
    print("  4. hermes_service 必须在 localhost:3012 运行")
    print()

    # 按顺序测试
    try:
        # 1. quantum_service 是基础，必须先测试
        test_quantum_service_health()
        test_quantum_service_tools()

        # 2. 测试 agent_service
        test_agent_service()

        # 3. 测试 qca_service
        test_qca_service()

        # 4. 测试 hermes_service
        test_hermes_service()

        # 5. 测试响应格式一致性
        test_response_format()

        print()
        print("=" * 60)
        print("  测试完成!")
        print("=" * 60)

    except KeyboardInterrupt:
        print()
        print("测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print()
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
