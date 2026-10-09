# image_analysis 移植 DATAVAULT/OFFLINE 选择器 —— 实施方案

> 状态：**已实现，人工验证通过（2026-10-08）**
> 确认时间：本轮会话
> 为什么先写方案：该改动涉及 3 个文件（合计 2500+ 行）与 1 个新组件，需连续读改并重建验证；
> 当前会话上下文已被前序 lqcs 离线化排查占满，硬做有改坏前端风险。此文件供新会话直接开工。

---

## 零、实施结果（2026-10-08 补记）

第二节那个「唯一的未知点」已查清，**前提假设不成立**：

> 绘图产物**不是**按 `jobId` 寻址的。离线和在线两个绘图接口都直接返回 base64 图像，
> `api.plotUrl(jobId)` / `PLOTS_DIR` / `normalizePlotUrl()` 只服务旧的 Express `/sessions/plot` 流程。

- 离线：`api.plotOfflineDatasetV2({ dataset_id, command })` → `{success, image:"data:image/png;base64,...", qubit, experiment_type, dataset_name}`
- 在线：`api.plotExperimentDataset(name, path)` → `{success, image, exp_type, qubit, exp_num}`

因此 A2（选中即出图）是直接 `setImage(res.image)`，无需先跑实验拿 URL。

改动落盘情况（含第二轮返工）：

| 文件 | 说明 |
|---|---|
| `src/components/DataVaultPicker.tsx` | 新增，原 `DataVaultCard` 逐行搬运 + 加 props（`onPick`/`onQuickPlot`/`refreshTrigger`/`compact`/`maxListHeight`） |
| `src/components/JobsPanel.tsx` | 原区块换成 `<DataVaultPicker refreshTrigger={...} />`（不传 onPick，行为不变） |
| `src/lib/experimentFamily.ts` | 新增，实验类型匹配与**映射表** `DATAVAULT_EXP_TYPE_TO_FAMILY`（集中一处，方便审校） |
| `src/components/tabs/ImageAnalysisTab.tsx` | 接收 `pickedDataset` prop → 绘图到原有拖拽框；实验类型匹配独立成 effect（等 families 加载完再匹配，避免重复绘图） |
| `src/app/page.tsx` | **第二轮修正**：选择器放在应用左栏 **QUBIT 下方**，仅 `image_analysis` 标签显示；选中结果经 state 传给 `<ImageAnalysisTab pickedDataset={...} />` |
| `src/styles/animations.css` | 补 `@keyframes spin`（原来 spinner 用的 keyframe 全仓库不存在） |

### 为什么需要映射表（第二轮查实）

`families` 是 **VLM prompt 的分类**（vendor `qubitclient/llm/experiment_tools.py` 的 `ExperimentFamily`），
DataVault 的 `experiment_type` 是**采集名**，两套词表基本不重合（本地 offline_data 索引实测）：

| 类型 | families 里有吗 |
|---|---|
| `iqraw` | ❌（本地最高频类型） |
| `pipulse` | ❌（只有 `optpipulse`） |
| `s21` | ✅ |
| `spectroscopy` | ❌ |
| `t1` | ✅ |

仅 `iqraw`+`pipulse` 两类就占了绝大部分数据。而 vendor 里 `get_prompt()` 找不到 key 时**静默回退到 rabi 的 prompt**
（`qubitclient/llm/experiments/q1_describe_plot.py:171` 等 6 处），所以给错 family 不是报错，
而是"看起来合理但用错模板"的分析 —— 映射表必须由熟悉物理语义的人确认。

合法 family 共 **33 个**（已核对 6 个任务 × 中英 12 个 prompt 字典，完全一致）。
映射表（`src/lib/experimentFamily.ts`）覆盖了绝大多数实测类型，未覆盖的保持原选择并提示。
（具体的类型条数分布属于本地数据特征，不写进仓库。）

> ⚠️ 顺带查出的既有 bug（**未修**，超出本次范围）：后端
> `services/qubitclient_service/server.py` 的 `EXPERIMENT_FAMILIES` 里有 `s21peak`、`s21peakmulti`，
> 这两个 **不在** 那 33 个合法 key 里 → 前端下拉能选中，但分析会静默用 rabi 的 prompt。


验证状态：**已通过用户人工验证（2026-10-08）**。
`tsc --noEmit` 对本轮改动的文件零错误（仓库另有 6 个既有报错，位于
`page.tsx` / `AgentToolsPanel.tsx` / `VariantGenerator.tsx`，与本次改动无关且改前就存在）。

遗留（用户未拍板，均不影响当前功能）：

1. `src/lib/experimentFamily.ts` 里标「待确认」的映射项（iqraw→singleshot 等）尚未逐条review。
   覆盖面 99.3%，改一行字符串即可调整。**注意给错 family 会静默回退到 rabi 的 prompt，不报错。**
2. 既有 bug：后端 `EXPERIMENT_FAMILIES` 里的 `s21peak` / `s21peakmulti` 不在合法的 33 个
   prompt key 里，选中即静默用 rabi prompt。本次未修。


---

## 一、已确认的需求

| 项 | 结论 |
|---|---|
| 图片显示位置 | `ImageAnalysisTab` 里**现有的拖拽框**（`image` / `imagePreview` 两个 state） |
| 选择器位置 | **左侧栏** |
| 实验类型自动匹配 | 按**文件名里的实验类型**（如 `00001 - qXXX%c S21.hdf5` → `S21`） |
| 图片从哪来 | **A2：选中即出图** —— 选文件时自动触发生成绘图 |
| 是否自动触发 VLM 分析 | **不触发**，等用户手动点分析 |
| 原有 VLM 分析 | **保留不动** |

