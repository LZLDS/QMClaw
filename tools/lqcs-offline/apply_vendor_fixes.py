# -*- coding: utf-8 -*-
"""
把 vendor/QubitClient 里必须的补丁重新应用一遍。

为什么需要这个脚本
------------------
`vendor/QubitClient` 在父仓库里是**子模块指针**（160000 3da70fe），但目录里**没有 .git**，
是从 vendor.zip 解出来的普通副本。所以：
  * 在里面改的代码，父仓库 `git status` 看不见、`git commit` 也带不走；
  * 重新解压 vendor.zip / 换机器，改动全丢。

这个脚本把改动写成「已知坏模式 -> 期望好模式」的替换规则，可以随时重放：

    python apply_vendor_fixes.py            # 应用（幂等，已应用会跳过）
    python apply_vendor_fixes.py --check    # 只检查，不改动（退出码非 0 表示有未应用项）

比 .patch 更耐操：不依赖行号和上下文精确匹配，重复运行安全。
"""

from __future__ import annotations

import argparse
import os
import sys

VENDOR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "vendor", "QubitClient")
)

FIXES = [
    {
        "rel": "qubitclient/draw/nnscope/powershiftnnscopepltplotter.py",
        "why": "powershift 的 amp_2d 是复数（I+1j*Q），cv2.flip 不支持复数类型，"
               "会抛 error: (-5:Bad argument) in function 'flip'",
        "bad": "            data = cv2.flip(data, 0)",
        "good": "            data = np.ascontiguousarray(np.flip(data, 0))",
    },
    {
        "rel": "qubitclient/draw/nnscope/powershiftnnscopeplyplotter.py",
        "why": "同上（plotly 版）",
        "bad": "            data = cv2.flip(data, 0)",
        "good": "            data = np.ascontiguousarray(np.flip(data, 0))",
    },
    {
        "rel": "tests/skills/lqcs/test_rb.py",
        "why": "死 gate：data.get(\"name\") 在 {Title前缀: 数组} 上恒为空串，条件永远为 False，"
               "整个测试静默空转（exit=0 且无任何产出）",
        "bad": '        if "rb" in data.get("name", "").lower():\n'
               '            if task_key in ["rb"]:',
        "good": '        # 注意：base_dir 本身已按数据类型分好（./data/RB）。\n'
                '        # 原来这里写的是 if "rb" in data.get("name", "").lower()，但\n'
                '        # utils.get_hdf5_content 返回的是 {Title前缀: 结构化数组}，根本没有 name 键，\n'
                '        # 条件恒为 False，整个循环体从不执行 —— 表现为「exit=0 但什么都没做」。\n'
                '        if task_key in ["rb"]:',
    },
    {
        "rel": "tests/skills/lqcs/test_rabicos.py",
        "why": "同样的死 gate（data.get(\"name\") 恒 False），而且原来把函数体多缩进了一层，"
               "去掉 if 后必须同时回退缩进",
        "bad": '        if "rabi" in data.get("name", "").lower():\n'
               '            found_files += 1\n'
               '            print(f"正在测试 Rabi 文件 ({found_files}): {hdf5_path}")\n'
               '\n'
               '            analysis_result = rabi(data)\n'
               "            fig_list = plot_rabicos(data, analysis_result, save_path=f'./tmp/vis/rabicos_{pure_name}.png')\n"
               '            # if fig_list and len(fig_list) > 0:\n'
               '            #     fig_list[0].show()\n'
               '            # plt.show(block=True)',
        "good": '        # 注意：base_dir 已按数据类型分好（tmp/data/rabi）。原来这里用\n'
                '        # data.get("name") 判断，而 utils.get_hdf5_content 返回的是 {Title前缀: 数组}，\n'
                '        # 没有 name 键，条件恒为 False —— 整个测试静默什么都不做（exit=0 无产出）。\n'
                '        found_files += 1\n'
                '        print(f"正在测试 Rabi 文件 ({found_files}): {hdf5_path}")\n'
                '\n'
                '        analysis_result = rabi(data)\n'
                "        fig_list = plot_rabicos(data, analysis_result, save_path=f'./tmp/vis/rabicos_{pure_name}.png')\n"
                '        # if fig_list and len(fig_list) > 0:\n'
                '        #     fig_list[0].show()\n'
                '        # plt.show(block=True)',
    },
    {
        "rel": "skills/lqcs-qubit-calib/scripts/analysis/inception.py",
        "why": "scope 的 spectrum2d 载荷布局错：共享的 spectrum2d_convert 返回 "
               "(amp_2d, zpa, freq)，而实测真实服务要的是 (amp_2d.T, freq, zpa)"
               "（少转置 + 轴顺序相反）。不能改共享转换器 —— nnscope 的 seglines "
               "复用同一个，而旧布局在真实服务上是能通过的。",
        "bad": "    results = scope_template(image,task_type=TaskName.SPECTRUM2D)",
        "good": '    fixed = {"image": {}}\n'
                '    for q, item in image["image"].items():\n'
                '        amp2d, zpa, freq = item[0], item[1], item[2]\n'
                '        fixed["image"][q] = (amp2d.T, freq, zpa)\n'
                '    results = scope_template(fixed, task_type=TaskName.SPECTRUM2D)',
    },
    {
        "rel": "qubitclient/nnscope/nnscope.py",
        "why": "非 200 响应没有短路：带阈值时会直接进 postprocess，而 postprocess 调 "
               "response.json()，服务端 500 返回 text/plain 会抛 JSONDecodeError，"
               "再被 handle_exceptions 吞掉，真实原因完全丢失",
        "bad": "    def get_result(self,response, threshold:float=None, task_type: str = None):\n"
               "        if threshold is None:",
        "good": "    def get_result(self,response, threshold:float=None, task_type: str = None):\n"
                "        # 非 200 必须先短路返回。否则即使带了阈值也会进 postprocess，\n"
                "        # 而 postprocess 直接调 response.json()：服务端 500 返回的是\n"
                "        # text/plain（如 'Internal Server Error'），会抛 JSONDecodeError，\n"
                "        # 再被上层 handle_exceptions 吞掉，真实原因完全丢失。\n"
                "        if response.status_code != 200:\n"
                "            # 抛异常而不是返回 []：返回空列表会被上层当成「正常但无结果」，\n"
                "            # 静默跳过一个文件（少出一张图）却仍是 exit=0。抛出后由\n"
                "            # handle_exceptions 记录，配合 QUBITCLIENT_STRICT_EXIT=1 影响退出码。\n"
                "            raise RuntimeError(\n"
                "                f\"HTTP {response.status_code} from NNScope service: {response.text[:200]}\")\n"
                "        if threshold is None:",
    },
    {
        "rel": "qubitclient/scope/scope.py",
        "why": "同上：非 200 时 response.parsed 是 None，postprocess 会抛 AttributeError",
        "bad": "    def get_result(self,response, threshold:float=None, task_type: str = None):\n"
               "        if threshold is None:",
        "good": "    def get_result(self,response, threshold:float=None, task_type: str = None):\n"
                "        # 非 200 必须先短路返回（理由同 nnscope.py：带阈值时会直接进 postprocess，\n"
                "        # 而 postprocess 假定 response.parsed 一定是 dict，非 200 时它是 None，\n"
                "        # 会抛 AttributeError 并被 handle_exceptions 吞掉）。\n"
                "        if response.status_code != 200:\n"
                "            # 同 nnscope.py：抛异常而不是返回 []，否则「服务端报错」会被当成\n"
                "            # 「正常但无结果」，静默少出图且退出码仍为 0。\n"
                "            raise RuntimeError(\n"
                "                f\"HTTP {response.status_code} from Scope service: {response.parsed}\")\n"
                "        if threshold is None:",
    },
    {
        "rel": "qubitclient/wrapper_handler.py",
        "why": "handle_exceptions 吞掉异常后连退出码都不影响 —— 分析全失败但进程仍返回 0，"
               "任何以退出码为判据的 CI 都失效。加入计数器 + 退出时统一报告，"
               "并用 QUBITCLIENT_STRICT_EXIT=1 让退出码变非零（默认不严格，避免影响长驻服务）",
        "bad": """import functools
import logging
import traceback

def handle_exceptions(func):""",
        "good": """import atexit
import functools
import logging
import os
import sys
import traceback

# 被 handle_exceptions 吞掉的异常摘要。原本这些异常只写日志、连退出码都不影响，
# 导致「分析全失败但进程仍返回 0」，任何以退出码为判据的 CI 都是失效的。
_SWALLOWED = []


def swallowed_errors():
    \"\"\"返回本次进程内被吞掉的异常摘要列表。\"\"\"
    return list(_SWALLOWED)


def _atexit_report():
    if not _SWALLOWED:
        return
    sys.stderr.write(
        f"\\n[handle_exceptions] 本次运行共吞掉 {len(_SWALLOWED)} 个异常"
        f"（这些异常原本不影响退出码）：\\n"
        + "".join(f"  - {m}\\n" for m in _SWALLOWED[:20])
        + (f"  ... 其余 {len(_SWALLOWED) - 20} 个省略\\n" if len(_SWALLOWED) > 20 else "")
    )
    sys.stderr.flush()
    # 默认只报告不改退出码，避免影响长驻服务；显式设置该环境变量才让退出码变非零。
    if os.environ.get("QUBITCLIENT_STRICT_EXIT") == "1":
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)


atexit.register(_atexit_report)


def handle_exceptions(func):""",
    },
    {
        "rel": "qubitclient/wrapper_handler.py",
        "why": "把被吞的异常记入摘要（配合上一条）",
        "bad": """            # 返回None或者可以根据需要返回默认值
            return None""",
        "good": """            # 记入摘要，供退出时统一报告 / 参与退出码
            _SWALLOWED.append(f"{func.__name__}: {type(e).__name__}: {e}")
            # 返回None或者可以根据需要返回默认值
            return None""",
    },
    {
        "rel": "qubitclient/scope/postprocess.py",
        "why": "多个 postprocess 函数的 status=='failed' 分支只记日志、没有 continue，紧接着"
               "无条件索引 result[...]（如 result['params']），把服务端明确返回的 status=failed"
               "变成了 KeyError（还被 handle_exceptions 吞掉）。文件里共 6 处同样的写法。",
        "all": True,
        "bad": """        if state == 'failed':
            logging.warning(f"Error in request: {result.get('error')}")""",
        "good": """        if state == 'failed':
            # 只记日志就继续往下走的话，紧接着会无条件索引 result[...]（如 result['params']），
            # 于是服务端「明确返回 status=failed」就变成了 KeyError，还被上层吞掉。
            logging.warning(f"Error in request: {result.get('error')}")
            continue""",
    },
]


