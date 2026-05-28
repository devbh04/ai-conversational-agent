"use client";

import { useState, useEffect } from "react";
import "./admin.css";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001";

type Stats = {
  real_estate: { total: number; booked: number; avg_duration: number; booking_rate: number };
  doctor: { total: number; booked: number; avg_duration: number; booking_rate: number };
  eximple: { total: number; booked: number; avg_duration: number; booking_rate: number };
  combined: { total: number; booked: number; avg_duration: number; booking_rate: number };
};

type CallLog = {
  id?: string;
  phone_number?: string;
  caller_name?: string;
  duration_seconds?: number;
  was_booked?: boolean;
  sentiment?: string;
  estimated_cost_usd?: number;
  interrupt_count?: number;
  transcript?: string;
  summary?: string;
  property_preferences?: string;
  dental_concern?: string;
  appointment_time?: string;
  booking_id?: string;
  created_at?: string;
  // Eximple fields
  company_name?: string;
  email?: string;
  trade_direction?: string;
  port_of_loading?: string;
  port_of_destination?: string;
  goods_description?: string;
  quantity?: number;
  quantity_unit?: string;
  incoterm?: string;
  dispatch_date?: string;
  container_type?: string;
  inquiry_complete?: boolean;
  services?: string[];
  missing_fields?: string[];
};

type CheckItem = { step: string; status: string; message: string };

