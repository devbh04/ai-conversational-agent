"use client";

import { useState } from "react";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001";

const AGENTS = [
  {
    id: "real-estate-agent",
    name: "Real Estate",
    icon: "🏢",
    description: "Arjun, Property Consultant. Handles enquiries and schedules site visits.",
  },
  {
    id: "real-estate-ny-agent",
    name: "NY Real Estate",
    icon: "🗽",
    description: "David, NY Real Estate Agent. Confident & casual property consultant speaking English, Spanish, German, and French.",
  },
  {
    id: "doctor-nehra",
    name: "Dr. Nehra's Clinic",
    icon: "🦷",
    description: "Arjun, AI Receptionist. Books dental appointments with slot awareness.",
  },
  {
    id: "eximple-agent",
    name: "Trade",
    icon: "🚢",
    description: "Arjun, Trade Inquiry Consultant. Collects cross-border shipment inquiries.",
  },
];

export default function Home() {
  const [selectedAgent, setSelectedAgent] = useState("");
  const [callingMode, setCallingMode] = useState<"national" | "international">("national");
  const [phone, setPhone] = useState("");
  const [intlPhone, setIntlPhone] = useState("");
  const [callStatus, setCallStatus] = useState("");
  const [callStatusType, setCallStatusType] = useState<"" | "active" | "error">("");
  const [isCalling, setIsCalling] = useState(false);

  async function handleCall() {
    const isIntl = callingMode === "international";
    const currentPhone = isIntl ? intlPhone : phone;
    const minLength = isIntl ? 7 : 10;

    if (!selectedAgent || currentPhone.length < minLength) return;
    setIsCalling(true);
    setCallStatus("Dispatching call...");
    setCallStatusType("active");

    const fullPhone = isIntl 
      ? (currentPhone.startsWith("+") ? currentPhone : `+${currentPhone}`) 
      : (currentPhone.startsWith("+") ? currentPhone : `+91${currentPhone}`);

    try {
      const res = await fetch(`${BACKEND_URL}/api/dispatch-call`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_type: selectedAgent, phone_number: fullPhone }),
      });
      const data = await res.json();
      if (data.success) {
        setCallStatus(`Call dispatched — room: ${data.room}`);
        setCallStatusType("active");
      } else {
        setCallStatus(data.error || "Failed to dispatch");
        setCallStatusType("error");
      }
    } catch {
      setCallStatus("Cannot reach backend. Is the system running?");
      setCallStatusType("error");
    }
    setIsCalling(false);
  }

  return (
    <div className="container">
      <h1 className="page-title">Voice Agent</h1>
      <p className="page-subtitle">Select an agent and make a call</p>

      <div className="agent-grid">
        {AGENTS.map((agent) => (
          <div
            key={agent.id}
            className={`agent-card${selectedAgent === agent.id ? " selected" : ""}`}
            onClick={() => setSelectedAgent(agent.id)}
          >
            <div className="agent-icon">{agent.icon}</div>
            <h3>{agent.name}</h3>
            <p>{agent.description}</p>
          </div>
        ))}
      </div>

      <div className="calling-mode-tabs">
        <button
          className={`tab-btn${callingMode === "national" ? " active" : ""}`}
          onClick={() => { setCallingMode("national"); setCallStatus(""); }}
        >
          🇮🇳 National (India)
        </button>
        <button
          className={`tab-btn${callingMode === "international" ? " active" : ""}`}
          onClick={() => { setCallingMode("international"); setCallStatus(""); }}
        >
          🌐 International
        </button>
      </div>

      <div className="phone-section">
        {callingMode === "national" ? (
          <div className="mode-content">
            <div className="phone-input-wrapper">
              <div className="phone-prefix">+91</div>
              <input
                className="phone-input"
                type="tel"
                placeholder="9876543210"
                value={phone}
                onChange={(e) => setPhone(e.target.value.replace(/\D/g, "").slice(0, 10))}
              />
            </div>
            <p className="mode-hint">National India calls are routed through local gateway lines.</p>
          </div>
        ) : (
          <div className="mode-content">
            <div className="phone-input-wrapper">
              <div className="phone-prefix">+</div>
              <input
                className="phone-input"
                type="tel"
                placeholder="14155551234"
                value={intlPhone}
                onChange={(e) => setIntlPhone(e.target.value.replace(/\D/g, "").slice(0, 15))}
              />
            </div>
            <p className="mode-hint warning-hint">⚠️ International calls may fail depending on carrier & routing constraints.</p>
          </div>
        )}
      </div>

      <button
        className={`btn-primary${isCalling ? " calling" : ""}`}
        disabled={
          !selectedAgent || 
          isCalling || 
          (callingMode === "national" ? phone.length < 10 : intlPhone.length < 7)
        }
        onClick={handleCall}
      >
        {isCalling ? (
          <><span className="spinner" /> Calling...</>
        ) : (
          <>📞 Call Now</>
        )}
      </button>

      {callStatus && (
        <div className={`call-status${callStatusType ? ` ${callStatusType}` : ""}`}>
          {callStatus}
        </div>
      )}

      <div className="fallback-box">
        <p className="fallback-text">
          {callingMode === "international"
            ? "Avoid international trunk failures. Connect directly using your browser mic:"
            : "Prefer not to make a phone call? Try the voice agent directly:"}
        </p>
        <a href={`/chat?agent=${selectedAgent || ""}`} className="btn-chat-fallback">
          🎤 Talk to {selectedAgent ? AGENTS.find(a => a.id === selectedAgent)?.name : "Agent"} in Browser
        </a>
      </div>

      <div className="footer-links">
        <a href="/admin">Admin Dashboard</a>
      </div>
    </div>
  );
}
