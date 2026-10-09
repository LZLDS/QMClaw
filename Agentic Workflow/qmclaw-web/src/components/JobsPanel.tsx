"use client";

import { useState, useEffect, useCallback } from "react";
import { api, JobResult } from "../lib/api";
import DataVaultPicker from "./DataVaultPicker";

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

      {/* DataVault Card (抽取为 DataVaultPicker，选择行为与原 DataVaultCard 一致) */}
      <DataVaultPicker refreshTrigger={refreshTrigger} />

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
