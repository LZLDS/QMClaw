# QMClaw / lqcs 实验离线化 —— 进度与问题报告

| 项目 | 内容 |
|---|---|
| 对象 | `vendor/QubitClient/tests/skills/lqcs/` 下的 25 个测控实验测试 |
| 目标 | 验证「这些实验能否完全离线运行」，并解决阻塞问题 |
| 运行环境 | Windows + `deploy/qmclaw/python.exe`（3.11.16）· 无实验室内网 |
| 当前进度 | **21 / 25 跑通**（起点为 0 / 25） |
| 报告日期 | 2026-09-24 |

---

## 一、结论摘要

**离线运行在技术上完全可行。** 这些实验的分析链路是「本地 HDF5 → 格式转换 → 分析 → 绘图」，其中**唯一的联网环节就是一次 HTTP 推理调用**（发往实验室内网 `<nnscope-host>:9801` 的 NNScope / Scope 服务）。把这一个环节用本地实现替换后，整条链路即可在完全离线的机器上跑完并出图。

已用本地数值方法（scipy 找峰 / 曲线拟合）复现该服务的 HTTP 契约，实现 **14 类任务端点**，使 **21 个测试端到端跑通并产出 40+ 张图**。

**剩余 4 个测试跑不通的原因与离线能力无关** —— 是 vendor 代码快照本身不完整（函数缺失/被注释），即使接上实验室服务同样无法运行。见第五节。

---

## 二、当前进度

### 2.1 逐测试状态

| 分组 | 测试 | 状态 |
|---|---|---|
| S21 谐振峰 | `test_s21peak` · `test_s21peakmulti` · `test_nns21peak` | ✅ |
| 频谱 | `test_spectrum` · `test_nnspectrum` · `test_spectrum2d` · `test_nnspectrum2d` | ✅ |
| 时间域拟合 | `test_t1fit` · `test_t2fit` · `test_ramsey` · `test_spinecho` | ✅ |
| 功率/磁通扫描 | `test_powershift` · `test_nnpowershift` · `test_s21vsflux` · `test_nns21vsflux` | ✅ |
| 其他 | `test_timingxyz` · `test_singleshot` · `test_optreadfreq` · `test_t12dfit` · `test_rb` · `test_rabicos` | ✅ |
| **缺失函数** | `test_delta` · `test_drag` · `test_optpipulse` · `test_pkl_convert` | ❌ |

通过判定标准：`exit=0` **且** stderr 无被吞异常 **且** HTTP 返回 200 **且**产出图文件。仅看 `exit=0` 是不可靠的（见 4.1）。

### 2.2 关键指标

| 指标 | 数值 |
|---|---|
| 测试跑通 | 21 / 25 |
| 已实现任务端点 | 14 类（约 22 个端点名） |
| 离线生成图 | 40+ 张（PNG + HTML） |
| 修复的 vendor 缺陷 | 4 处（均有脚本可重放） |

---

## 三、技术路线

### 3.1 协议逆向

服务端契约无法从文档获得，是从客户端源码逆向出来的。两条独立通道：

| | NNScope | Scope |
|---|---|---|
| 端点 | `POST /api/v1/tasks/nnscope/<task>` | `POST /api/v1/tasks/scope/<task>?type=<task>` |
| multipart 字段名 | `request` | `files` |
| 响应外壳 | `{"result": [...]}` | `{"results": [...]}` |
| 鉴权 | `Authorization: Bearer <key>` | 同左 |

上传体为 pickle 序列化的 `{"image": {qubit: <任务相关元组>}}`；响应按**文件**分组，元素内部再按 **qubit** 分组。

### 3.2 离线推理服务

`tools/lqcs-offline/offline_service.py` —— 用传统数值方法复现上述契约：

- **找峰类**：`s21peak`、`s21peakmulti`、`spectrum`、`powershift`、`s21vflux`、`seglines`、`spectrum2d`、`singleshot`、`optreadfreq`
- **拟合类**：`t1fit`、`t2fit`、`ramsy`、`spinecho`、`timingxyz`、`rb`（`A·exp(-t/T)+B`、阻尼余弦）
- **振荡极值类**：`rabicos`
- 未实现的端点一律返回 **501 + 明确说明**，不静默通过

需要强调：**本服务是启发式等价实现，不是神经网络的替代品**，精度不等价。用途是离线开发、回归测试与绘图链路验证。

