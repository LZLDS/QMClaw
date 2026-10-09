# -*- coding: utf-8 -*-
"""
把 deploy/offline_data 里的真实数据按实验类型灌进 vendor/QubitClient 的测试数据目录。

为什么需要脚本
-------------
tests/skills/lqcs 下的测试都用**相对路径**的 base_dir（如 `tmp/data/powershift`），
而这些目录在仓库里原本是空的。手工拷贝既不可重复、也踩过坑：
powershift 第一次挑中的 2 个 S21power2d 文件不是完整矩形扫描，导致
`powershift_convert` 抛 cannot reshape array of size 184 into shape (15,13)。
所以这里把「类型 -> 目录」的映射和筛选规则都固化下来。

    python populate_data.py              # 灌入
    python populate_data.py --clean      # 先清空目标目录再灌入
    python populate_data.py --list       # 只打印映射，不动文件

2D 类型（S21power2d / S21zpa2d）会自动**优先挑完整矩形扫描**的文件：
行数必须等于「唯一频率数 × 唯一扫描轴数」，否则 reshape 必崩。
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

import h5py
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WORKSPACE = os.path.dirname(ROOT)
VENDOR = os.path.join(ROOT, "vendor", "QubitClient")
SRC_CANDIDATES = [
    os.path.join(WORKSPACE, "deploy", "offline_data"),
    os.path.join(ROOT, "Agentic Workflow", "qmclaw-server", "data", "offline_data"),
]

PER_DIR = 3          # 每个目录放几个文件（测试会遍历整个目录，太多会很慢）
NEEDS_GRID = {"S21power2d", "S21zpa2d"}

# 实验类型 -> 测试期望的 base_dir（相对 vendor/QubitClient）
MAP = {
    "S21":           ["tmp/data/s21", "tmp/data/s21peak"],
    "Spectroscopy":  ["tmp/data/spectrum"],
    "S21zpa2d":      ["tmp/data/s21vsflux", "tmp/data/spectrum2d", "tmp/data/t12d"],
    "S21power2d":    ["tmp/data/powershift"],
    "T1":            ["tmp/data/t1"],
    "Ramsey df":     ["tmp/data/ramsey", "tmp/data/t2"],
    "PiPulse":       ["tmp/data/rabi"],
    "PiPulse df":    ["tmp/data/drag"],
    "IQraw":         ["tmp/data/singleshot"],
    # 下面两个是实测出来的：optreadfreq_convert 要 f3/f4/f7/f8/f9，
    # t12dfit_convert 要 f3 且需要 ZPA 轴，所以 AlphaFine / T1 都不匹配。
    "IQcenter spectroscopy": ["tmp/data/optreadfreq"],
    "PiAmpFine":     ["tmp/data/opt_pipulse"],
    "SpinEchoCPMG":  ["data/spin_echo_lqcs"],
    "TimingXYZ":     ["data/XYZ_Timing_lqcs"],
    "XEB reference": ["data/RB"],
}


def exp_name(basename: str) -> str:
    """`00003 - qXXX%c S21power2d` -> `S21power2d`"""
    return basename.split("%c", 1)[-1].strip() if "%c" in basename else ""


def is_complete_grid(path: str) -> bool:
    """行数是否等于「唯一 f0 数 × 唯一 f1 数」——不满足就 reshape 必崩。"""
    try:
        with h5py.File(path, "r") as h:
            dv = h["DataVault"]
            if not dv.dtype.names or "f1" not in dv.dtype.names:
                return True
            d = dv[()]
        f0 = np.asarray(d["f0"], dtype=float)
        f1 = np.asarray(d["f1"], dtype=float)
        return len(f0) == len(np.unique(f0)) * len(np.unique(f1))
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="把 offline_data 灌进 lqcs 测试的数据目录")
    ap.add_argument("--clean", action="store_true", help="先清空目标目录")
    ap.add_argument("--list", action="store_true", help="只打印，不动文件")
    args = ap.parse_args()

    src = next((d for d in SRC_CANDIDATES if os.path.isdir(d)), None)
    if not src:
        print("找不到 offline_data，试过：\n  " + "\n  ".join(SRC_CANDIDATES), file=sys.stderr)
        return 2
    print(f"数据源: {src}")
    print(f"目标根: {VENDOR}\n")

    # 收集所有 hdf5，按实验类型分组
    by_type: dict[str, list[str]] = {}
    for base, _dirs, files in os.walk(src):
        for fn in files:
            if not fn.endswith(".hdf5"):
                continue
            t = exp_name(os.path.splitext(fn)[0])
            if t in MAP:
                by_type.setdefault(t, []).append(os.path.join(base, fn))

    if args.list:
        for t, dirs in sorted(MAP.items()):
            print(f"  {t:<15} {len(by_type.get(t, [])):>4} 个可用  ->  {', '.join(dirs)}")
        return 0

    total = 0
    for t, dirs in sorted(MAP.items()):
        pool = by_type.get(t, [])
        if t in NEEDS_GRID:
            grid = [p for p in pool if is_complete_grid(p)]
            if len(grid) < len(pool):
                print(f"  [{t}] {len(pool)} 个里有 {len(grid)} 个是完整矩形扫描，其余跳过")
            pool = grid
        if not pool:
            print(f"  [{t}] 没有可用文件，跳过")
            continue

        chosen = sorted(pool)[:PER_DIR]
        for d in dirs:
            dest = os.path.join(VENDOR, d.replace("/", os.sep))
            if args.clean and os.path.isdir(dest):
                shutil.rmtree(dest)
            os.makedirs(dest, exist_ok=True)
            for p in chosen:
                shutil.copy2(p, os.path.join(dest, os.path.basename(p)))
            print(f"  [{t}] -> {d}  放入 {len(chosen)} 个")
            total += len(chosen)

    print(f"\n共复制 {total} 个文件。")
    print("提示：这些目录都在 tmp/ 与 data/ 下，属于可清理的临时数据。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