def main() -> int:
    ap = argparse.ArgumentParser(description="重新应用 vendor/QubitClient 的必要补丁")
    ap.add_argument("--check", action="store_true", help="只检查不修改")
    args = ap.parse_args()

    if not os.path.isdir(VENDOR):
        print(f"找不到 vendor 目录: {VENDOR}", file=sys.stderr)
        return 2
    print(f"vendor: {VENDOR}\n")

    pending = 0
    for fix in FIXES:
        path = os.path.join(VENDOR, fix["rel"].replace("/", os.sep))
        if not os.path.isfile(path):
            print(f"  [缺失] {fix['rel']}")
            pending += 1
            continue
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

        if fix["good"] in text:
            print(f"  [已应用] {fix['rel']}")
            continue
        if fix["bad"] not in text:
            print(f"  [不匹配] {fix['rel']} —— 文件内容与预期不符，需要人工看")
            print(f"           原因: {fix['why']}")
            pending += 1
            continue

        if args.check:
            print(f"  [待应用] {fix['rel']}")
            print(f"           原因: {fix['why']}")
            pending += 1
            continue

        with open(path, "w", encoding="utf-8") as f:
            # "all": True 表示替换该文件里所有匹配（例如 scope/postprocess.py 里
            # 同一段 "只记日志不 continue" 的写法出现了 6 次，只替换第一处不够）。
            f.write(text.replace(fix["bad"], fix["good"], -1 if fix.get("all") else 1))
        print(f"  [已修复] {fix['rel']}")
        print(f"           原因: {fix['why']}")

    print()
    if pending:
        print(f"有 {pending} 处未应用/不匹配。" + ("（--check 模式，未改动）" if args.check else ""))
        return 1
    print("全部补丁已就绪。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