export default function AdminPage() {
  const [isLoggedIn, setIsLoggedIn] = useState<boolean | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);

  const [tab, setTab] = useState("overview");
  const [stats, setStats] = useState<Stats | null>(null);
  const [reCalls, setReCalls] = useState<CallLog[]>([]);
  const [docCalls, setDocCalls] = useState<CallLog[]>([]);
  const [eximpleCalls, setEximpleCalls] = useState<CallLog[]>([]);
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [loadingCalls, setLoadingCalls] = useState(false);

  // System check
  const [checkItems, setCheckItems] = useState<CheckItem[]>([]);
  const [isChecking, setIsChecking] = useState(false);

  // Auth check
  useEffect(() => {
    const cookie = document.cookie.split(";").find((c) => c.trim().startsWith("auth="));
    setIsLoggedIn(!!cookie);
  }, []);

  // Fetch data on login
  useEffect(() => {
    if (isLoggedIn) {
      fetchStats();
    }
  }, [isLoggedIn]);

  // Fetch calls on tab change
  useEffect(() => {
    if (!isLoggedIn) return;
    if (tab === "real_estate" && reCalls.length === 0) fetchCalls("real_estate");
    if (tab === "doctor" && docCalls.length === 0) fetchCalls("doctor");
    if (tab === "eximple" && eximpleCalls.length === 0) fetchCalls("eximple");
  }, [tab, isLoggedIn]);

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
      if (data.success) setIsLoggedIn(true);
      else setLoginError(data.error || "Invalid credentials");
    } catch { setLoginError("Connection failed"); }
    setLoginLoading(false);
  }

  function handleLogout() {
    document.cookie = "auth=; path=/; max-age=0";
    setIsLoggedIn(false);
  }

  async function fetchStats() {
    try {
      const res = await fetch(`${BACKEND_URL}/api/admin/stats`);
      const data = await res.json();
      setStats(data);
    } catch { /* ignore */ }
  }

  async function fetchCalls(agent: string) {
    setLoadingCalls(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/admin/calls?agent=${agent}&limit=50`);
      const data = await res.json();
      if (agent === "real_estate") setReCalls(data);
      else if (agent === "doctor") setDocCalls(data);
      else if (agent === "eximple") setEximpleCalls(data);
    } catch { /* ignore */ }
    setLoadingCalls(false);
  }

  function runSystemCheck() {
    setIsChecking(true);
    setCheckItems([]);
    const evtSource = new EventSource(`${BACKEND_URL}/api/system-check`);
    evtSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.step === "done") { evtSource.close(); setIsChecking(false); return; }
      setCheckItems((prev) => {
        const idx = prev.findIndex((i) => i.step === data.step);
        if (idx >= 0) { const u = [...prev]; u[idx] = data; return u; }
        return [...prev, data];
      });
    };
    evtSource.onerror = () => { evtSource.close(); setIsChecking(false); };
  }

  function formatDuration(secs: number): string {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  }

  function formatDate(iso?: string): string {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  }

  // ── Render ─────────────────────────────────────────────────────────────

  if (isLoggedIn === null) return null;

  // Login
  if (!isLoggedIn) {
    return (
      <div className="login-container">
        <form className="login-card" onSubmit={handleLogin}>
          <h1>Admin Dashboard</h1>
          <p className="subtitle">Sign in to manage your agents</p>
          <div className="form-group">
            <label>Username</label>
            <input type="text" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <button type="submit" className="btn-primary" disabled={loginLoading || !username || !password}>
            {loginLoading ? "Signing in..." : "Sign In"}
          </button>
          {loginError && <p className="error-msg">{loginError}</p>}
        </form>
      </div>
    );
  }

  // Dashboard
  return (
    <div className="admin-container">
      <div className="admin-header">
        <h1>Admin Dashboard</h1>
        <button className="btn-logout" onClick={handleLogout}>Sign Out</button>
      </div>

      <div className="tabs">
        {[
          { key: "overview", label: "Overview" },
          { key: "real_estate", label: "🏢 Real Estate" },
          { key: "doctor", label: "🦷 Doctor" },
          { key: "eximple", label: "🚢 Eximple" },
          { key: "system", label: "System" },
        ].map((t) => (
          <button key={t.key} className={`tab${tab === t.key ? " active" : ""}`} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {tab === "overview" && (
        <>
          {stats ? (
            <>
              <div className="stat-grid">
                <div className="stat-card">
                  <div className="label">Total Calls</div>
                  <div className="value">{stats.combined.total}</div>
                </div>
                <div className="stat-card">
                  <div className="label">Booked</div>
                  <div className="value">{stats.combined.booked}</div>
                </div>
                <div className="stat-card">
                  <div className="label">Avg Duration</div>
                  <div className="value">{formatDuration(stats.combined.avg_duration)}</div>
                </div>
                <div className="stat-card">
                  <div className="label">Booking Rate</div>
                  <div className="value">{stats.combined.booking_rate}%</div>
                </div>
              </div>
              <div className="agent-split">
                <span>🏢 Real Estate: {stats.real_estate.total} calls, {stats.real_estate.booked} booked</span>
                <span>🦷 Doctor: {stats.doctor.total} calls, {stats.doctor.booked} booked</span>
                <span>🚢 Eximple: {stats.eximple.total} calls, {stats.eximple.booked} submitted</span>
              </div>
            </>
          ) : (
            <div className="loading"><span className="spinner" /> Loading stats...</div>
          )}
        </>
      )}

      {/* Call Logs Tab */}
      {(tab === "real_estate" || tab === "doctor" || tab === "eximple") && (
        <>
          {loadingCalls ? (
            <div className="loading"><span className="spinner" /> Loading calls...</div>
          ) : (
            <CallTable
              calls={tab === "real_estate" ? reCalls : tab === "doctor" ? docCalls : eximpleCalls}
              agent={tab}
              expandedRow={expandedRow}
              onToggle={(id) => setExpandedRow(expandedRow === id ? null : id)}
              formatDuration={formatDuration}
              formatDate={formatDate}
            />
          )}
        </>
      )}

      {/* System Tab */}
      {tab === "system" && (
        <div className="card system-check">
          <div className="system-check-header">
            <h3>System Status</h3>
            <button className="btn-secondary" onClick={runSystemCheck} disabled={isChecking}>
              {isChecking ? "Checking..." : "Run Check"}
            </button>
          </div>
          <div className="check-items">
            {checkItems.length === 0 && !isChecking && (
              <div className="check-item">Click &quot;Run Check&quot; to verify all systems</div>
            )}
            {checkItems.map((item, idx) => (
              <div key={idx} className={`check-item ${item.status}`}>
                {item.status === "checking" ? <span className="spinner" /> : <span>{item.status === "ok" ? "✓" : item.status === "error" ? "✗" : "⚠"}</span>}
                {item.message}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════════
// Call Table Component
// ═══════════════════════════════════════════════════════════════════════════════

function CallTable({
  calls,
  agent,
  expandedRow,
  onToggle,
  formatDuration,
  formatDate,
}: {
  calls: CallLog[];
  agent: string;
  expandedRow: string | null;
  onToggle: (id: string) => void;
  formatDuration: (s: number) => string;
  formatDate: (s?: string) => string;
}) {
  if (calls.length === 0) {
    return <div className="empty-state">No calls recorded yet.</div>;
  }

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Phone</th>
          <th>Name</th>
          <th>Duration</th>
          <th>Status</th>
          <th>Sentiment</th>
          <th>Date</th>
        </tr>
      </thead>
      <tbody>
        {calls.map((call, i) => {
          const rowId = call.id || `row-${i}`;
          const isExpanded = expandedRow === rowId;
          const isWeb = call.phone_number === "web-user";
          return (
            <>
              <tr key={rowId} className="expandable" onClick={() => onToggle(rowId)}>
                <td>
                  {isWeb ? <span className="badge web">Web</span> : (call.phone_number || "—")}
                </td>
                <td>{call.caller_name || "—"}</td>
                <td>{call.duration_seconds ? formatDuration(call.duration_seconds) : "—"}</td>
                <td>
                  {agent === "eximple" ? (
                    <span className={`badge ${call.inquiry_complete ? "complete" : "incomplete"}`}>
                      {call.inquiry_complete ? "Submitted" : "Incomplete"}
                    </span>
                  ) : (
                    <span className={`badge ${call.was_booked ? "booked" : "not-booked"}`}>
                      {call.was_booked ? "Booked" : "No booking"}
                    </span>
                  )}
                </td>
                <td>
                  <span className={`badge ${call.sentiment === "positive" ? "positive" : call.sentiment === "negative" || call.sentiment === "frustrated" ? "negative" : "neutral"}`}>
                    {call.sentiment || "—"}
                  </span>
                </td>
                <td>{formatDate(call.created_at)}</td>
              </tr>
              {isExpanded && (
                <tr key={`${rowId}-exp`}>
                  <td colSpan={6}>
                    <div className="expanded-content">
                      <div className="expanded-meta">
                        <span>Cost: ${call.estimated_cost_usd?.toFixed(4) || "—"}</span>
                        <span>Interrupts: {call.interrupt_count ?? "—"}</span>
                        {agent === "doctor" && call.dental_concern && <span>Concern: {call.dental_concern}</span>}
                        {agent === "doctor" && call.appointment_time && <span>Appointment: {call.appointment_time}</span>}
                        {agent === "real_estate" && call.property_preferences && <span>Prefs: {call.property_preferences}</span>}
                        {agent === "eximple" && call.company_name && <span>Company: {call.company_name}</span>}
                        {agent === "eximple" && call.trade_direction && <span>Trade: {call.trade_direction}</span>}
                        {agent === "eximple" && (call.port_of_loading || call.port_of_destination) && (
                          <span>Route: {call.port_of_loading || "—"} → {call.port_of_destination || "—"}</span>
                        )}
                        {agent === "eximple" && call.goods_description && <span>Goods: {call.goods_description}</span>}
                        {agent === "eximple" && call.container_type && <span>Container: {call.container_type}</span>}
                        {agent === "eximple" && call.incoterm && <span>Incoterm: {call.incoterm}</span>}
                        {agent === "eximple" && call.dispatch_date && <span>Dispatch: {call.dispatch_date}</span>}
                        {agent === "eximple" && call.services && call.services.length > 0 && (
                          <span>Services: {call.services.join(", ")}</span>
                        )}
                        {agent === "eximple" && call.missing_fields && call.missing_fields.length > 0 && (
                          <span className="missing-fields">Missing: {call.missing_fields.join(", ")}</span>
                        )}
                      </div>
                      {call.summary && (
                        <>
                          <h4>Summary</h4>
                          <div className="transcript-text">{call.summary}</div>
                        </>
                      )}
                      {call.transcript && (
                        <>
                          <h4>Transcript</h4>
                          <div className="transcript-text">{call.transcript}</div>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              )}
            </>
          );
        })}
      </tbody>
    </table>
  );
}
