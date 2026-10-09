# lqcs 离线推理服务

实验室 NNScope / Scope 推理服务的**本地等价版**，让 `vendor/QubitClient` 的
`tests/skills/lqcs/` 测试在完全离线的机器上也能端到端跑完并出图。

## 为什么需要它

`QubitNNScopeClient` / `QubitScopeClient` 是**远程 HTTP 客户端**，模型在实验室内网
（`<nnscope-host>:9801`）。出了那个网络，所有分析调用都连接超时；而
`qubitclient/wrapper_handler.py` 的 `handle_exceptions` 会把异常吞掉并 `return None`，
于是测试**退出码 0 但什么都没做**——失败只留在 stderr 里。

本服务用传统数值方法（scipy 找峰 / 拟合）复现同一套 HTTP 契约，把这条链路补上。
**它不是神经网络的替代品，精度不等价**，用途是离线开发、回归、画图链路验证。

## 启动

```cmd
D:\访问github\deploy\qmclaw\python.exe offline_service.py --port 9801
```

自检（不启服务，验证分析核心）：

```cmd
D:\访问github\deploy\qmclaw\python.exe offline_service.py --selftest
```

健康检查：`GET http://127.0.0.1:9801/health`

## 让客户端指向它

⚠️ **必须用环境变量**：`qubitclient/utils/env_load.py:105` 的最低优先级配置源是
`from .. import config`，即 `qubitclient/config.py` —— 这个文件**不存在**，
所以仓库根那个写着实验室地址的 `config.py` 永远不会被读到。

```cmd
set QUBITCLIENT_URL=http://127.0.0.1:9801
set QUBITCLIENT_API_KEY=offline
```

也可以在某次运行的**当前目录**放 `qubitclient.json`（`{"url": "...", "api_key": "..."}`）。
因为读取路径是 `Path.cwd()/"qubitclient.json"`，测试又都用相对数据目录，
所以一律**从 `vendor/QubitClient` 根目录**启动测试。

## 协议（自客户端源码逆向）

| | NNScope | Scope |
|---|---|---|
| 端点 | `POST /api/v1/tasks/nnscope/<task>` | `POST /api/v1/tasks/scope/<task>?type=<task>` |
| multipart 字段名 | `request` | `files` |
| 鉴权 | `Authorization: Bearer <key>` | 同左 |
| 响应外壳 | `{"result": [...]}` | `{"results": [...]}` |

上传体统一是以 `np.save` 写出的桩对象：

```python
{"image": {qubit_name: (freq, amp, phi), ...}}     # 各任务元组含义见 analysis/format.py
```

响应数组按 **文件** 分组，元素内部再按 **qubit** 分组。注意 `peaks` 是
**采样点下标**而非频率值（绘图器写的是 `x[peak]`）。

## 已实现的任务

| 通道 | 任务（端点） | 输入元组 | 输出键 | 实现方式 |
|---|---|---|---|---|
| nnscope | `s21peak` | `(freq, amp, phi)` | `peaks` / `confs` / `freqs_list` | `-amp` 上找下凹 |
| nnscope | `s21peakmulti` | 同上 | 同上 | 同上 |
| nnscope | `spectrum` | `(freq, amp)` | `peaks_list` / `confidences_list` / `peak_start` / `peak_end` | 一维找峰 |
| scope | `s21peak` | `(freq, amp, phi)` | `peaks` / `confs` / `freqs_list` | 同上 |
| scope | `s21peakmulti` | 同上 | 同上 | 同上 |
| scope | `spectrum` | `(freq, amp)` | `peaks_list` / `confidences_list` / `mean_cut_widths_list` | 同上 |
| scope | `t1fit` | `(delay, p_x)` | `params_list` / `r2_list` / `fit_data_list` / `fit_data_dense_list` / `x_dense_list` | `A·exp(-t/T)+B` 拟合 |
| scope | `t2fit` | `(delay, amplitude)` | 同 t1fit | 阻尼余弦拟合 |
| scope | `ramsy` | `(delay, amplitude)` | `params_list` / `r2_list` / `fit_data_list` | 阻尼余弦拟合 |
| scope | `spinecho` | `(delay, amplitude)` | 8 个平行列表（见下） | 阻尼余弦拟合 + 包络 |
| scope | `timingxyz` | `(amp, delay)` ⚠️顺序相反 | 7 个平行列表（见下） | 阻尼余弦拟合 + 零交叉 |
| scope / nnscope | `powershift` | `(freq, volt, amp_2d)` ⚠️复振幅 | `q_list` / `keypoints_list` / `confs` / `class_num_list` | 逐电压列找下凹连成折线 |
| scope | `s21vflux` | `(freq, volt, amp_2d)` | `coscurves_list` / `cosconfs_list` / `lines_list` / `lineconfs_list` | 逐电压列找下凹连成轨迹 |
| nnscope | `s21vflux` | 同上 | `params_list` / `linepoints_list` / `confidence_list` / `class_ids` / `curve_type` | 同左 |
| scope | `spectrum2d` | `(amp_2d, zpa, freq)` ⚠️实数图 | `params` / `confs` / `coscompress_list` / `lines_list` / `lineconfs_list` | 逐 zpa 列找峰连成轨迹 |
| nnscope | `seglines` | 同上 | `params_list` / `linepoints_list` / `confidences_list` / `class_ids_list` / `curve_type_list` | 同左 |
| scope | `singleshot` | `(s0, s1)` 复数 IQ | `sep_score_list` / `threshold_list` / `phi_list` / `signal_list` / `idle_list` / `params_list` / `std_list` / `cdf_list` | 旋转投影 + 阈值 + 经验 CDF |