### 3.3 环境可重建（两个配套脚本）

| 脚本 | 作用 |
|---|---|
| `populate_data.py` | 按实验类型把 `deploy/offline_data` 灌入测试所需的数据目录；**自动优先挑选完整矩形扫描的 2D 文件** |
| `apply_vendor_fixes.py` | 重放 vendor 补丁；`--check` 模式退出码可用于 CI 防回退 |

### 3.4 方法论：用实测代替猜测

数据映射最初靠「按名字对应」猜测，导致 2 个测试持续报错。改为写探针脚本，把 `offline_data` 中**全部 26 种实验类型**的字段结构列出，并让各转换器**逐个试吃**，直接得出可用组合：

```
optreadfreq_convert 可用类型: ['IQcenter spectroscopy', 'S21_dis']
t12dfit_convert     可用类型: ['CZ Xeb', 'S21power2d', 'S21zpa2d', 'Swap11to20', 'XEB reference']
```

结论：这两个测试**不需要任何新代码，只需换数据**。此方法同样澄清了 `S21power2d` 中 99 个文件有 96 个是完整矩形扫描，此前 reshape 崩溃是选错文件所致。

---

## 四、遇到的主要问题

### 4.1 【严重】异常被静默吞掉，退出码完全不可信

`qubitclient/wrapper_handler.py:18` 的 `handle_exceptions` 捕获所有异常，仅写日志后 `return None`。而 `analysis/inception.py` 给几乎每个任务函数都套了该装饰器。

**后果**：一次完整的分析失败，在测试侧表现为「退出码 0 + 无图 + stderr 两行日志」。实测首次批量运行时，25 个测试中 **19 个 `exit=0`，但只有 3 个真正完成了分析**。更极端的是 `test_nns21peak`：3 个文件全部分析失败，进程仍返回 0，并且照常画出 3 张「原始曲线图」，外观上完全像成功。

**影响**：任何以退出码为判据的 CI 在此项目上都是失效的。

**建议**：让被吞掉的异常反映到退出码（例如装饰器内累加失败计数，`main()` 结束时据此返回非零）；或至少在测试中显式检查 `analysis_result is None`。

### 4.2 【严重】非 200 响应没有任何处理分支

两侧的 postprocess 均假设服务一定返回 200：

- scope 侧 `scope/postprocess.py:63` 直接 `response.parsed.get(...)`，非 200 时 `parsed` 为 `None` → `AttributeError`
- nnscope 侧 `nnscope/postprocess.py:253` 直接 `response.json()["result"]`，错误体无该键 → `KeyError`

任务函数随后被吞成 `None`，绘图函数再抛一次 `TypeError`、**又被吞一次**。
实验室服务大概永远返回 200，所以这条路径从未被走过。

### 4.3 【严重】装饰器使用不一致

`inception.py` 中 `spectrum2d`（第 52 行）与 `nns21vsflux`（第 174 行）**缺少** `@handle_exceptions` / `@control_api_execution`。它们是全部测试中唯二 `exit=1`（异常逃逸）的——同一文件内并存两种错误处理策略。

### 4.4 【已修】三个实质性代码缺陷

| 缺陷 | 位置 | 现象与修法 |
|---|---|---|
| 复数数组传入 OpenCV | `powershiftnnscopepltplotter.py:119`、`powershiftnnscopeplyplotter.py:102` | 对复数映射（`I+1j·Q`）调用 `cv2.flip(data, 0)` → `error: (-5:Bad argument) in function 'flip'`。改为 `np.ascontiguousarray(np.flip(data, 0))`。scope 侧同名绘图器写的是 `np.abs(values)`，故未暴露 |
| 死 gate 导致静默空转 | `test_rb.py:35`、`test_rabicos.py:38` | `if "rb" in data.get("name", "")` —— `utils.get_hdf5_content` 返回 `{Title前缀: 数组}`，**没有 `name` 键**，条件恒为 False，整个循环体从不执行。因 `base_dir` 已按类型分好，正确的修法是移除该内容判断 |
| 非文件表单字段污染请求 | 离线服务自身 | nnscope 客户端在 `curve_type` 非 `None` 时（`s21vflux`/`seglines` 会传 `CurveType.COSINE`）会发送一个**无 filename** 的表单字段；将其当作文件解析会失败并向结果列表多塞一个空元素，导致 postprocess 索引越界（`KeyError: 'params_list'`）。`s21peak` 未暴露是因为 requests 会跳过值为 `None` 的字段 |

