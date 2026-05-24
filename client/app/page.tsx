"use client";

import { useState, useEffect } from "react";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001";

type Agent = {
  id: string;
  name: string;
  icon: string;
  description: string;
};

const AGENTS: Agent[] = [
  {
    id: "real-estate-agent",
    name: "Real Estate Agent",
    icon: "🏢",
    description: "Arjun, Property Consultant. Handles property enquiries and schedules site visits.",
  },
  {
    id: "doctor-nehra",
    name: "Dr. Nehra's Clinic",
    icon: "🦷",
    description: "Arjun, AI Receptionist. Books dental appointments with available slot awareness.",
  },
];

type CheckItem = {
  step: string;
  status: "checking" | "ok" | "error" | "warn";
  message: string;
};

export default function Home() {
  const [isLoggedIn, setIsLoggedIn] = useState<boolean | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);

  // Dashboard state
  const [selectedAgent, setSelectedAgent] = useState<string>("");
  const [phone, setPhone] = useState("");
  const [callStatus, setCallStatus] = useState("");
  const [callStatusType, setCallStatusType] = useState<"" | "active" | "error">("");
  const [isCalling, setIsCalling] = useState(false);

  // System check
  const [checkItems, setCheckItems] = useState<CheckItem[]>([]);
  const [isChecking, setIsChecking] = useState(false);

  // Check auth on mount
  useEffect(() => {
    const cookie = document.cookie.split(";").find((c) => c.trim().startsWith("auth="));
    setIsLoggedIn(!!cookie);
  }, []);

  // ── Login ──────────────────────────────────────────────────────────────
  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoginLoading(true);
    setLoginError("");
    try {
      const res = await fetch("/api/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (data.success) {
        setIsLoggedIn(true);
      } else {
        setLoginError(data.error || "Invalid credentials");
      }
    } catch {
      setLoginError("Connection failed");
    }
    setLoginLoading(false);
  }

  function handleLogout() {
    document.cookie = "auth=; path=/; max-age=0";
    setIsLoggedIn(false);
    setUsername("");
    setPassword("");
  }

  // ── Dispatch Call ──────────────────────────────────────────────────────
  async function handleCall() {
    if (!selectedAgent || !phone || phone.length < 10) return;

    setIsCalling(true);
    setCallStatus("Dispatching call...");
    setCallStatusType("active");

    const fullPhone = phone.startsWith("+") ? phone : `+91${phone}`;
    try {
      const res = await fetch(`${BACKEND_URL}/api/dispatch-call`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_type: selectedAgent, phone_number: fullPhone }),
      });
      const data = await res.json();
      if (data.success) {
        setCallStatus(`✅ Call dispatched! Room: ${data.room}`);
        setCallStatusType("active");
      } else {
        setCallStatus(`❌ ${data.error || "Failed to dispatch"}`);
        setCallStatusType("error");
      }
    } catch (err) {
      setCallStatus("❌ Failed to connect to backend. Is the system running?");
      setCallStatusType("error");
    }
    setIsCalling(false);
  }

  // ── System Check ───────────────────────────────────────────────────────
  function runSystemCheck() {
    setIsChecking(true);
    setCheckItems([]);

    const evtSource = new EventSource(`${BACKEND_URL}/api/system-check`);

    evtSource.onmessage = (event) => {
      const data = JSON.parse(event.data) as CheckItem;
      if (data.step === "done") {
        evtSource.close();
        setIsChecking(false);
        return;
      }
      setCheckItems((prev) => {
        const existing = prev.findIndex((i) => i.step === data.step);
        if (existing >= 0) {
          const updated = [...prev];
          updated[existing] = data;
          return updated;
        }
        return [...prev, data];
      });
    };

    evtSource.onerror = () => {
      evtSource.close();
      setIsChecking(false);
      setCheckItems((prev) => [
        ...prev,
        { step: "connection", status: "error", message: "❌ Cannot reach backend — system may be sleeping. Try again in 30s." },
      ]);
    };
  }

  // ── Render ─────────────────────────────────────────────────────────────

  // Loading state
  if (isLoggedIn === null) return null;

  // Login page
  if (!isLoggedIn) {
    return (
      <div className="login-container">
        <form className="login-card" onSubmit={handleLogin}>
          <h1>Voice Agent Console</h1>
          <p>Sign in to manage your AI agents</p>
          <div className="form-group">
            <label>Username</label>
            <input
              id="login-username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="admin"
              autoFocus
            />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input
              id="login-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </div>
          <button
            id="login-submit"
            type="submit"
            className="btn-primary"
            disabled={loginLoading || !username || !password}
          >
            {loginLoading ? "Signing in..." : "Sign In"}
          </button>
          {loginError && <p className="error-msg">{loginError}</p>}
        </form>
      </div>
    );
  }

  // Dashboard
  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h1>Voice Agent Console</h1>
        <p>Select an agent and make a call</p>
      </div>

      {/* Agent Selection */}
      <div className="agent-grid">
        {AGENTS.map((agent) => (
          <div
            key={agent.id}
            id={`agent-${agent.id}`}
            className={`agent-card${selectedAgent === agent.id ? " selected" : ""}`}
            onClick={() => setSelectedAgent(agent.id)}
          >
            <div className="agent-icon">{agent.icon}</div>
            <h3>{agent.name}</h3>
            <p>{agent.description}</p>
          </div>
        ))}
      </div>

      {/* Phone Input */}
      <div className="phone-section">
        <div className="phone-input-wrapper">
          <div className="phone-prefix">🇮🇳 +91</div>
          <input
            id="phone-input"
            className="phone-input"
            type="tel"
            placeholder="9876543210"
            value={phone}
            onChange={(e) => setPhone(e.target.value.replace(/\D/g, "").slice(0, 10))}
          />
        </div>
      </div>

      {/* Call Button */}
      <button
        id="call-button"
        className={`btn-call${isCalling ? " calling" : ""}`}
        disabled={!selectedAgent || phone.length < 10 || isCalling}
        onClick={handleCall}
      >
        {isCalling ? (
          <>
            <span className="spinner" /> Calling...
          </>
        ) : (
          <>📞 Call Now</>
        )}
      </button>

      {/* Call Status */}
      {callStatus && (
        <div className={`call-status${callStatusType ? ` ${callStatusType}` : ""}`}>
          {callStatus}
        </div>
      )}

      {/* System Check */}
      <div className="system-check">
        <div className="system-check-header">
          <h3>🔍 System Status</h3>
          <button
            id="system-check-btn"
            className="btn-check"
            onClick={runSystemCheck}
            disabled={isChecking}
          >
            {isChecking ? "Checking..." : "Run Check"}
          </button>
        </div>
        <div className="check-items">
          {checkItems.length === 0 && !isChecking && (
            <div className="check-item">Click &quot;Run Check&quot; to verify all systems</div>
          )}
          {checkItems.map((item, idx) => (
            <div key={idx} className={`check-item ${item.status}`}>
              {item.status === "checking" ? (
                <span className="spinner" />
              ) : (
                <span>{item.status === "ok" ? "✓" : item.status === "error" ? "✗" : "⚠"}</span>
              )}
              {item.message}
            </div>
          ))}
        </div>
      </div>

      <button className="btn-logout" onClick={handleLogout}>
        Sign Out
      </button>
    </div>
  );
}
