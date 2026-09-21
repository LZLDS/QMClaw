"use client";

import { useState, useEffect, useCallback } from "react";
import { api, JobResult } from "../lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Dataset {
  id: string;
  name: string;
  path: string;
  qubit?: string;
  experiment_type?: string;
  date?: string;
  file_size?: number;
}

interface SessionConfig {
  user: string;
  path: string[];
}

// Offline mode state type
interface OfflineModeState {
  enabled: boolean;
  qubits: string[];
  selectedQubit: string;
  selectedExpType: string;
  selectedDate: string;
}

// ── StatusDot ─────────────────────────────────────────────────────────────────

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    pending: "#94a3b8",
    running: "#38bdf8",
    completed: "#22c55e",
    failed: "#f87171",
    cancelled: "#f59e0b",
  };
  return (
    <span style={{
      display: "inline-block",
      width: "6px",
      height: "6px",
      borderRadius: "50%",
      background: colors[status] || "#94a3b8",
      marginRight: "0.4rem",
      flexShrink: 0,
    }} />
  );
}

// ── RunningJobs Component ─────────────────────────────────────────────────────

function RunningJobsCard({ refreshTrigger }: { refreshTrigger: number }) {
  const [jobs, setJobs] = useState<JobResult[]>([]);

  const fetchJobs = useCallback(async () => {
    try {
      const list = await api.listJobs() as JobResult[];
      // Only show pending/running jobs
      setJobs(list.filter(j => j.status === "pending" || j.status === "running"));
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs, refreshTrigger]);

  // Poll while there are running jobs
  useEffect(() => {
    if (jobs.length === 0) return;
    const interval = setInterval(fetchJobs, 1000);
    return () => clearInterval(interval);
  }, [jobs.length, fetchJobs]);

  const handleCancel = async (jobId: string) => {
    try {
      await api.cancelJob(jobId);
      setJobs(prev => prev.filter(j => j.id !== jobId));
    } catch (e) {
      console.error("Cancel failed:", e);
    }
  };

  const getElapsed = (submittedAt: number): string => {
    const ms = Date.now() - submittedAt;
    if (ms < 1000) return "<1s";
    if (ms < 60000) return `${Math.floor(ms / 1000)}s`;
    return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`;
  };

  return (
    <div style={{
      border: "1px solid #1e293b",
      borderRadius: "0.5rem",
      background: "#0a0f1a",
      overflow: "hidden",
    }}>
      <div style={{
        padding: "0.4rem 0.75rem",
        fontSize: "0.65rem",
        fontWeight: 600,
        color: "#475569",
        letterSpacing: "0.1em",
        borderBottom: "1px solid #1e293b",
        background: "#0f172a",
      }}>
        ⚡ RUNNING JOBS ({jobs.length})
      </div>

      <div style={{ maxHeight: "100px", overflow: "auto" }}>
        {jobs.length === 0 ? (
          <div style={{
            padding: "0.5rem",
            color: "#334569",
            fontSize: "0.7rem",
            textAlign: "center",
          }}>
            No running jobs
          </div>
        ) : (
          jobs.map(job => (
            <div key={job.id} style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.25rem 0.5rem",
              borderBottom: "1px solid #1e293b",
              fontSize: "0.7rem",
            }}>
              <StatusDot status={job.status} />
              <span style={{
                fontFamily: "monospace",
                color: "#94a3b8",
                flex: 1,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}>
                {job.qubit || "?"}-{job.experiment || "?"}
              </span>
              <span style={{ color: "#64748b", fontSize: "0.6rem" }}>
                {getElapsed(job.submittedAt)}
              </span>
              {/* Progress bar */}
              <div style={{
                width: "40px",
                height: "2px",
                background: "#1e293b",
                borderRadius: "1px",
                overflow: "hidden",
                flexShrink: 0,
              }}>
                <div style={{
                  height: "100%",
                  width: job.status === "pending" ? "30%" : "70%",
                  background: "#38bdf8",
                  animation: job.status === "running" ? "pulse 1.5s ease-in-out infinite" : "none",
                }} />
              </div>
              <button
                onClick={() => handleCancel(job.id)}
                title="Cancel job"
                style={{
                  padding: "0.1rem 0.25rem",
                  fontSize: "0.55rem",
                  borderRadius: "0.2rem",
                  border: "1px solid #f87171",
                  background: "transparent",
                  color: "#f87171",
                  cursor: "pointer",
                  flexShrink: 0,
                }}
              >
                ✕
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// ── DataVaultList Component ───────────────────────────────────────────────────

function DataVaultCard({ refreshTrigger }: { refreshTrigger: number }) {
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
        console.error('[DataVaultCard] Failed to load config:', e);
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
        console.log('[DataVault] Mode check:', { modeRes, isOffline });
        setOfflineMode(isOffline);

        // Always try to load qubits - the service will return offline data if in offline mode
        const qubitsRes = await api.listQubits() as { qubits?: Array<{ name: string }>; source?: string; error?: string };
        console.log('[DataVault] Qubits loaded:', { source: qubitsRes.source, count: qubitsRes.qubits?.length });

        // If we're in offline mode OR the service returned offline data
        if (isOffline || qubitsRes.source === "offline") {
          if (qubitsRes.qubits && qubitsRes.qubits.length > 0) {
            setOfflineQubits(qubitsRes.qubits.map(q => q.name));
            if (!offlineSelectedQubit) {
              setOfflineSelectedQubit(qubitsRes.qubits[0].name);
            }
          }
        }
      } catch (e) {
        console.error('[DataVaultCard] Failed to check offline status:', e);
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
      console.error('[DataVaultCard] Failed to load offline datasets:', e);
    } finally {
      setOfflineLoading(false);
    }
  };

  // Handle plotting offline dataset (using v2 API with qter.fitData support)
  // Dispatches event to Experiments page for rendering
  const handlePlotOfflineDataset = async (ds: Dataset) => {
    setPlottingDsId(ds.id);
    try {
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
        console.error('[DataVaultCard] Plot error:', res.error);
      }
    } catch (e: any) {
      console.error('[DataVaultCard] Failed to plot:', e);
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

  return (
    <div style={{
      border: "1px solid #1e293b",
      borderRadius: "0.5rem",
      background: "#0a0f1a",
      overflow: "hidden",
      display: "flex",
      flexDirection: "column",
    }}>
      {/* Header */}
      <div style={{
        padding: "0.4rem 0.75rem",
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
      <div style={{ flex: 1, overflow: "auto", minHeight: "80px" }}>
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
              setSelectedDs(selectedDs?.id === ds.id ? null : ds);
            }}
            style={{
              padding: "0.25rem 0.75rem",
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

// ── QubitCard Component ───────────────────────────────────────────────────────

interface QubitCardProps {
  selectedQubit: string;
  onSelectQubit: (q: string) => void;
  qubits: string[];
  onLoadQubits: () => void;
}

function QubitCard({ selectedQubit, onSelectQubit, qubits, onLoadQubits }: QubitCardProps) {
  const [filter, setFilter] = useState("");
  const filteredQubits = qubits.filter(q => q.toLowerCase().includes(filter.toLowerCase()));

  return (
    <div style={{
      border: "1px solid #1e293b",
      borderRadius: "0.5rem",
      background: "#0a0f1a",
      overflow: "hidden",
    }}>
      <div style={{
        padding: "0.4rem 0.75rem",
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
        <span>🔧 QUBIT</span>
        <button
          onClick={onLoadQubits}
          style={{
            padding: "0.1rem 0.25rem",
            background: "transparent",
            border: "1px solid #334155",
            borderRadius: "0.2rem",
            color: "#64748b",
            cursor: "pointer",
            fontSize: "0.55rem",
          }}
        >
          ↻
        </button>
      </div>

      {/* Selected qubit display */}
      <div style={{
        padding: "0.25rem 0.5rem",
        borderBottom: "1px solid #1e293b",
        background: selectedQubit ? "#1e3a5f" : "#1e293b",
        border: "1px solid",
        borderColor: selectedQubit ? "#38bdf8" : "#334155",
        borderRadius: "0.25rem",
        margin: "0.4rem",
        fontFamily: "monospace",
        fontSize: "0.7rem",
        color: selectedQubit ? "#38bdf8" : "#64748b",
        textAlign: "center",
      }}>
        {selectedQubit || "Select qubit"}
      </div>

      {/* Filter input */}
      <div style={{ padding: "0.3rem 0.5rem", borderBottom: "1px solid #1e293b" }}>
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="🔍 Search..."
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

      {/* Qubit list */}
      <div style={{ maxHeight: "100px", overflow: "auto" }}>
        {filteredQubits.length === 0 && filter && (
          <div style={{ padding: "0.25rem", color: "#475569", fontSize: "0.65rem", textAlign: "center" }}>
            No match
          </div>
        )}
        {filteredQubits.map((q) => (
          <div
            key={q}
            onClick={() => onSelectQubit(q)}
            style={{
              padding: "0.2rem 0.5rem",
              borderBottom: "1px solid #1e293b",
              cursor: "pointer",
              background: selectedQubit === q ? "#1e3a5f" : "transparent",
            }}
          >
            <span style={{
              fontFamily: "monospace",
              fontSize: "0.65rem",
              color: selectedQubit === q ? "#38bdf8" : "#94a3b8",
            }}>
              {q}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── JobsPanel Main Component ──────────────────────────────────────────────────

interface JobsPanelProps {
  selectedQubit: string;
  onSelectQubit: (q: string) => void;
  qubits: string[];
  onLoadQubits: () => void;
}

export default function JobsPanel({ selectedQubit, onSelectQubit, qubits, onLoadQubits }: JobsPanelProps) {
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const handleRefresh = () => {
    setRefreshTrigger(t => t + 1);
  };

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      gap: "0.5rem",
      flex: 1,
      minHeight: 0,
      overflow: "auto",
    }}>
      {/* Running Jobs Card */}
      <RunningJobsCard refreshTrigger={refreshTrigger} />

      {/* DataVault Card */}
      <DataVaultCard refreshTrigger={refreshTrigger} />

      {/* Qubit Card */}
      <QubitCard
        selectedQubit={selectedQubit}
        onSelectQubit={onSelectQubit}
        qubits={qubits}
        onLoadQubits={onLoadQubits}
      />
    </div>
  );
}