注意这几个坑：
- **`confs` 是「每个 qubit 一个浮点」**，不是每个 qubit 一组。postprocess 会把它转成
  一维数组当掩码用（`confs_arr >= threshold`），传成二维直接形状不匹配。
- **NN 侧 powershift 绘图器的 cv2.flip bug（已修）**：`powershiftnnscopepltplotter.py:119`
  和 `powershiftnnscopeplyplotter.py:102` 原本对**复数**数组调用 `cv2.flip(data, 0)`，
  OpenCV 不支持复数 → `error: (-5:Bad argument) in function 'flip'`（scope 侧同名绘图器
  写的是 `np.abs(values)` 所以没事）。已改为 `np.ascontiguousarray(np.flip(data, 0))`。
  ⚠️ 这是 vendor 代码改动，而 `vendor/QubitClient` 是没有 `.git` 的子模块，改动不会进
  `git status`、也提交不了 —— 换机器/重新解压 vendor.zip 后会丢。
- **multipart 里的非文件字段**：nnscope 的 `request_task` 会带 `data={"curve_type": ...}`，
  当它**非 None** 时（`s21vflux`、`seglines` 会传 `CurveType.COSINE`）requests 就会真的
  发一个 `curve_type` 表单字段，它**没有 filename**。若把它当文件去 `np.load` 会失败，
  并往结果列表里多塞一个空元素，导致 postprocess 在第二项上索引失败
  （典型报错 `KeyError: 'params_list'`）。本服务只收带 filename 的部分。
  `s21peak` 之所以没暴露这个问题，是因为 requests 会跳过值为 `None` 的字段。
- **ramsey 的端点拼写是 `ramsy`**（生成客户端里的原样拼写，别改成 `ramsey`）。
- **`peaks` 的语义按任务不同**：`s21peak` 是**采样点下标**（绘图器写 `x[peak]`）；
  `spectrum` 是**频率值**（绘图器写 `amp[argmin(|x-p|)]`）。
- **元组顺序各任务不一样**：`t1fit`/`t2fit`/`spinecho` 是 `(x, y)`；
  `timingxyz` 是 `(amp, delay)` 且 delay 已在 convert 里换算成秒；
  `s21vsflux` 是 `(freq, volt, amp_2d)`；`spectrum2d` 是 `(amp_2d, zpa, freq)`。
- **标量 vs 数组**：`timingxyz` 的 `zd_xy_list[q]` 是**标量**（绘图器写 `zd_xy*1e-9`
  和 `:.3f` 格式化），传数组会报 `can't multiply sequence by non-int of type 'float'`。
- **`zip` 截断**：`spinecho` 的 postprocess `zip` 了 **8 个**列表、`timingxyz` **7 个**、
  `t1fit`/`t2fit` **5 个**、`spectrum` **3 个** —— 少一个就整体空转且不报错。

spinecho 的 8 个键：`params_list`、`fit_envelope_list`、`r2_list`、`x_out_list`、
`amp_out_list`、`envelope_list`、`success_list`、`t2_list`。
timingxyz 的 7 个键：`params_list`、`fit_data_list`、`r2_list`、`x_out_list`、
`amp_out_list`、`success_list`、`zd_xy_list`。

其余端点返回 **501 + 明确的 JSON 说明**，不会再静默通过。

已验证跑通并出图的测试（**21 个**）：`test_s21peak`、`test_s21peakmulti`、`test_nns21peak`、
`test_spectrum`、`test_nnspectrum`、`test_t1fit`、`test_t2fit`、`test_ramsey`、
`test_spinecho`、`test_timingxyz`、`test_powershift`、`test_nnpowershift`、
`test_s21vsflux`、`test_nns21vsflux`、`test_spectrum2d`、`test_nnspectrum2d`、
`test_singleshot`、`test_rb`、`test_rabicos`、`test_optreadfreq`、`test_t12dfit`。

剩下 4 个（`test_delta` / `test_drag` / `test_optpipulse` / `test_pkl_convert`）跑不了的原因
**与离线无关**：`inception.py` 里 `delta` / `allxy_drag` 被注释、`optpipulse` 不存在，
`format.py` 里没有 `optpipulse_convert`；而 `Delta` 类型的数据在 `offline_data` 里也没有。
属于 vendor 快照本身不完整。

## 配套脚本（把环境变成可重建的）

