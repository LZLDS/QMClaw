# -*- coding: utf-8 -*-
"""
lqcs 离线推理服务 —— 实验室 NNScope / Scope 服务的本地等价版。

背景
----
vendor/QubitClient 里的 QubitNNScopeClient / QubitScopeClient 是**远程 HTTP 客户端**，
真正的模型在实验室内网（默认 <nnscope-host>:9801）。出了实验室网络，所有分析调用都会
连接超时，而 analysis/inception.py 的 handle_exceptions 又会把异常吞掉，导致测试
"exit=0 但什么都没做"。

本服务用传统数值方法（scipy 找峰 / 拟合）在本机复现同一套 HTTP 契约，让 lqcs 的测试
在完全离线的情况下能端到端跑完并出图。它**不是**神经网络的替代品，精度不等价；
用途是离线开发、回归与画图链路验证。

协议（从客户端源码逆向得到）
--------------------------
NNScope:  POST {url}/api/v1/tasks/nnscope/<task>
          multipart 字段名 "request"，Authorization: Bearer <key>
          响应外壳 {"result": [...]}

Scope:    POST {url}/api/v1/tasks/scope/<task>?type=<task>
          multipart 字段名 "files"，  Authorization: Bearer <key>
          响应外壳 {"results": [...]}

上传体统一是以 np.save 写出的桩对象：
    {"image": {qubit_name: (freq, amp, phi), ...}}
响应元素按 **文件** 分组，每个文件的元素内部再按 **qubit** 分组：
    {"peaks": [[下标, ...], ...],        # 注意是采样点下标，不是频率
     "confs": [[置信度, ...], ...],
     "freqs_list": [[频率, ...], ...],
     "status": "success"}

运行
----
    python offline_service.py                 # 监听 127.0.0.1:9801
    python offline_service.py --port 9801
    python offline_service.py --selftest      # 不启服务，跑一遍内置自检

客户端指向本服务：
    set QUBITCLIENT_URL=http://127.0.0.1:9801
    set QUBITCLIENT_API_KEY=offline
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

try:
    from scipy.optimize import curve_fit
    from scipy.signal import find_peaks, peak_widths
except ImportError:  # pragma: no cover
    print("需要 scipy：deploy 环境的 python 里已自带", file=sys.stderr)
    raise

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9801

# --------------------------------------------------------------------------
# 多部分表单解析（只用标准库，避免依赖 cgi / python-multipart）
# --------------------------------------------------------------------------


def parse_multipart(body: bytes, boundary: bytes):
    """返回 [(field_name, filename, payload_bytes), ...]"""
    parts = []
    for chunk in body.split(b"--" + boundary):
        if not chunk or chunk[:2] == b"--":
            continue
        chunk = chunk.lstrip(b"\r\n")
        head, sep, data = chunk.partition(b"\r\n\r\n")
        if not sep:
            continue
        if data.endswith(b"\r\n"):
            data = data[:-2]
        name = filename = None
        m = re.search(rb'name="([^"]*)"', head)
        if m:
            name = m.group(1).decode("utf-8", "replace")
        m = re.search(rb'filename="([^"]*)"', head)
        if m:
            filename = m.group(1).decode("utf-8", "replace")
        parts.append((name, filename, data))
    return parts


def boundary_of(content_type: str) -> bytes | None:
    m = re.search(r'boundary="?([^";]+)"?', content_type or "")
    return m.group(1).encode() if m else None


# --------------------------------------------------------------------------
# 上传体解码
# --------------------------------------------------------------------------


def decode_payload(blob: bytes):
    """把上传的 .npy 还原成 {"image": {qubit: (freq, amp, phi)}}。

    返回 (payload, error_message)。
    """
    try:
        arr = np.load(io.BytesIO(blob), allow_pickle=True)
    except Exception as exc:
        return None, f"np.load 失败: {exc}"
    obj = arr.item() if isinstance(arr, np.ndarray) and arr.dtype == object else arr
    if not isinstance(obj, dict):
        return None, f"载荷不是 dict，而是 {type(obj).__name__}"
    if "image" not in obj:
        return None, f"载荷缺少 'image' 键，实际键: {list(obj.keys())}"
    return obj, None


def iter_images(payload: dict):
    """产出 (qubit_name, item)。item 是各任务自己的元组，长度随任务而定：
    S21 系是 (freq, amp, phi)，T1/T2 是 (x, y)，频谱是 (freq, amp)。
    """
    image = payload.get("image") or {}
    if not isinstance(image, dict):
        return
    for name, item in image.items():
        yield str(name), item


def as_arrays(item, n=2):
    """取元组前 n 项转成 float 数组；长度不够或类型不对返回 None。"""
    try:
        if item is None or len(item) < n:
            return None
        return [np.asarray(item[i], dtype=float) for i in range(n)]
    except Exception:
        return None


# --------------------------------------------------------------------------
# 分析核心：S21 谐振峰（|S21| 上的下凹）
# --------------------------------------------------------------------------


def detect_s21_peaks(freq: np.ndarray, amp: np.ndarray, max_peaks: int = 5):
    """在 |S21| 曲线上找谐振下凹，返回 (下标, 置信度, 频率)。"""
    n = int(min(len(freq), len(amp)))
    if n < 5:
        return [], [], []
    x = freq[:n]
    y = amp[:n]
    y = y[np.isfinite(y)]
    if y.size < 5:
        return [], [], []

    span = float(np.ptp(y))
    if not np.isfinite(span) or span <= 0:
        span = 1.0

    # 谐振是 |S21| 的下凹，取负值后就是峰
    inv = -y
    idx, props = find_peaks(inv, prominence=0.05 * span)
    if idx.size == 0:  # 放宽一次
        idx, props = find_peaks(inv, prominence=0.02 * span)

    if idx.size == 0:
        # 兜底：取全局最低点，置信度压低
        k = int(np.argmin(y))
        return [k], [0.40], [float(x[k])]

    # 1-exp(-p/(0.25*span))：单调、有界、不饱和，比直接按比例更容易拉开差距
    confs = 1.0 - np.exp(-props["prominences"] / (0.25 * span))
    order = np.argsort(confs)[::-1][:max_peaks]
    idx = idx[order]
    confs = confs[order]
    return idx.astype(int).tolist(), confs.astype(float).tolist(), [float(x[i]) for i in idx]


# --------------------------------------------------------------------------
# 各任务的响应构造
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# 拟合辅助（T1 指数衰减 / T2·Ramsey 阻尼余弦）
# --------------------------------------------------------------------------


def r_squared(y, y_fit):
    y = np.asarray(y, dtype=float)
    y_fit = np.asarray(y_fit, dtype=float)
    ss_res = float(np.sum((y - y_fit) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return max(0.0, 1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0


def clean_xy(x, y):
    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    n = min(x.size, y.size)
    x, y = x[:n], y[:n]
    m = np.isfinite(x) & np.isfinite(y)
    return x[m], y[m]


def fit_exp_decay(x, y):
    """A*exp(-x/T) + B。返回 ([A, T, B], r2, callable) 或 None。"""
    x, y = clean_xy(x, y)
    if x.size < 5:
        return None
    A0 = float(y[0] - y[-1]) or 1.0
    B0 = float(y[-1])
    T0 = float((x.max() - x.min()) / 3.0) or 1.0
    try:
        p, _ = curve_fit(lambda t, A, T, B: A * np.exp(-t / T) + B,
                         x, y, p0=[A0, T0, B0], maxfev=40000,
                         bounds=([-np.inf, 1e-12, -np.inf], [np.inf, np.inf, np.inf]))
    except Exception:
        return None
    A, T, B = (float(v) for v in p)
    T = abs(T) or 1e-9
    f = lambda t: A * np.exp(-t / T) + B  # noqa: E731
    return [A, T, B], r_squared(y, f(x)), f


def fit_damped_cosine(x, y):
    """A*exp(-x/T2)*cos(2*pi*w*x + phi) + B。返回 (A, B, T2, w, phi, r2, callable) 或 None。"""
    from numpy.fft import rfft, rfftfreq

    x, y = clean_xy(x, y)
    if x.size < 8:
        return None
    B0 = float(np.mean(y))
    A0 = float(np.ptp(y)) / 2.0 or 1.0
    T0 = float(x.max() - x.min()) or 1.0
    span = float(x.max() - x.min()) or 1.0

    cands = []
    try:
        dx = float(np.median(np.diff(x))) or 1.0
        fr = rfftfreq(x.size, d=dx)
        sp = np.abs(rfft(y - B0))
        if sp.size > 1:
            cands.append(float(fr[int(np.argmax(sp[1:])) + 1]))
    except Exception:
        pass
    cands += [k / span for k in (1, 2, 3, 5, 8)]

    best = None
    for w0 in cands:
        if not np.isfinite(w0) or w0 <= 0:
            continue
        try:
            p, _ = curve_fit(
                lambda t, A, B, T, w, phi: A * np.exp(-t / T) * np.cos(2 * np.pi * w * t + phi) + B,
                x, y, p0=[A0, B0, T0, w0, 0.0], maxfev=40000,
                bounds=([-np.inf, -np.inf, 1e-12, 0.0, -np.inf],
                        [np.inf, np.inf, np.inf, np.inf, np.inf]))
        except Exception:
            continue
        A, B, T, w, phi = (float(v) for v in p)
        T, w = abs(T) or 1e-9, abs(w)
        r2 = r_squared(y, A * np.exp(-x / T) * np.cos(2 * np.pi * w * x + phi) + B)
        if best is None or r2 > best[5]:
            best = (A, B, T, w, phi, r2)
    if best is None:
        return None
    A, B, T, w, phi, r2 = best
    f = lambda t: A * np.exp(-t / T) * np.cos(2 * np.pi * w * t + phi) + B  # noqa: E731
    return A, B, T, w, phi, r2, f


def detect_spectrum_peaks(x, y, max_peaks=5):
    """一维频谱找峰。注意：绘图器把 peaks 当**频率值**用（amp[argmin(|x-p|)]），
    和 s21peak 用采样下标的约定不同。返回 (频率, 置信度, 半高宽)。"""
    x, y = clean_xy(x, y)
    if x.size < 5:
        return [], [], []
    span = float(np.ptp(y)) or 1.0
    idx, props = find_peaks(y, prominence=0.05 * span)
    if idx.size == 0:
        idx, props = find_peaks(y, prominence=0.02 * span)
    if idx.size == 0:
        k = int(np.argmax(y))
        return [float(x[k])], [0.40], [0.0]
    confs = 1.0 - np.exp(-props["prominences"] / (0.25 * span))
    try:
        w_samples = peak_widths(y, idx, rel_height=0.5)[0]
        dx = abs(float(np.median(np.diff(x)))) if x.size > 1 else 1.0
        widths = np.abs(w_samples) * dx
    except Exception:
        widths = np.zeros_like(confs)
    order = np.argsort(confs)[::-1][:max_peaks]
    return ([float(x[i]) for i in idx[order]],
            confs[order].astype(float).tolist(),
            widths[order].astype(float).tolist())


# --------------------------------------------------------------------------
# 各任务的响应构造
# --------------------------------------------------------------------------


def _s21_item(payload):
    peaks, confs, freqs = [], [], []
    for _name, item in iter_images(payload):
        arr = as_arrays(item, 3)
        if arr is None:
            peaks.append([]), confs.append([]), freqs.append([])
            continue
        p, c, fr = detect_s21_peaks(arr[0], arr[1])
        peaks.append(p), confs.append(c), freqs.append(fr)
    return {"peaks": peaks, "confs": confs, "freqs_list": freqs, "status": "success"}


def _spectrum_item(payload, channel):
    peaks, confs, widths = [], [], []
    for _name, item in iter_images(payload):
        arr = as_arrays(item, 2)
        if arr is None:
            peaks.append([]), confs.append([]), widths.append([])
            continue
        p, c, w = detect_spectrum_peaks(arr[0], arr[1])
        peaks.append(p), confs.append(c), widths.append(w)
    if channel == "nnscope":
        # nnscope 侧 postprocess 按 confidences_list 定位，并读 peak_start/peak_end
        return {"peaks_list": peaks, "confidences_list": confs,
                "peak_start": peaks, "peak_end": peaks, "status": "success"}
    # scope 侧 postprocess 会 zip 三个列表，mean_cut_widths_list 不能省
    return {"peaks_list": peaks, "confidences_list": confs,
            "mean_cut_widths_list": widths, "status": "success"}


def _t1fit_item(payload):
    params_l, r2_l, fit_l, dense_l, xdense_l = [], [], [], [], []
    for _name, item in iter_images(payload):
        arr = as_arrays(item, 2)
        got = fit_exp_decay(arr[0], arr[1]) if arr else None
        if not got:
            params_l.append([]), r2_l.append([]), fit_l.append([]), dense_l.append([]), xdense_l.append([])
            continue
        params, r2, f = got
        x = arr[0]
        xd = np.linspace(float(np.min(x)), float(np.max(x)), 200)
        params_l.append(params)          # 绘图器解包 A, T1, B
        r2_l.append(float(r2))
        fit_l.append(f(x).tolist())      # scope postprocess 会 zip 五个列表，这个不能省
        dense_l.append(f(xd).tolist())
        xdense_l.append(xd.tolist())
    return {"params_list": params_l, "r2_list": r2_l, "fit_data_list": fit_l,
            "fit_data_dense_list": dense_l, "x_dense_list": xdense_l, "status": "success"}


def _t2fit_item(payload):
    params_l, r2_l, fit_l, dense_l, xdense_l = [], [], [], [], []
    for _name, item in iter_images(payload):
        arr = as_arrays(item, 2)
        got = fit_damped_cosine(arr[0], arr[1]) if arr else None
        if not got:
            params_l.append([]), r2_l.append([]), fit_l.append([]), dense_l.append([]), xdense_l.append([])
            continue
        A, B, T, w, phi, r2, f = got
        x = arr[0]
        xd = np.linspace(float(np.min(x)), float(np.max(x)), 200)
        params_l.append([A, B, T, T, w, phi])   # 绘图器解包 A, B, T1, T2, w, phi
        r2_l.append(float(r2))
        fit_l.append(f(x).tolist())
        dense_l.append(f(xd).tolist())
        xdense_l.append(xd.tolist())
    return {"params_list": params_l, "r2_list": r2_l, "fit_data_list": fit_l,
            "fit_data_dense_list": dense_l, "x_dense_list": xdense_l, "status": "success"}


def _ramsey_item(payload):
    params_l, r2_l, fit_l = [], [], []
    for _name, item in iter_images(payload):
        arr = as_arrays(item, 2)
        got = fit_damped_cosine(arr[0], arr[1]) if arr else None
        if not got:
            params_l.append([]), r2_l.append([]), fit_l.append([])
            continue
        A, B, T, w, phi, r2, f = got
        params_l.append([A, B, w, phi, T])      # 绘图器解包 A, B, freq, phi, T2
        r2_l.append(float(r2))
        fit_l.append(f(arr[0]).tolist())        # ramsey 用的是 fit_data_list，没有 dense
    return {"params_list": params_l, "r2_list": r2_l, "fit_data_list": fit_l, "status": "success"}


def _spinecho_item(payload):
    """输入同 t2fit：(delay, amplitude)。postprocess 会 zip 8 个平行列表，一个都不能省。"""
    keys = ["params_list", "fit_envelope_list", "r2_list", "x_out_list",
            "amp_out_list", "envelope_list", "success_list", "t2_list"]
    out = {k: [] for k in keys}
    for _name, item in iter_images(payload):
        arr = as_arrays(item, 2)
        got = fit_damped_cosine(arr[0], arr[1]) if arr else None
        if not got:
            for k in keys:
                out[k].append([])
            continue
        A, B, T, w, phi, r2, f = got
        x = arr[0]
        xd = np.linspace(float(np.min(x)), float(np.max(x)), 200)
        envelope = np.abs(A) * np.exp(-xd / T)
        out["params_list"].append([A, B, T, w, phi])
        out["fit_envelope_list"].append(envelope.tolist())
        out["r2_list"].append(float(r2))
        out["x_out_list"].append(xd.tolist())
        out["amp_out_list"].append(f(xd).tolist())
        out["envelope_list"].append(envelope.tolist())
        out["success_list"].append(True)
        out["t2_list"].append(float(T))
    out["status"] = "success"
    return out


def _zd_xy_ns(w, phi):
    """zd_xy 是**标量**（绘图器写 zd_xy_list[q]*1e-9 和 :.3f 格式化）：
    Z 脉冲包络的零交叉时刻，单位 ns。取拟合余弦的第一个非负零点。"""
    if not np.isfinite(w) or w <= 0:
        return 0.0
    k = int(np.ceil((np.pi / 2 - phi) / np.pi))
    k = max(k, 0)
    t = (np.pi / 2 + k * np.pi - phi) / (2 * np.pi * w)
    return float(max(t, 0.0) * 1e9)


def _timingxyz_item(payload):
    """输入是 (amp, delay) —— 顺序和 t2fit 相反（delay 已被 convert 换算成秒）。"""
    keys = ["params_list", "fit_data_list", "r2_list", "x_out_list",
            "amp_out_list", "success_list", "zd_xy_list"]
    out = {k: [] for k in keys}
    for _name, item in iter_images(payload):
        arr = as_arrays(item, 2)
        got = fit_damped_cosine(arr[1], arr[0]) if arr else None
        if not got:
            for k in keys:
                out[k].append([])
            continue
        A, B, T, w, phi, r2, f = got
        x = arr[1]
        xd = np.linspace(float(np.min(x)), float(np.max(x)), 200)
        out["params_list"].append([A, B, T, w, phi])
        out["fit_data_list"].append(f(x).tolist())
        out["r2_list"].append(float(r2))
        out["x_out_list"].append(xd.tolist())
        out["amp_out_list"].append(f(xd).tolist())
        out["success_list"].append(True)
        out["zd_xy_list"].append(_zd_xy_ns(w, phi))
    out["status"] = "success"
    return out


def _powershift_item(payload):
    """输入 (freq, volt, amp_2d)，其中 amp_2d 是**复数**、形状 (n_volt, n_freq)。

    产出结构（scope / nnscope 两侧相同）：
      q_list          每个 qubit 一个名字
      keypoints_list  每个 qubit 一条 [[freq, volt], ...] 折线
      confs           每个 qubit **一个浮点**（postprocess 会把它当一维数组做掩码，
                      传成二维会直接形状不匹配）
      class_num_list  每个 qubit 一个类别号，1 = 单条连通折线
    """
    q_list, keypoints_list, confs, class_list = [], [], [], []
    for name, item in iter_images(payload):
        q_list.append(name)
        try:
            if item is None or len(item) < 3:
                raise ValueError("元组不足 3 项")
            freq = np.asarray(item[0], dtype=float).ravel()
            volt = np.asarray(item[1], dtype=float).ravel()
            amp2d = np.abs(np.asarray(item[2]))       # 复振幅取模
        except Exception:
            keypoints_list.append([])
            confs.append(0.0)
            class_list.append(1)
            continue

        n_volt = int(min(amp2d.shape[0], volt.size))
        pts, cvals = [], []
        for j in range(n_volt):
            col = amp2d[j]
            if col.size == 0:
                continue
            i = int(np.argmin(col))                   # 谐振 = |S21| 的下凹
            if i >= freq.size:
                continue
            span = float(np.ptp(col))
            depth = float(np.max(col) - col[i])
            cvals.append(1.0 - np.exp(-depth / (0.25 * span)) if span > 0 else 0.0)
            pts.append([float(freq[i]), float(volt[j])])
        keypoints_list.append(pts)
        confs.append(float(np.mean(cvals)) if cvals else 0.0)
        class_list.append(1)
    return {"q_list": q_list, "keypoints_list": keypoints_list, "confs": confs,
            "class_num_list": class_list, "status": "success"}


def _flux_trace(freq, volt, amp2d):
    """逐电压列找 |S21| 下凹，连成一条 [[freq, volt], ...] 轨迹，返回 (折线, 置信度)。
    注意 amp_2d 方向是 (n_volt, n_freq)。"""
    n_volt = int(min(amp2d.shape[0], volt.size))
    pts, cvals = [], []
    for j in range(n_volt):
        col = amp2d[j]
        if col.size == 0:
            continue
        i = int(np.argmin(col))
        if i >= freq.size:
            continue
        span = float(np.ptp(col))
        depth = float(np.max(col) - col[i])
        cvals.append(1.0 - np.exp(-depth / (0.25 * span)) if span > 0 else 0.0)
        pts.append([float(freq[i]), float(volt[j])])
    conf = float(np.mean(cvals)) if cvals else 0.0
    return pts, conf


def _s21vflux_item(payload, channel):
    """输入 (unique_freq, unique_volt, amp_2d)（amp_2d 为 (n_volt, n_freq) 的实/复数组）。

    简化说明：真实服务区分「余弦拟合曲线」和「直线段」，这里两者都填检测到的
    谐振轨迹折线，画出来是同一条线。scope / nnscope 的键名不同。
    """
    if channel == "nnscope":
        keys = ["params_list", "linepoints_list", "confidence_list", "class_ids", "curve_type"]
    else:
        keys = ["coscurves_list", "cosconfs_list", "lines_list", "lineconfs_list"]
    out = {k: [] for k in keys}

    for _name, item in iter_images(payload):
        try:
            if item is None or len(item) < 3:
                raise ValueError("元组不足 3 项")
            freq = np.asarray(item[0], dtype=float).ravel()
            volt = np.asarray(item[1], dtype=float).ravel()
            amp2d = np.abs(np.asarray(item[2]))
        except Exception:
            for k in keys:
                out[k].append([])
            continue

        pts, conf = _flux_trace(freq, volt, amp2d)
        if channel == "nnscope":
            out["params_list"].append([[float(np.mean(freq)), 0.0, conf, float(len(pts))]])
            out["linepoints_list"].append([pts])
            out["confidence_list"].append([conf])
            out["class_ids"].append([0])       # 必须在 s21vflux_labels 的索引范围内
            out["curve_type"].append([0])
        else:
            out["coscurves_list"].append([pts])
            out["cosconfs_list"].append([conf])
            out["lines_list"].append([pts])
            out["lineconfs_list"].append([conf])
    out["status"] = "success"
    return out


def _spectrum2d_item(payload, channel):
    """输入 (amp_2d, zpa, freq)，amp_2d 是 (n_freq, n_zpa) 的实数幅度图。

    spectrum2d_convert 已按「峰在下还是在上」把 amp 翻正，所以这里直接找极大值。
    逐 zpa 列找峰，连成一条 [[freq, zpa], ...] 轨迹。
    """
    if channel == "nnscope":
        keys = ["params_list", "linepoints_list", "confidences_list",
                "class_ids_list", "curve_type_list"]
    else:
        keys = ["params", "confs", "coscompress_list", "lines_list", "lineconfs_list"]
    out = {k: [] for k in keys}

    for _name, item in iter_images(payload):
        try:
            if item is None or len(item) < 3:
                raise ValueError("元组不足 3 项")
            amp2d = np.asarray(item[0], dtype=float)
            if amp2d.ndim != 2:
                raise ValueError(f"amp_2d 不是二维: {amp2d.shape}")
            zpa = np.asarray(item[1], dtype=float).ravel()
            freq = np.asarray(item[2], dtype=float).ravel()
        except Exception:
            for k in keys:
                out[k].append([])
            continue

        n_col = int(min(amp2d.shape[1], zpa.size))
        pts, cvals, widths = [], [], []
        for j in range(n_col):
            col = amp2d[:, j]
            if col.size == 0 or not np.any(np.isfinite(col)):
                continue
            i = int(np.nanargmax(col))
            if i >= freq.size:
                continue
            span = float(np.nanmax(col) - np.nanmin(col))
            height = float(col[i] - np.nanmin(col))
            cvals.append(1.0 - np.exp(-height / (0.25 * span)) if span > 0 else 0.0)
            widths.append(float(span))
            pts.append([float(freq[i]), float(zpa[j])])

        conf = float(np.mean(cvals)) if cvals else 0.0
        comp = float(np.mean(widths)) if widths else 0.0
        if channel == "nnscope":
            out["params_list"].append([[float(np.mean(freq)), 0.0, conf, float(len(pts))]])
            out["linepoints_list"].append([pts])
            out["confidences_list"].append([conf])
            out["class_ids_list"].append([0])
            out["curve_type_list"].append([0])
        else:
            out["params"].append([pts])
            out["confs"].append([conf])
            out["coscompress_list"].append([comp])
            out["lines_list"].append([pts])
            out["lineconfs_list"].append([conf])
    out["status"] = "success"
    return out


def _singleshot_item(payload):
    """输入 (s0, s1)：两个态的复数 IQ 点云（IQraw，每文件 3000 点）。

    产出 8 个键，形状按绘图器反推：
      params_list[i]  = [[r0,i0,a0,b0,0,0,phi0], [r1,i1,a1,b1,0,0,phi1]]  （2×7）
      signal_list[i] / idle_list[i] = (投影0, 投影1) 两个实数数组
      cdf_list[i]     = (x, cdf0, cdf1, 平均)
      sep_score_list / threshold_list / phi_list = 标量
    """
    keys = ["sep_score_list", "threshold_list", "phi_list", "signal_list",
            "idle_list", "params_list", "std_list", "cdf_list"]
    out = {k: [] for k in keys}

    for _name, item in iter_images(payload):
        try:
            if item is None or len(item) < 2:
                raise ValueError("元组不足 2 项")
            s0 = np.asarray(item[0]).ravel().astype(complex)
            s1 = np.asarray(item[1]).ravel().astype(complex)
            if s0.size == 0 or s1.size == 0:
                raise ValueError("点云为空")
        except Exception:
            for k in keys:
                out[k].append([])
            continue

        m0, m1 = complex(np.mean(s0)), complex(np.mean(s1))
        d = m1 - m0
        phi = float(np.angle(d)) if abs(d) > 0 else 0.0
        # 旋转到分离方向后投影，阈值取两投影均值的中点
        rot = np.exp(-1j * phi)
        p0, p1 = np.real(s0 * rot), np.real(s1 * rot)
        thr = float((p0.mean() + p1.mean()) / 2.0)
        sd0, sd1 = float(np.std(p0)), float(np.std(p1))
        pooled = float(np.sqrt((sd0 ** 2 + sd1 ** 2) / 2.0)) or 1e-12
        sep = float(abs(p1.mean() - p0.mean()) / pooled)

        r0, i0 = float(np.real(m0)), float(np.imag(m0))
        r1, i1 = float(np.real(m1)), float(np.imag(m1))
        a0, b0 = float(np.std(np.real(s0))), float(np.std(np.imag(s0)))
        a1, b1 = float(np.std(np.real(s1))), float(np.std(np.imag(s1)))

        out["params_list"].append([[r0, i0, a0, b0, 0.0, 0.0, 0.0],
                                   [r1, i1, a1, b1, 0.0, 0.0, 0.0]])
        out["sep_score_list"].append(sep)
        out["threshold_list"].append(thr)
        out["phi_list"].append(phi)
        out["signal_list"].append((p0.tolist(), p1.tolist()))
        out["idle_list"].append((p0.tolist(), p1.tolist()))
        out["std_list"].append([[a0, b0], [a1, b1]])

        lo = float(min(p0.min(), p1.min()))
        hi = float(max(p0.max(), p1.max()))
        xs = np.linspace(lo, hi, 200)
        cdf0 = (np.searchsorted(np.sort(p0), xs) / max(p0.size, 1)).astype(float)
        cdf1 = (np.searchsorted(np.sort(p1), xs) / max(p1.size, 1)).astype(float)
        out["cdf_list"].append((xs.tolist(), cdf0.tolist(), cdf1.tolist(),
                                ((cdf0 + cdf1) / 2.0).tolist()))
    out["status"] = "success"
    return out


def _oscillation_extrema(x, y, max_peaks=6):
    """找振荡的极值点，返回 (横坐标取值列表, 置信度列表)。"""
    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    n = int(min(x.size, y.size))
    x, y = x[:n], y[:n]
    m = np.isfinite(y)
    x, y = x[m], y[m]
    if y.size < 5:
        return [], []
    span = float(np.ptp(y)) or 1.0
    found = []
    for sign in (1.0, -1.0):
        idx, props = find_peaks(sign * y, prominence=0.1 * span)
        if idx.size == 0:
            idx, props = find_peaks(sign * y, prominence=0.03 * span)
        if idx.size:
            found.append((idx, props["prominences"]))
    if not found:
        return [], []
    xs, cs = [], []
    for idx, prom in found:
        for k, i in enumerate(idx):
            xs.append(float(x[i]))
            cs.append(float(1.0 - np.exp(-prom[k] / (0.25 * span))))
    order = np.argsort(cs)[::-1][:max_peaks]
    return [xs[i] for i in order], [cs[i] for i in order]


def _rb_item(payload):
    """输入是**嵌套**的 [x, [y_main, y_ref]]（rb_convert 的产物，不是 2 元组）。

    拟合 A*exp(-t/T)+B 后把 T 换算成 RB 常用的退相干参数 p = exp(-1/T)，
    因为绘图器按 `A, p, B` 解包。
    """
    keys = ["params_list", "r2_list", "fit_data_list", "fit_data_dense_list", "x_dense_list"]
    out = {k: [] for k in keys}
    for _name, item in iter_images(payload):
        try:
            if item is None or len(item) < 2:
                raise ValueError("元组不足 2 项")
            x = np.asarray(item[0], dtype=float).ravel()
            yy = item[1]
            y_main = yy[0] if isinstance(yy, (list, tuple, np.ndarray)) and len(yy) >= 1 else yy
            y = np.asarray(y_main, dtype=float).ravel()
        except Exception:
            for k in keys:
                out[k].append([])
            continue
        got = fit_exp_decay(x, y)
        if not got:
            for k in keys:
                out[k].append([])
            continue
        (A, T, B), r2, f = got
        p = float(np.exp(-1.0 / T)) if T > 0 else 0.0
        xd = np.linspace(float(np.min(x)), float(np.max(x)), 200)
        out["params_list"].append([A, p, B])
        out["r2_list"].append(float(r2))
        out["fit_data_list"].append(f(x).tolist())
        out["fit_data_dense_list"].append(f(xd).tolist())
        out["x_dense_list"].append(xd.tolist())
    out["status"] = "success"
    return out


def _rabicos_item(payload):
    """输入 (delay, p6)：Rabi 余弦振荡。

    `peaks` 是**横坐标取值**而不是采样下标 —— 绘图器写的是
    `idx = np.argmin(np.abs(x - p))`，传下标记会画到完全不相关的位置。
    """
    out = {"peaks": [], "confs": []}
    for _name, item in iter_images(payload):
        arr = as_arrays(item, 2)
        if arr is None:
            out["peaks"].append([])
            out["confs"].append([])
            continue
        peaks, confs = _oscillation_extrema(arr[0], arr[1])
        out["peaks"].append(peaks)
        out["confs"].append(confs)
    out["status"] = "success"
    return out


def _optreadfreq_item(payload):
    """输入 (freq, s0, s1)：两态在频率轴上的复数 IQ。

    最优读出频率 = 两态区分度 |s0-s1| 最大处，产出 `peak_list`
    （频率**取值**，与 spectrum 同约定）。
    """
    out = {"peak_list": []}
    for _name, item in iter_images(payload):
        try:
            freq = np.asarray(item[0], dtype=float).ravel()
            s0 = np.asarray(item[1]).ravel().astype(complex)
            s1 = np.asarray(item[2]).ravel().astype(complex)
        except Exception:
            out["peak_list"].append([])
            continue
        n = int(min(freq.size, s0.size, s1.size))
        if n < 3:
            out["peak_list"].append([])
            continue
        dis = np.abs(s0[:n] - s1[:n])
        span = float(np.ptp(dis)) or 1.0
        idx, _props = find_peaks(dis, prominence=0.05 * span)
        if idx.size == 0:
            idx = np.array([int(np.argmax(dis))])
        order = np.argsort(dis[idx])[::-1][:3]
        # peak_list 每个 qubit 放**一个标量下标**（区分度最大的那个点）：
        # 放列表会被 postprocess 转成数组，绘图器 `if peaks:` 时报
        # The truth value of an array with more than one element is ambiguous。
        out["peak_list"].append(int(idx[order][0]))
    out["status"] = "success"
    return out


def _t12dfit_item(payload):
    """输入 (p_arr, delay, zpa)，p_arr 形状 (n_delay, n_zpa)。

    对每个 zpa 列拟合一次 T1，产出平行的 `t1_list` / `zpa_list`。
    """
    out = {"t1_list": [], "zpa_list": []}
    for _name, item in iter_images(payload):
        try:
            if item is None or len(item) < 3:
                raise ValueError("元组不足 3 项")
            parr = np.asarray(item[0], dtype=float)
            delay = np.asarray(item[1], dtype=float).ravel()
            zpa = np.asarray(item[2], dtype=float).ravel()
            if parr.ndim != 2:
                raise ValueError("p_arr 不是二维")
        except Exception:
            out["t1_list"].append([])
            out["zpa_list"].append([])
            continue
        t1s, zpas = [], []
        for j in range(int(min(parr.shape[1], zpa.size))):
            got = fit_exp_decay(delay, parr[:, j])
            if not got:
                continue
            params, r2, _f = got
            if r2 <= 0:
                continue
            t1s.append(float(params[1]))
            zpas.append(float(zpa[j]))
        out["t1_list"].append(t1s)
        out["zpa_list"].append(zpas)
    out["status"] = "success"
    return out


def item_for_file(payload: dict, task: str, channel: str):
    """构造一个文件对应的响应元素（内部按 qubit 分组）。"""
    if task in ("s21peak", "s21peakmulti"):
        return _s21_item(payload)
    if task == "spectrum":
        return _spectrum_item(payload, channel)
    if task == "t1fit":
        return _t1fit_item(payload)
    if task == "t2fit":
        return _t2fit_item(payload)
    if task in ("ramsy", "ramsey"):
        return _ramsey_item(payload)
    if task == "spinecho":
        return _spinecho_item(payload)
    if task in ("timingxyz", "xyz_timing"):
        return _timingxyz_item(payload)
    if task == "powershift":
        return _powershift_item(payload)
    if task == "s21vflux":
        return _s21vflux_item(payload, channel)
    if task in ("spectrum2d", "seglines"):
        return _spectrum2d_item(payload, channel)
    if task == "singleshot":
        return _singleshot_item(payload)
    if task in ("rb", "rbfit"):
        return _rb_item(payload)
    if task in ("rabicos", "rabicospeak"):
        return _rabicos_item(payload)
    if task == "optreadfreq":
        return _optreadfreq_item(payload)
    if task == "t12dfit":
        return _t12dfit_item(payload)
    raise NotImplementedError(f"离线服务尚未实现任务: {channel}/{task}")


def empty_item(task: str, err: str):
    """解码失败时的占位元素，键与任务匹配，避免再引发二次异常。"""
    base = {"status": "failed", "error": err}
    if task in ("s21peak", "s21peakmulti"):
        base.update({"peaks": [], "confs": [], "freqs_list": []})
    elif task == "spectrum":
        base.update({"peaks_list": [], "confidences_list": []})
    return base


def summarize(item: dict) -> str:
    if "peaks" in item:
        return f"qubits={len(item['peaks'])} peaks={sum(len(p) for p in item['peaks'])}"
    if "peaks_list" in item:
        return f"qubits={len(item['peaks_list'])} peaks={sum(len(p) for p in item['peaks_list'])}"
    if "params_list" in item:
        return f"qubits={len(item['params_list'])} fitted={sum(1 for p in item['params_list'] if p)}"
    return "ok"


SUPPORTED = {
    "nnscope": ["s21peak", "s21peakmulti", "spectrum", "powershift", "s21vflux", "seglines"],
    "scope": ["s21peak", "s21peakmulti", "spectrum", "t1fit", "t2fit", "ramsy",
              "spinecho", "timingxyz", "powershift", "s21vflux", "spectrum2d",
              "singleshot", "rb", "rbfit", "rabicos", "rabicospeak",
              "optreadfreq", "t12dfit"],
}


# --------------------------------------------------------------------------
# HTTP 处理
# --------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    server_version = "lqcs-offline/0.1"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # 更紧凑的访问日志
        sys.stdout.write("    [http] " + (fmt % args) + "\n")
        sys.stdout.flush()

    # -- 工具 -------------------------------------------------------------
    def _send(self, code: int, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or not auth[7:].strip():
            return False
        self.token = auth[7:].strip()
        return True

    # -- 路由 -------------------------------------------------------------
    def do_GET(self):
        if self.path.rstrip("/") in ("/health", "/api/v1/health"):
            self._send(200, {"status": "ok", "service": "lqcs-offline", "supported": SUPPORTED})
        else:
            self._send(404, {"detail": "not found"})

    def do_POST(self):
        path = self.path.split("?", 1)[0].rstrip("/")
        m = re.match(r"^/api/v1/tasks/(nnscope|scope)/([A-Za-z0-9_]+)$", path)
        if not m:
            self._send(404, {"detail": f"unknown path: {path}"})
            return
        channel, task = m.group(1), m.group(2).lower()

        if not self._authorized():
            self._send(401, {"detail": "missing or malformed Authorization: Bearer <key>"})
            return

        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        boundary = boundary_of(self.headers.get("Content-Type", ""))
        if not boundary:
            self._send(400, {"detail": "不是 multipart/form-data"})
            return
        # 只收真正的文件部分。nnscope 在 curve_type 非空时会额外带一个**非文件**表单字段
        # （requests 会跳过值为 None 的字段，所以只有 s21vflux/seglines 这类会带）。
        # 把它当文件去 np.load 会失败，并往结果列表里塞一个空元素，导致外层多一项。
        parts = [p for p in parse_multipart(body, boundary)
                 if p[2] and (p[1] is not None or p[0] in ("request", "files"))]
        if not parts:
            self._send(400, {"detail": "multipart 里没有文件内容"})
            return

        if task not in SUPPORTED.get(channel, []):
            self._send(501, {
                "detail": f"离线服务未实现 {channel}/{task}",
                "supported": SUPPORTED.get(channel, []),
            })
            return

        items = []
        try:
            for name, filename, blob in parts:
                payload, err = decode_payload(blob)
                if err:
                    print(f"  !! 字段 {name} ({filename}) 解码失败: {err}", flush=True)
                    items.append(empty_item(task, err))
                    continue
                item = item_for_file(payload, task, channel)
                print(f"  -> {channel}/{task}  field={name}  {summarize(item)}", flush=True)
                items.append(item)
        except NotImplementedError as exc:
            self._send(501, {"detail": str(exc)})
            return
        except Exception as exc:
            traceback.print_exc()
            self._send(500, {"detail": f"离线服务内部错误: {exc}"})
            return

        if channel == "nnscope":
            self._send(200, {"result": items})
        else:
            self._send(200, {"results": items})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow", "POST, GET, OPTIONS")
        self.end_headers()


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------


def selftest() -> int:
    """不启服务，用合成数据验证每个任务的产出结构（键名 + 参数元数）。"""
    ok = True

    xs = np.linspace(6.40, 6.50, 201)
    dip = 1.0 - 0.6 * np.exp(-((xs - 6.452) ** 2) / (2 * 0.004 ** 2))
    it = item_for_file({"image": {"q": (xs, dip, np.zeros_like(xs))}}, "s21peak", "scope")
    hit = bool(it["peaks"][0]) and abs(xs[it["peaks"][0][0]] - 6.452) < 0.005
    print(f"s21peak         peaks={it['peaks'][0]} -> {'OK' if hit else 'FAIL'}")
    ok = ok and hit

    spec = np.exp(-((xs - 6.455) ** 2) / (2 * 0.003 ** 2))
    it = item_for_file({"image": {"q": (xs, spec)}}, "spectrum", "scope")
    hit = bool(it["peaks_list"][0]) and abs(it["peaks_list"][0][0] - 6.455) < 0.005
    print(f"scope spectrum  peaks={it['peaks_list'][0]} -> {'OK' if hit else 'FAIL'}")
    ok = ok and hit

    t = np.linspace(0, 200e-6, 60)
    y = 0.9 * np.exp(-t / 40e-6) + 0.05
    it = item_for_file({"image": {"q": (t, y)}}, "t1fit", "scope")
    p = it["params_list"][0]
    hit = len(p) == 3 and abs(p[1] - 40e-6) / 40e-6 < 0.05 and it["r2_list"][0] > 0.99
    print(f"t1fit           params(3)={['%.3g' % v for v in p]} r2={it['r2_list'][0]:.4f} -> {'OK' if hit else 'FAIL'}")
    ok = ok and hit

    y2 = 0.8 * np.exp(-t / 60e-6) * np.cos(2 * np.pi * (3 / 200e-6) * t + 0.3) + 0.1
    it = item_for_file({"image": {"q": (t, y2)}}, "t2fit", "scope")
    p = it["params_list"][0]
    hit = len(p) == 6 and it["r2_list"][0] > 0.9
    print(f"t2fit           params(6)={['%.3g' % v for v in p]} r2={it['r2_list'][0]:.4f} -> {'OK' if hit else 'FAIL'}")
    ok = ok and hit

    it = item_for_file({"image": {"q": (t, y2)}}, "ramsy", "scope")
    p = it["params_list"][0]
    hit = len(p) == 5 and it["r2_list"][0] > 0.9
    print(f"ramsy           params(5)={['%.3g' % v for v in p]} r2={it['r2_list'][0]:.4f} -> {'OK' if hit else 'FAIL'}")
    ok = ok and hit

    print("自检:", "全部通过" if ok else "有失败")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="lqcs 离线推理服务（实验室 NNScope/Scope 的本地等价版）")
    ap.add_argument("--host", default=os.environ.get("LQCS_OFFLINE_HOST", DEFAULT_HOST))
    ap.add_argument("--port", type=int, default=int(os.environ.get("LQCS_OFFLINE_PORT", DEFAULT_PORT)))
    ap.add_argument("--selftest", action="store_true", help="只跑内置自检，不启动服务")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print("=" * 66)
    print(" lqcs 离线推理服务（本地等价版，非神经网络）")
    print(f" 监听      : http://{args.host}:{args.port}")
    print(f" 已实现    : {json.dumps(SUPPORTED, ensure_ascii=False)}")
    print(" 客户端指向: QUBITCLIENT_URL / QUBITCLIENT_API_KEY")
    print("=" * 66)
    sys.stdout.flush()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n收到中断，退出。")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
