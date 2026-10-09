"use client";

/**
 * DataVaultPicker - DATAVAULT / 📦OFFLINE 数据集选择器
 *
 * 从 JobsPanel.tsx 的 DataVaultCard 原样抽取（抽组件而非复制，避免两处逻辑分叉）。
 * 使用方：
 *   - JobsPanel（experiments 页左侧栏）—— 只做选择，行为与抽取前一致
 *   - ImageAnalysisTab（image_analysis 左栏）—— 选中即触发绘图，见 onPick
 *
 * 本组件不包含任何 job / 实验执行逻辑。
 */

import { useState, useEffect, useCallback } from "react";
import { api } from "../lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Dataset {
  id: string;
  name: string;
  path?: string;
  qubit?: string;
  experiment_type?: string;
  date?: string;
  file_size?: number;
}

/** 选中回调携带的数据集（附带来源模式，调用方据此选择绘图 API） */
export interface PickedDataset extends Dataset {
  mode: "online" | "offline";
}

interface SessionConfig {
  user: string;
  path: string[];
}

// 实验类型匹配（normalizeFamilyKey / extractFamilyTokenFromFilename / matchFamily /
// DATAVAULT_EXP_TYPE_TO_FAMILY）统一放在 @/lib/experimentFamily，供 image_analysis 使用。

// ── Props ─────────────────────────────────────────────────────────────────────