| 脚本 | 作用 |
|---|---|
| `offline_service.py` | 本服务 |
| `populate_data.py` | 把 `deploy/offline_data` 按实验类型灌进测试的数据目录。**会优先挑完整矩形扫描**的 2D 文件（行数 = 唯一频率数 × 唯一扫描轴数），否则 `powershift_convert` 的 reshape 必崩。`--clean` 先清空，`--list` 只看映射 |
| `apply_vendor_fixes.py` | 重新应用 vendor 里必须的补丁：powershift 的 `cv2.flip` → `np.flip`（2 个文件），以及 `test_rb`/`test_rabicos` 的死 gate（`data.get("name")` → 去掉这个恒 False 的判断）。`--check` 只检查，退出码非 0 表示有未应用项，可挂到 CI |

`apply_vendor_fixes.py` 存在的原因：`vendor/QubitClient` 是**没有 `.git` 的子模块**，
在里面改的代码父仓库看不见、提交不了，重新解压 `vendor.zip` 就会丢。所以把改动写成
「坏模式 → 好模式」的替换规则，随时可重放（比 `.patch` 更耐操，不依赖行号上下文）。

## 扩展新任务

两步：

1. 在 `analysis/format.py` 里找到该任务的 `*_convert`，确认 `image` 里元组的含义。
2. 在 `item_for_file()` 里加一个分支，产出绘图器要读的键。

各任务绘图器实际读取的键（扫 `qubitclient/draw/**/*pltplotter.py` 得到）：

| 任务 | 必需响应键 |
|---|---|
| `s21peak` / `s21peakmulti` | `peaks`, `confs`, `freqs_list` |
| `spectrum` / `nnspectrum` | `peaks_list`, `confidences_list` |
| `powershift` / `nnpowershift` | `keypoints_list`, `class_num_list`, `confs` |
| `t1fit` / `t2fit` | `params_list`, `r2_list`, `fit_data_dense_list`, `x_dense_list` |
| `ramsey` | `params_list`, `r2_list`, `fit_data_list` |
| `t12dfit` | `t1_list`, `zpa_list` |
| `spinecho` | `fit_envelope_list`, `r2_list`, `t2_list`, `x_out_list` |
| `timingxyz` | `fit_data_list`, `r2_list`, `zd_xy_list`, `x_out_list` |
| `rb` / `xeb` | `params_list`, `r2_list`, `fit_data_dense_list`, `x_dense_list` |
| `singleshot` | `sep_score_list`, `threshold_list`, `phi_list`, `signal_list`, `idle_list`, `params_list`, `std_list`, `cdf_list` |
| `rabicos` | `peaks`, `confs` |
| `optreadfreq` | `peak_list` |
| `s21vflux` | `curves_list` / `confs_list` / `lines_list` / `lineconfs_list`（scope 前缀 `cos`）|
| `drag` | `x_pred_list`, `y0_pred_list`, `y1_pred_list`, `intersections_list`, `intersections_confs_list` |
| `delta` / `optpipulse` | `params`, `confs` |

注意 scope 通道的 `postprocess.py` 会在透传前**先过滤**（多数用 `r2` 或置信度阈值），
所以扩展时要保证被过滤字段有合理取值，否则结果会被整条丢掉并置 `status="failed"`。

## 已知限制

- **置信度是启发式的**：`1 - exp(-prominence / (0.25 * ptp(y)))`，单调有界、不饱和。
  实测真实数据：S21 约 0.36 ~ 0.53，频谱约 0.86 ~ 0.98。分布与真实 NN 不同，
  会影响 `threshold`（nnscope 用 0.3、scope 用 0.1）过滤后留下的峰值个数。
  调松/调紧改 `detect_s21_peaks()` / `detect_spectrum_peaks()` 里的分母。
  （早先用 `prominence/(0.5*span)` 会在频谱上全部顶到 1.0000，阈值过滤失去意义。）
- **时间轴单位**：`t1fitpltplotter.py` 打印 `T₁ = {T1*1e6:.1f} µs`，把 T1 当成**秒**。
  `offline_data` 里 T1 数据的时间轴是**纳秒**，所以图上会出现 `T₁ = 63391617414.4 µs`
  这种数字 —— 实际是 63391 ns ≈ 63.4 µs，**拟合本身是对的，只是标注单位不对**。
- **只做了下凹检测**：`|S21|` 的谐振是下凹，故对 `-amp` 找峰。若数据本身是倒过来的
  （`spectrum_convert` 会自动翻转，`s21_convert` 不会），结果会不对。
- 边缘处的下凹（如首尾采样点）不会被 `find_peaks` 识别，因为缺少邻点。
- 一个都没找到时会退化为「全局最低点 + 置信度 0.40」并在日志里体现。
- 拟合对初值敏感：阻尼余弦会先扫一遍候选频率（FFT 主峰 + span 的 1/2/3/5/8 分之一），
  Ramsey/T2 数据点少或信噪比差时 R² 会明显下降。

## 排错

- **测试 exit=0 但没出图** → 先看 stderr 里有没有 `Error occurred in xxx:`。
  退出码在这些测试里没有意义。
- **提示 `URL configuration is required`** → 环境变量没设，或没从
  `vendor/QubitClient` 根目录运行。
- **返回 501** → 该任务还没在 `SUPPORTED` 里实现。
- **返回 401** → `Authorization: Bearer <key>` 缺失或为空。