### 4.5 协议约定高度不统一，极易写错

| 问题 | 说明 |
|---|---|
| **平行列表 `zip` 截断** | postprocess 用 `zip` 合并 N 个平行列表，**少返回任何一个都会整体空转且不报错**。N 分别为：`spinecho` 8、`timingxyz` 7、`t1fit`/`t2fit` 5、`spectrum` 3 |
| **`peaks` 有四种语义** | `s21peak` 为采样下标列表；`spectrum` 为频率取值列表；`optreadfreq` 为**单个标量下标**；`rabicos` 为取值。传错通常不崩溃，只是画错位置或抛 `IndexError` |
| **元组顺序/结构各异** | `t1fit`/`t2fit`/`spinecho` 为 `(x, y)`；`timingxyz` 为 `(amp, delay)` 且 delay 已换算为秒；`s21vsflux` 为 `(freq, volt, amp_2d)` 而 `spectrum2d` 为 `(amp_2d, zpa, freq)`；`rb` 为嵌套 `[x, [y_main, y_ref]]` |
| **标量 / 数组混用** | `timingxyz` 的 `zd_xy_list[q]` 是标量（绘图器写 `zd_xy*1e-9`）；`powershift` 的 `confs[q]` 是每 qubit 一个浮点，传成二维会使掩码形状不匹配 |
| **拼写不一致** | ramsey 的端点拼写为 `ramsy`；绘图器注册名有 `powershitnnscope`（缺 `f`）、`t12dfit` 注册成 `t1fit` |

### 4.6 数据与配置问题

| 问题 | 说明 |
|---|---|
| **数据契约三套并存** | `tests/skills/lqcs/utils.py` 返回 `{Title: 结构化数组}`，但 `test_rb`/`test_rabicos` 用 `data["name"]`、`test_delta` 用 `data["meta"]["name"]`，而 `utils.py` 只实现了第一种 |
| **配置文件为死代码** | `qubitclient/utils/env_load.py:105` 的最低优先级配置源是 `from .. import config`（即 `qubitclient/config.py`，该文件不存在）。因此仓库根目录中写有实验室地址的 `config.py` **永远不会被读取**，只能通过环境变量或 CWD 下的 `qubitclient.json` 配置 |
| **实验类型与转换器不匹配** | `optreadfreq_convert` 需要 `f3/f4/f7/f8/f9`，`AlphaFine` 只有 `f0-f2`；`t12dfit_convert` 需要 ZPA 轴，`T1` 不匹配。需实测才能确定正确类型 |
| **2D 数据非完整矩形** | `powershift_convert` 以 `unique_freq × unique_volt` 进行 reshape，若扫描不完整则抛 `cannot reshape array of size 184 into shape (15,13)` |

### 4.7 工具链与环境

| 问题 | 说明 |
|---|---|
| **vendor 为无 `.git` 的子模块** | `vendor/QubitClient` 在父仓库中是子模块指针（`160000 3da70fe`），但目录内没有 `.git`，是从 `vendor.zip` 解出的普通副本。**在其中修改的代码父仓库 `git status` 不可见、`git commit` 无法带走，重新解压即丢失** |
| **端口检测 API 不可靠** | `Get-NetTCPConnection` 在本机多次给出假阴性，导致一次服务重启失败却误以为在运行新代码，浪费一轮验证。判断端口应统一使用 `netstat -ano` |
| **沙箱下无法运行 Chromium** | 浏览器多进程架构必须使用命名管道，沙箱禁止 → `FATAL: platform_channel.cc: Check failed`。因此无法产出网页/界面截图，所有可视化均以 matplotlib 生成 |

---

## 五、剩余 4 个测试的详细说明

| 测试 | 阻塞点 | 根因 |
|---|---|---|
| `test_delta` | `ImportError: cannot import name 'delta'` | `inception.py:148-153` 整段被注释；且 `Delta` 类型数据在 `offline_data` 的 26 种类型中**不存在** |
| `test_drag` | `ImportError: cannot import name 'allxy_drag'` | `inception.py:179-184` 整段被注释 |
| `test_optpipulse` | `ImportError: cannot import name 'optpipulse'` | `inception.py` 中从未实现该函数 |
| `test_pkl_convert` | `ImportError: cannot import name 'optpipulse_convert'` | `format.py` 中没有该转换器 |