export interface DataVaultPickerProps {
  /** 选中数据集时回调（取消选中不触发） */
  onPick?: (ds: PickedDataset) => void;
  /**
   * 离线数据集行内 📈 快速绘图按钮的行为。
   * 不传则保持原有行为：dispatch `dataset:plot-offline` 事件给 experiments 页。
   */
  onQuickPlot?: (ds: PickedDataset) => void | Promise<void>;
  /** experiments 页的刷新信号，传入后刷新按钮会联动 */
  refreshTrigger?: number;
  /** 左侧栏紧凑布局：限制数据集列表高度并自带滚动 */
  compact?: boolean;
  /** compact 模式下列表最大高度（px） */
  maxListHeight?: number;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function DataVaultPicker({
  onPick,
  onQuickPlot,
  refreshTrigger = 0,
  compact = false,
  maxListHeight = 220,
}: DataVaultPickerProps) {
  const [sessionConfig, setSessionConfig] = useState<SessionConfig | null>(null);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [labradAvailable, setLabradAvailable] = useState(true);
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(1);
  const [selectedDs, setSelectedDs] = useState<Dataset | null>(null);
  const [plottingDsId, setPlottingDsId] = useState<string | null>(null);
  const PAGE_SIZE = 20;

  // Offline mode state
  const [offlineMode, setOfflineMode] = useState(false);
  const [offlineQubits, setOfflineQubits] = useState<string[]>([]);
  const [offlineSelectedQubit, setOfflineSelectedQubit] = useState<string>("");
  const [offlineDatasets, setOfflineDatasets] = useState<Dataset[]>([]);
  const [offlineLoading, setOfflineLoading] = useState(false);

  // Load session config from quantum service
  useEffect(() => {
    const loadConfig = async () => {
      try {
        const res = await api.listQubits() as { sessionPath?: string[]; error?: string; source?: string };
        if (res.sessionPath && res.sessionPath.length > 0) {
          const sp = res.sessionPath;
          const user = sp.length > 1 ? sp[1] : 'LQHL';
          const path = sp.slice(2);
          setSessionConfig({ user, path });
        }
      } catch (e) {
        console.error('[DataVaultPicker] Failed to load config:', e);
      }
    };
    loadConfig();
  }, []);

  // Check offline mode status and load offline qubits
  useEffect(() => {
    const checkOfflineStatus = async () => {
      try {
        const modeRes = await api.quantumMode() as { mode?: string; offline_available?: boolean };
        const isOffline = modeRes.mode === "offline" || (modeRes.mode === "auto" && !modeRes.offline_available);
        console.log('[DataVaultPicker] Mode check:', { modeRes, isOffline });
        setOfflineMode(isOffline);

        // Always try to load qubits - the service will return offline data if in offline mode
        const qubitsRes = await api.listQubits() as { qubits?: Array<{ name: string }>; source?: string; error?: string };
        console.log('[DataVaultPicker] Qubits loaded:', { source: qubitsRes.source, count: qubitsRes.qubits?.length });

        // If we're in offline mode OR the service returned offline data
        if (isOffline || qubitsRes.source === "offline") {
          if (qubitsRes.qubits && qubitsRes.qubits.length > 0) {
            setOfflineQubits(qubitsRes.qubits.map(q => q.name));
            setOfflineSelectedQubit(prev => prev || qubitsRes.qubits![0].name);
          }
        }
      } catch (e) {
        console.error('[DataVaultPicker] Failed to check offline status:', e);
      }
    };
    checkOfflineStatus();
  }, []);

  // Load offline datasets when qubit changes
  useEffect(() => {
    if (offlineMode && offlineSelectedQubit) {
      loadOfflineDatasets();
    }
  }, [offlineMode, offlineSelectedQubit]);

  const loadOfflineDatasets = async () => {
    setOfflineLoading(true);
    try {
      const res = await api.listOfflineDatasets({ qubit: offlineSelectedQubit }) as { datasets: Dataset[]; error?: string };
      if (res.datasets) {
        setOfflineDatasets(res.datasets);
        setPage(1);
      }
    } catch (e: any) {
      console.error('[DataVaultPicker] Failed to load offline datasets:', e);
    } finally {
      setOfflineLoading(false);
    }
  };

  // Handle plotting offline dataset (using v2 API with qter.fitData support)
  // 默认行为：dispatch 事件给 experiments 页渲染；传入 onQuickPlot 时改由调用方处理
  const handlePlotOfflineDataset = async (ds: Dataset) => {
    setPlottingDsId(ds.id);
    try {
      if (onQuickPlot) {
        await onQuickPlot({ ...ds, mode: "offline" });
        return;
      }

      // Use the new v2 API that supports qter.fitData() style commands
      const res = await api.plotOfflineDatasetV2({
        dataset_id: ds.id,
        command: "qter.fitData(do_plot=True)"
      }) as {
        success: boolean;
        image?: string;
        plotUrl?: string;
        error?: string;
        dataset_name?: string;
        qubit?: string;
        experiment_type?: string;
      };

      if (res.success) {
        // Dispatch event to Experiments page with Base64 image
        if (res.image) {
          window.dispatchEvent(new CustomEvent("dataset:plot-offline", {
            detail: { dataset_id: ds.id, image: res.image }
          }));
        }
      } else if (res.error) {
        console.error('[DataVaultPicker] Plot error:', res.error);
      }
    } catch (e: any) {
      console.error('[DataVaultPicker] Failed to plot:', e);
    } finally {
      setPlottingDsId(null);
      // Don't clear selectedDs - user may want to use it for variant generation
    }
  };

  // Check LabRAD availability via quantum service health
  const checkLabradAvailable = async (): Promise<boolean> => {
    try {
      const res = await api.listQubits() as { error?: string };
      return !res.error;
    } catch { /* ignore */ }
    return false;
  };

  const loadDatasets = useCallback(async () => {
    if (!sessionConfig) return;

    const available = await checkLabradAvailable();
    setLabradAvailable(available);

    if (!available) {
      setLoading(false);
      setError("LabRAD 服务器未连接");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const path = "/" + sessionConfig.user + "/" + sessionConfig.path.join("/");
      const res = await api.listDatasets(path) as { datasets: Dataset[] };
      setDatasets(res.datasets.reverse());
      setPage(1);
    } catch (e: any) {
      if (e.message?.includes("data_vault") || e.message?.includes("NoneType")) {
        setLabradAvailable(false);
        setError("LabRAD 服务器未连接");
      } else {
        setError(e.message || "Failed to load datasets");
      }
    } finally {
      setLoading(false);
    }
  }, [sessionConfig]);

  useEffect(() => {
    if (sessionConfig && labradAvailable && !offlineMode) {
      loadDatasets();
    }
  }, [sessionConfig, labradAvailable, loadDatasets, refreshTrigger, offlineMode]);

  // Filter datasets (use offline datasets when in offline mode)
  const displayDatasets = offlineMode ? offlineDatasets : datasets;
  const filteredDatasets = filter
    ? displayDatasets.filter(ds => ds.name.toLowerCase().includes(filter.toLowerCase()))
    : displayDatasets;

  // Paginate
  const totalPages = Math.ceil(filteredDatasets.length / PAGE_SIZE);
  const paginatedDatasets = filteredDatasets.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const sessionPath = sessionConfig
    ? `${sessionConfig.user}/${sessionConfig.path.join("/")}`
    : "...";

  const isLoading = offlineMode ? offlineLoading : loading;

  const pad = compact ? "0.2rem 0.45rem" : "0.4rem 0.75rem";

  return (
    <div style={{
      border: "1px solid #1e293b",
      borderRadius: "0.5rem",
      background: "#0a0f1a",
      overflow: "hidden",
      display: "flex",
      flexDirection: "column",
      flexShrink: 0,
    }}>
      {/* Header */}
      <div style={{
        padding: pad,
        fontSize: "0.65rem",
        fontWeight: 600,
        color: "#475569",
        letterSpacing: "0.1em",
        borderBottom: "1px solid #1e293b",
        background: "#0f172a",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
      }}>
        <span style={{ color: offlineMode ? "#f59e0b" : "#475569" }}>
          📂 DATAVAULT {offlineMode && "📦OFFLINE"}
        </span>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          {offlineMode && selectedDs && (
            <button
              onClick={() => {
                // Dispatch event to open variant generator in parent
                window.dispatchEvent(new CustomEvent("dataset:open-variant-generator", {
                  detail: {
                    dataset_id: selectedDs.id,
                    name: selectedDs.name,
                    qubit: selectedDs.qubit,
                    experiment_type: selectedDs.experiment_type,
                  }
                }));
              }}
              style={{
                padding: "0.1rem 0.4rem",
                background: "#6366f1",
                border: "none",
                borderRadius: "0.2rem",
                color: "#fff",
                cursor: "pointer",
                fontSize: "0.6rem",
                fontWeight: 600,
              }}
              title="Generate variant"
            >
              🔬
            </button>
          )}
          <span
            onClick={() => offlineMode ? loadOfflineDatasets() : loadDatasets()}
            style={{ color: "#38bdf8", cursor: "pointer", fontWeight: 400 }}
            title="Refresh"
          >↻</span>
        </div>
      </div>

      {/* Offline mode qubit selector */}
      {offlineMode && (
        <div style={{ padding: "0.3rem 0.5rem", borderBottom: "1px solid #1e293b" }}>
          <select
            value={offlineSelectedQubit}
            onChange={(e) => setOfflineSelectedQubit(e.target.value)}
            style={{
              width: "100%",
              padding: "0.2rem 0.3rem",
              background: "#1e293b",
              border: "1px solid #334155",
              borderRadius: "0.2rem",
              color: "#e2e8f0",
              fontSize: "0.65rem",
              fontFamily: "monospace",
              boxSizing: "border-box",
            }}
          >
            {offlineQubits.map(q => (
              <option key={q} value={q}>{q}</option>
            ))}
          </select>
        </div>
      )}

      {/* Session path (only in online mode) */}
      {!offlineMode && (
        <div style={{
          padding: "0.2rem 0.75rem",
          borderBottom: "1px solid #1e293b",
          fontSize: "0.6rem",
          color: "#64748b",
          fontFamily: "monospace",
          background: "#0f172a",
        }}>
          📍 {sessionPath}
        </div>
      )}

      {/* Filter input */}
      <div style={{
        padding: "0.3rem 0.5rem",
        borderBottom: "1px solid #1e293b",
      }}>
        <input
          type="text"
          value={filter}
          onChange={(e) => { setFilter(e.target.value); setPage(1); }}
          placeholder="🔍 Filter..."
          style={{
            width: "100%",
            padding: "0.2rem 0.3rem",
            background: "#1e293b",
            border: "1px solid #334155",
            borderRadius: "0.2rem",
            color: "#e2e8f0",
            fontSize: "0.65rem",
            fontFamily: "monospace",
            boxSizing: "border-box",
          }}
        />
      </div>

      {/* Error message */}
      {error && (
        <div style={{
          margin: "0.3rem",
          padding: "0.3rem",
          background: !labradAvailable ? "#422006" : "#451a1a",
          border: `1px solid ${!labradAvailable ? "#f59e0b" : "#ef4444"}`,
          borderRadius: "0.2rem",
          fontSize: "0.6rem",
          color: labradAvailable ? "#f87171" : "#fbbf24",
          textAlign: "center",
        }}>
          {!labradAvailable ? "⚠️ 请先启动测控服务" : error}
        </div>
      )}

      {/* Dataset list */}
      <div style={
        compact
          ? { maxHeight: `${maxListHeight}px`, overflow: "auto", minHeight: "60px" }
          : { flex: 1, overflow: "auto", minHeight: "80px" }
      }>
        {isLoading && (
          <div style={{ padding: "0.5rem", color: "#334569", fontSize: "0.7rem", textAlign: "center" }}>
            Loading...
          </div>
        )}
        {!isLoading && !error && paginatedDatasets.map((ds) => (
          <div
            key={ds.id}
            onClick={() => {
              // In offline mode: select/deselect (like online mode)
              // User can then click 🔬 button to open variant generator
              const next = selectedDs?.id === ds.id ? null : ds;
              setSelectedDs(next);
              // 只在真正选中时回调，取消选中不触发（避免重复绘图）
              if (next) {
                onPick?.({ ...ds, mode: offlineMode ? "offline" : "online" });
              }
            }}
            style={{
              padding: compact ? "0.2rem 0.5rem" : "0.25rem 0.75rem",
              borderBottom: "1px solid #1e293b",
              cursor: "pointer",
              background: selectedDs?.id === ds.id ? "#1e3a5f" : "transparent",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
            }}
          >
            {offlineMode && (
              <span style={{
                fontSize: "0.5rem",
                color: plottingDsId === ds.id ? "#38bdf8" : "#64748b",
                width: "12px",
              }}>
                {plottingDsId === ds.id ? "⏳" : "📊"}
              </span>
            )}
            <div style={{
              fontFamily: "monospace",
              fontSize: "0.65rem",
              color: selectedDs?.id === ds.id ? "#38bdf8" : "#94a3b8",
              flex: 1,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}>
              {ds.name}
            </div>
            {offlineMode && ds.qubit && (
              <span style={{
                fontSize: "0.55rem",
                color: "#64748b",
                background: "#1e293b",
                padding: "0.1rem 0.3rem",
                borderRadius: "0.2rem",
              }}>
                {ds.qubit}
              </span>
            )}
            {/* Quick plot button in offline mode */}
            {offlineMode && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handlePlotOfflineDataset(ds);
                }}
                disabled={plottingDsId === ds.id}
                style={{
                  background: "transparent",
                  border: "1px solid #334155",
                  borderRadius: "0.2rem",
                  color: plottingDsId === ds.id ? "#334155" : "#64748b",
                  cursor: plottingDsId === ds.id ? "not-allowed" : "pointer",
                  padding: "0.1rem 0.3rem",
                  fontSize: "0.6rem",
                }}
                title="Plot dataset"
              >
                📈
              </button>
            )}
          </div>
        ))}
        {!isLoading && !error && filteredDatasets.length === 0 && (
          <div style={{ padding: "0.5rem", color: "#334569", fontSize: "0.7rem", textAlign: "center" }}>
            {offlineMode ? "No offline datasets" : "No datasets found"}
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{
          padding: "0.25rem 0.5rem",
          borderTop: "1px solid #1e293b",
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          gap: "0.15rem",
          background: "#0f172a",
        }}>
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            style={{
              padding: "0.1rem 0.3rem",
              borderRadius: "0.15rem",
              border: "1px solid #334155",
              background: page === 1 ? "#1e293b" : "#0f172a",
              color: page === 1 ? "#475569" : "#94a3b8",
              cursor: page === 1 ? "not-allowed" : "pointer",
              fontSize: "0.6rem",
            }}
          >
            ‹
          </button>
          <span style={{ fontSize: "0.6rem", color: "#64748b", padding: "0 0.25rem" }}>
            {page}/{totalPages}
          </span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            style={{
              padding: "0.1rem 0.3rem",
              borderRadius: "0.15rem",
              border: "1px solid #334155",
              background: page === totalPages ? "#1e293b" : "#0f172a",
              color: page === totalPages ? "#475569" : "#94a3b8",
              cursor: page === totalPages ? "not-allowed" : "pointer",
              fontSize: "0.6rem",
            }}
          >
            ›
          </button>
        </div>
      )}
    </div>
  );
}
