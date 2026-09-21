"use client";

/**
 * QCATab - QCA (Quantum Calibration Agent) Tab Component
 *
 * Provides:
 * - Chat interface for natural language experiment control
 * - Experiment execution
 * - History view
 */

import { useState, useRef, useEffect } from "react";
import { api } from "../lib/api";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  type?: string;
  data?: any;
}

interface HistoryItem {
  id: string;
  type: string;
  target?: string;
  timestamp: string;
  status: string;
}

interface Experiment {
  name: string;
  description: string;
  parameters?: any[];
}

export default function QCATab() {
  const [mode, setMode] = useState<"chat" | "history" | "experiments">("chat");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [selectedExp, setSelectedExp] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load experiments on mount
  useEffect(() => {
    loadExperiments();
    loadHistory();
  }, []);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const loadExperiments = async () => {
    try {
      const data = await api.qcaCapabilities();
      if (data.experiments) {
        setExperiments(data.experiments);
      }
    } catch (err) {
      console.error("Failed to load experiments:", err);
    }
  };

  const loadHistory = async () => {
    try {
      const data = await api.qcaHistory(50);
      if (data.experiments) {
        setHistory(data.experiments);
      }
    } catch (err) {
      console.error("Failed to load history:", err);
    }
  };

  const sendMessage = async () => {
    if (!input.trim() || loading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const response = await api.qcaChat({
        message: userMessage.content,
        thread_id: `qca_${Date.now()}`,
      });

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: response.content || response.error || "No response",
        timestamp: new Date(),
        type: response.type,
        data: response,
      };

      setMessages(prev => [...prev, assistantMessage]);

      // Refresh history if an experiment was run
      if (response.type === "experiment") {
        loadHistory();
      }
    } catch (err: any) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: `Error: ${err.message}`,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const runExperiment = async (expName: string) => {
    setLoading(true);
    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: `Run ${expName}`,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMessage]);

    try {
      const response = await api.qcaRun({
        experiment_name: expName,
        params: {},
      });

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: response.success
          ? `✅ Experiment completed!\nStatus: ${response.status}\nID: ${response.id}`
          : `❌ Error: ${response.error || "Unknown error"}`,
        timestamp: new Date(),
        type: "experiment",
        data: response,
      };

      setMessages(prev => [...prev, assistantMessage]);
      loadHistory();
    } catch (err: any) {
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: `Error: ${err.message}`,
        timestamp: new Date(),
      }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "#0f172a" }}>
      {/* Mode tabs */}
      <div style={{
        display: "flex",
        gap: "0.5rem",
        padding: "0.75rem",
        borderBottom: "1px solid #1e293b",
      }}>
        {(["chat", "experiments", "history"] as const).map(m => (
          <button
            key={m}
            onClick={() => setMode(m)}
            style={{
              padding: "0.4rem 1rem",
              borderRadius: "0.375rem",
              border: "none",
              background: mode === m ? "#38bdf8" : "#1e293b",
              color: mode === m ? "#0f172a" : "#94a3b8",
              fontWeight: 600,
              cursor: "pointer",
              textTransform: "capitalize",
            }}
          >
            {m}
          </button>
        ))}
      </div>

      {/* Content area */}
      <div style={{ flex: 1, overflow: "hidden", display: "flex" }}>
        {/* Main content */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          {mode === "chat" && (
            <>
              {/* Messages */}
              <div style={{ flex: 1, overflow: "auto", padding: "1rem" }}>
                {messages.length === 0 && (
                  <div style={{ textAlign: "center", color: "#64748b", padding: "2rem" }}>
                    <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>🔬</div>
                    <div>QCA - Quantum Calibration Agent</div>
                    <div style={{ fontSize: "0.875rem", marginTop: "0.5rem" }}>
                      Try: "run t1 measurement" or "list experiments"
                    </div>
                  </div>
                )}
                {messages.map(msg => (
                  <div
                    key={msg.id}
                    style={{
                      marginBottom: "1rem",
                      display: "flex",
                      flexDirection: "column",
                      alignItems: msg.role === "user" ? "flex-end" : "flex-start",
                    }}
                  >
                    <div style={{
                      maxWidth: "80%",
                      padding: "0.75rem 1rem",
                      borderRadius: "0.5rem",
                      background: msg.role === "user" ? "#1e3a5f" : "#1e293b",
                      color: "#e2e8f0",
                      whiteSpace: "pre-wrap",
                    }}>
                      {msg.content}
                    </div>
                    <div style={{ fontSize: "0.7rem", color: "#475569", marginTop: "0.25rem" }}>
                      {msg.timestamp.toLocaleTimeString()}
                    </div>
                  </div>
                ))}
                {loading && (
                  <div style={{ color: "#64748b", fontStyle: "italic" }}>
                    ⏳ Processing...
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Input */}
              <div style={{ padding: "1rem", borderTop: "1px solid #1e293b" }}>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <input
                    type="text"
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && !e.shiftKey && sendMessage()}
                    placeholder="Ask QCA to run experiments..."
                    disabled={loading}
                    style={{
                      flex: 1,
                      padding: "0.75rem 1rem",
                      background: "#1e293b",
                      border: "1px solid #334155",
                      borderRadius: "0.5rem",
                      color: "#e2e8f0",
                      fontSize: "0.875rem",
                      outline: "none",
                    }}
                  />
                  <button
                    onClick={sendMessage}
                    disabled={loading || !input.trim()}
                    style={{
                      padding: "0.75rem 1.5rem",
                      background: loading ? "#334155" : "#38bdf8",
                      border: "none",
                      borderRadius: "0.5rem",
                      color: loading ? "#64748b" : "#0f172a",
                      fontWeight: 600,
                      cursor: loading ? "not-allowed" : "pointer",
                    }}
                  >
                    Send
                  </button>
                </div>
              </div>
            </>
          )}

          {mode === "experiments" && (
            <div style={{ flex: 1, overflow: "auto", padding: "1rem" }}>
              <h3 style={{ color: "#e2e8f0", marginBottom: "1rem" }}>Available Experiments</h3>
              <div style={{ display: "grid", gap: "0.75rem" }}>
                {experiments.map(exp => (
                  <div
                    key={exp.name}
                    onClick={() => runExperiment(exp.name)}
                    style={{
                      padding: "1rem",
                      background: "#1e293b",
                      border: "1px solid #334155",
                      borderRadius: "0.5rem",
                      cursor: "pointer",
                      transition: "border-color 0.2s",
                    }}
                    onMouseEnter={e => (e.currentTarget.style.borderColor = "#38bdf8")}
                    onMouseLeave={e => (e.currentTarget.style.borderColor = "#334155")}
                  >
                    <div style={{ color: "#38bdf8", fontWeight: 600, marginBottom: "0.25rem" }}>
                      {exp.name}
                    </div>
                    <div style={{ color: "#94a3b8", fontSize: "0.875rem" }}>
                      {exp.description || "No description"}
                    </div>
                  </div>
                ))}
                {experiments.length === 0 && (
                  <div style={{ color: "#64748b", textAlign: "center", padding: "2rem" }}>
                    No experiments available
                  </div>
                )}
              </div>
            </div>
          )}

          {mode === "history" && (
            <div style={{ flex: 1, overflow: "auto", padding: "1rem" }}>
              <h3 style={{ color: "#e2e8f0", marginBottom: "1rem" }}>Experiment History</h3>
              <div style={{ display: "grid", gap: "0.5rem" }}>
                {history.map(item => (
                  <div
                    key={item.id}
                    style={{
                      padding: "0.75rem 1rem",
                      background: "#1e293b",
                      border: "1px solid #334155",
                      borderRadius: "0.375rem",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <div>
                      <div style={{ color: "#38bdf8", fontWeight: 600 }}>
                        {item.type}
                        {item.target && <span style={{ color: "#94a3b8" }}> ({item.target})</span>}
                      </div>
                      <div style={{ color: "#64748b", fontSize: "0.75rem" }}>
                        {new Date(item.timestamp).toLocaleString()}
                      </div>
                    </div>
                    <div style={{
                      padding: "0.25rem 0.5rem",
                      borderRadius: "0.25rem",
                      background: item.status === "success" ? "#166534" : "#7f1d1d",
                      color: item.status === "success" ? "#22c55e" : "#ef4444",
                      fontSize: "0.75rem",
                    }}>
                      {item.status}
                    </div>
                  </div>
                ))}
                {history.length === 0 && (
                  <div style={{ color: "#64748b", textAlign: "center", padding: "2rem" }}>
                    No experiment history
                  </div>
                )}
              </div>
              <button
                onClick={loadHistory}
                style={{
                  marginTop: "1rem",
                  padding: "0.5rem 1rem",
                  background: "#1e293b",
                  border: "1px solid #334155",
                  borderRadius: "0.375rem",
                  color: "#94a3b8",
                  cursor: "pointer",
                }}
              >
                ↻ Refresh
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