**判断**：这 4 个属于 vendor 快照与测试集不同步，**与离线/联网无关** —— 接上实验室服务同样无法运行。

**建议处置**（需要确认功能范围后择一）：
1. 若这些功能属于当前版本范围 → 参照 `inception.py` 中被注释的模板补齐 `*_convert` + 任务包装函数；`drag`/`optpipulse` 所需数据大体具备（`PiPulse df`、`PiAmpFine`），`delta` 无对应数据需另行准备
2. 若不属于 → 从测试集中移除，避免持续产生失败噪声

---

## 六、风险与遗留

1. **vendor 改动不可提交**：当前通过 `apply_vendor_fixes.py` 重放 4 处补丁来缓解，但这是**绕过而非解决**。建议将 `vendor/QubitClient` 初始化为真正的 git 子模块，或把这些改动以补丁形式纳入版本管理。
2. **离线服务非等价实现**：置信度采用启发式映射（`1-exp(-prominence/(0.25·span))`），分布与真实神经网络不同，会影响阈值过滤后保留的峰数量。仅适用于链路验证，不可用于物理结论。
3. **时间单位假设不一致**：`t1fitpltplotter.py` 按「秒」格式化 T1（`T1*1e6` 显示为 µs），而离线数据时间轴为纳秒，图上会出现 `T₁ = 63391617414.4 µs` 这类数值——**拟合本身正确**（实际 63391 ns ≈ 63.4 µs），属标注单位问题。
4. **测试数据目录为临时数据**：`tmp/data/*` 由脚本生成，可随时清理重建。
5. **精度未做定量评估**：尚未与实验室真实服务的结果做逐点比对，无法给出误差范围。

---

## 七、建议的下一步

| 优先级 | 事项 |
|---|---|
| 高 | 修复 4.1 的静默吞异常问题，使 CI 判据有效 |
| 高 | 明确 `delta`/`drag`/`optpipulse`/`pkl_convert` 的功能归属，决定补齐或移除 |
| 中 | 统一 `peaks` 等字段的语义约定，或在文档/类型注解中固化 |
| 中 | 解决 vendor 子模块的版本管理问题 |
| 中 | 在实验室内网环境下，用真实服务对同一批数据跑一遍，做精度比对 |
| 低 | 继续完善 4.2（非 200 响应处理）与 4.3（装饰器一致性） |

---

## 八、复现步骤

```cmd
:: 1. 灌入测试数据（自动挑选完整矩形扫描的 2D 文件）
deploy\qmclaw\python.exe tools\lqcs-offline\populate_data.py

:: 2. 应用 vendor 补丁（幂等；--check 可挂 CI）
deploy\qmclaw\python.exe tools\lqcs-offline\apply_vendor_fixes.py

:: 3. 启动离线推理服务
deploy\qmclaw\python.exe tools\lqcs-offline\offline_service.py --port 9801

:: 4. 指向本地服务并运行测试（须在 vendor\QubitClient 目录下执行）
set QUBITCLIENT_URL=http://127.0.0.1:9801
set QUBITCLIENT_API_KEY=offline
cd vendor\QubitClient
..\..\deploy\qmclaw\python.exe tests\skills\lqcs\test_s21peak.py
```

> 注意：配置必须通过环境变量提供。仓库根目录的 `config.py` 不会被读取（见 4.6）。

---

## 附录：产出物清单

| 文件 | 说明 |
|---|---|
| `tools/lqcs-offline/offline_service.py` | 离线推理服务（14 类任务） |
| `tools/lqcs-offline/populate_data.py` | 数据灌入脚本（可重建） |
| `tools/lqcs-offline/apply_vendor_fixes.py` | vendor 补丁重放脚本 |
| `tools/lqcs-offline/README.md` | 协议表、扩展指南、全部陷阱清单 |
| `logs/lqcs/PROBLEMS.md` | 25 个测试的逐条诊断与根因分类 |
| `logs/lqcs/dev_status.png` | 开发状况总览图 |
| `logs/lqcs/probe_*.py` | 字段结构 / 转换器实测探针 |
| `vendor/QubitClient/tmp/vis/` | 离线运行产出的图（40+ 张） |