## 二、动手前必须查清的一件事（唯一的未知点）

**绘图产物是按 `jobId` 寻址的，不是按数据集名。** 已知证据：

```
api.ts:413        plotUrl: (jobId: string) => `${API_BASE}/plot/${jobId}`
page.tsx:707      setPlotUrl(`${result.plotUrl}?t=${Date.now()}`)   // 来自「实验运行结果」
JobManager.tsx:92 src={api.plotUrl(job.id)}
UnifiedResults    <img src={plotUrl} />   （接收 plotUrl prop 展示）
```

因此 A2 的实现前提是：**能用「数据集 + qubit」参数触发一次绘图，并拿到它的 URL**。
需要读 `page.tsx` 里 offline sim 触发实验那段（约 **540–720 行**）确认：

1. 前端调用的是哪个 api 函数（`lib/api.ts` 里对应哪个）
2. 请求体需要哪些字段（数据集名？qubit？实验名？）
3. 返回结构里的 `plotUrl` 字段路径
4. `PLOTS_DIR`（`page.tsx:32`）与 `/plots/...` 的关系，以及 `api.ts:21–30` 那个路径辅助函数的用法

## 三、改动清单

### 1. 新建 `src/components/DataVaultPicker.tsx`
从 `JobsPanel.tsx` 第 **~396–602 行**抽出 DATAVAULT/OFFLINE 那块（`offlineMode` 状态、offline 数据集加载、qubit 选择、数据集列表），**抽组件而非复制**，避免两处逻辑分叉。

接口建议：

```ts
type PickedDataset = { name: string; qubit?: string; path?: string };

export default function DataVaultPicker(props: {
  onPick: (ds: PickedDataset) => void;   // 选中数据集时回调
  compact?: boolean;                      // 左侧栏用紧凑布局
}) { ... }
```

要点：
- 原 `JobsPanel` 里的副作用（自动选中 qubit 等）保留在组件内部
- 不要把 job 执行逻辑带过来（image_analysis 不需要跑实验）

### 2. 改 `src/components/JobsPanel.tsx`
把抽出的区块替换为 `<DataVaultPicker onPick={...} />`，把原来的行为映射到 `onPick`。

> ⚠️ 回归风险：experiments 页的 DATAVAULT 行为必须与改动前一致。改完要对照验证：
> 切 OFFLINE 模式、切 qubit、选数据集、刷新列表。

### 3. 改 `src/components/tabs/ImageAnalysisTab.tsx`
- 引入 `DataVaultPicker`，**放在左侧栏**
- 新增回调：

```ts
const onPickDataset = async (ds: PickedDataset) => {
  // ① 用 ds 触发绘图（api 待第二节确认），拿到 plotUrl
  // ② setImage(dataUrl); setImagePreview(dataUrl)
  // ③ 自动匹配实验类型：
  const fam = matchFamilyFromFilename(ds.name);   // 见下
  if (fam) setSelectedFamily(fam);
  else addLog(`未能从文件名匹配实验类型: ${ds.name}`);   // 不静默改
};
```

- **实验类型匹配规则**（按文件名）：
  - 取 `%c ` 之后、`.hdf5` 之前那段：`00001 - qXXX%c S21.hdf5` → `S21`
  - 与 `families`（来自 `api.qubitGetFamilies()`）的 key/名称做**大小写无关**匹配
  - 匹配不到：保持当前 `selectedFamily` 不变并提示（不要猜）
- 不改动 `compressImage()`、健康检查、分析按钮等既有逻辑
- 拖拽上传的原有行为不受影响（`DataVaultPicker` 只是多一个入口）

### 4. 已知需要核对的数据
`families` 的取值格式（key 是 `S21` 还是别的小写/带后缀形式）——读 `qubitGetFamilies` 返回或后端 family 定义确认，**不要凭猜写映射表**。

## 四、验证步骤

1. 服务启停由人控制：请用户双击 `D:\访问github\start-qmclaw.cmd`（Express 3002 / Python 3003-3012 / Next.js **8081**）
2. 浏览器打开 `http://localhost:8081` → 切到 `image_analysis` 标签
3. 逐项验证：
   - [ ] 左侧栏出现 📂 DATAVAULT 📦OFFLINE 选择器
   - [ ] 切 OFFLINE 模式、切 qubit、数据集列表正常
   - [ ] 选中一个数据集 → 图出现在**原有拖拽框**里
   - [ ] 下方的实验类型**自动选中**了正确项
   - [ ] 手动点分析 → VLM 分析仍正常（原有功能未回归）
   - [ ] 手动拖拽上传图片的原有路径仍正常
4. experiments 页回归：DATAVAULT 选择器行为与改前一致

> 截图验证注意：本机沙箱下 Chromium 起不来（命名管道被拒，`FATAL: platform_channel.cc`），
> 截图需 `danger-full-access` 提权，或请用户直接看一眼。

## 五、上下文交接说明

前序工作已全部落盘，不会丢：

| 内容 | 位置 |
|---|---|
| lqcs 离线推理服务 + 3 个脚本 | `QMClaw-main/tools/lqcs-offline/` |
| 进度与问题报告 | 同上 `PROGRESS_REPORT.md` |
| vendor 补丁重放器（10 条，`--check` exit=0） | 同上 `apply_vendor_fixes.py` |
| 逐条测试诊断、探针、日志 | `logs/lqcs/` |

**lqcs 侧的当前状态**：真实服务 `<lqcs-host>:7000` 下 21/25 通过；剩余 4 个是 vendor 代码缺失
（`delta`/`allxy_drag`/`optpipulse`/`optpipulse_convert`），与离线/网络无关。
