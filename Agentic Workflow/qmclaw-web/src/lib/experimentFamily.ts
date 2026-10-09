/**
 * 实验类型匹配：DataVault 采集名 → QubitClient VLM 实验家族（prompt key）
 *
 * ⚠️ 为什么要一张映射表
 * 这两套词表是**不同分类体系**：
 *   - DataVault 的 experiment_type 是"采集名"：iqraw / pipulse / spectroscopy / s21power2d ...
 *   - families 是 VLM prompt 的分类（vendor: qubitclient/llm/experiment_tools.py 的 ExperimentFamily）
 * 只有 s21 / t1 / ramsey 等少数重合，实测 iqraw+pipulse 就占离线数据的 70%。
 *
 * ⚠️ 给错 family 不会报错
 * vendor 里 get_prompt() 找不到 key 时**静默回退到 rabi 的 prompt**
 * （qubitclient/llm/experiments/q1_describe_plot.py:171 等 6 处），
 * 结果是"看起来合理但用错模板"的分析。所以映射目标必须是**合法的 33 个 key 之一**。
 *
 * 合法 key 集合（已核对 6 个任务 × 中英共 12 个 prompt 字典，完全一致）：
 *   coupler_flux cz_benchmarking drag gmm microwave_ramsey mot_loading optpipulse
 *   pinchoff pingpong powershift qubit_flux_spectroscopy qubit_spectroscopy
 *   qubit_spectroscopy_power_frequency rabi rabi_hw rabicos ramsey
 *   ramsey_charge_tomography ramsey_freq_cal ramsey_t2star rb res_spec rydberg_ramsey
 *   rydberg_spectroscopy s21 s21vflux singleshot spectrum spectrum_2d t1 t1_fluctuations
 *   t2 tweezer_array
 *
 * 类型清单来自本地 offline_data 索引的实测统计（该数据目录不在本仓库内，具体条数不在此记录）。
 */

export interface FamilyLike {
  id: string;
  name: string;
}

/** 归一化：小写 + 去掉非字母数字，用于大小写/分隔符无关的匹配 */
export function normalizeFamilyKey(s: string | null | undefined): string {
  return (s || "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

/**
 * 从数据集文件名里取出实验类型 token。
 *   00001 - qXXX%c S21.hdf5  →  "S21"
 * 规则：取 `%c` 之后、最后一个已知数据后缀之前的那段。
 * 取不到（文件名里没有 `%c`）返回 null。
 * 注意：experiment_type 有时候本身就是这种派生串（形如 "<qubit>, <coupler>%c <子类型>"），
 * 所以这个函数对 experiment_type 也同样适用。
 */
export function extractFamilyTokenFromFilename(filename: string): string | null {
  if (!filename) return null;
  const m = /%c\s*([^/\\]+)$/i.exec(filename);
  if (!m) return null;
  const token = m[1]
    .replace(/\.(hdf5|h5|mat|csv|dat|json|npy|npz|txt)$/i, "")
    .trim();
  return token || null;
}

/**
 * DataVault experiment_type → VLM family id
 *
 * key 一律写成 normalizeFamilyKey() 归一化后的形式（小写、无分隔符），
 * 所以 `s21_dis` 要写成 `s21dis`，`ramsey df` 写成 `ramseydf`。
 *
 * 🔧 待确认的行都标了「待确认」，改起来就是改右边那个字符串。
 */
export const DATAVAULT_EXP_TYPE_TO_FAMILY: Record<string, string> = {
  // ── 高置信：两边就是同一个东西 ──────────────────────────────
  s21: "s21",
  t1: "t1",
  ramsey: "ramsey",
  spectrum: "spectrum", // DataVault 侧同名类型

  // ── 待确认：靠名字推断，需要你的物理判断 ────────────────────
  iqraw: "singleshot", // IQ 原始单发数据 → Single Shot（本地最高频类型）
  pipulse: "optpipulse", // π 脉冲
  pipulsedf: "optpipulse", // π 脉冲（df 变体）
  spectroscopy: "spectrum", // 光谱；若指 qubit 光谱应改 qubit_spectroscopy
  spectroscopyauto: "spectrum",
  iqcenterspectroscopy: "qubit_spectroscopy", // IQ 中心光谱
  piampfine: "rabi", // π 幅度细扫（Rabi 类）
  alphafine: "rabi", // 幅度细扫（Rabi 类）
  s21zpa2d: "s21vflux", // S21 二维（ZPA）→ S21 vs Flux
  s21power2d: "spectrum_2d", // S21 vs Power 二维
  ramseydf: "ramsey", // Ramsey 去频；若是频率标定应改 ramsey_freq_cal
  s21dis: "s21", // S21 dispersion
  pulseshape: "rabicos", // 脉冲形状 → Rabi COS
  xeb: "cz_benchmarking", // XEB 门基准
  // 这个 key 来自「按 %c 取子类型」后的结果，不是整串归一化，
  // 所以必须配合 buildFamilyCandidates 里对 experiment_type 的 %c 提取才生效。
  czxeb: "cz_benchmarking",
  spinechocpmg: "t2", // Spin echo / CPMG → T2

  // 未映射（保持现状 + 提示，不猜）：
  //   swap11to20 / interaction / timingxyz / czechozpa sweep ... 在 33 个 family 里没有对应语义
};

/** 查映射表；查不到返回 undefined（调用方据此回退到原始值精确匹配） */
export function mapExperimentTypeToFamily(
  expType: string | null | undefined
): string | undefined {
  const k = normalizeFamilyKey(expType);
  if (!k) return undefined;
  return DATAVAULT_EXP_TYPE_TO_FAMILY[k];
}

/**
 * 组装 family 候选值，按优先级排列：
 *   ① 映射后的后端 experiment_type（最可靠：后端已从文件名解析并标准化）
 *   ② 原始 experiment_type（精确同名的情况）
 *   ③ 映射后的 `%c` 子类型（experiment_type 或文件名里取出来的）
 *   ④ `%c` 子类型原文
 *
 * ③④ 是必须的：有些 experiment_type 本身就是派生串（形如 "<qubit>, <coupler>%c cz xeb"），
 * 整串归一化后是 `...czxeb`，永远匹配不到 `czxeb` 这个 key —— 必须先按 `%c` 截出子类型。
 */
export function buildFamilyCandidates(
  expTypes: (string | null | undefined)[],
  datasetName?: string
): string[] {
  const out: string[] = [];
  const push = (v?: string | null) => {
    if (v && !out.includes(v)) out.push(v);
  };

  const tokens = [...expTypes, datasetName].map((s) =>
    extractFamilyTokenFromFilename(s || "")
  );

  for (const t of expTypes) push(mapExperimentTypeToFamily(t));
  for (const t of expTypes) push(t || undefined);
  for (const t of tokens) push(mapExperimentTypeToFamily(t));
  for (const t of tokens) push(t);

  return out;
}

/**
 * 在 families 里按候选值顺序找匹配项（大小写无关，同时比 id 和 name）。
 * 找不到返回 null —— 调用方保持原选择并提示，不要猜。
 */
export function matchFamily(
  candidates: (string | null | undefined)[],
  families: FamilyLike[]
): FamilyLike | null {
  for (const c of candidates) {
    const key = normalizeFamilyKey(c);
    if (!key) continue;
    const hit = families.find(
      (f) => normalizeFamilyKey(f.id) === key || normalizeFamilyKey(f.name) === key
    );
    if (hit) return hit;
  }
  return null;
}
