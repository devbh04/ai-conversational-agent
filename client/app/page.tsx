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
    warning: "Try only if you are out of India",
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

  async function handleCall(mode: "national" | "international") {
    const isIntl = mode === "international";
    const currentPhone = isIntl ? intlPhone : phone;
    const minLength = isIntl ? 7 : 10;

    if (!selectedAgent || currentPhone.length < minLength) return;
    setIsCalling(true);
    setCallingMode(mode);
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
        setCallStatus(`Call dispatched to ${fullPhone} — room: ${data.room}`);
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
            {agent.warning && (
              <div className="agent-card-warning">
                ⚠️ {agent.warning}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="calling-channels-container">
        {/* National Calling Card */}
        <div className="calling-channel-card">
          <div className="channel-header">
            <span className="channel-icon">🇮🇳</span>
            <h3>National Call (India)</h3>
          </div>
          <p className="channel-desc">Routed through local direct gateway lines.</p>
          
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

          <button
            className={`btn-primary${isCalling && callingMode === "national" ? " calling" : ""}`}
            disabled={!selectedAgent || phone.length < 10 || isCalling}
            onClick={() => handleCall("national")}
          >
            {isCalling && callingMode === "national" ? (
              <><span className="spinner" /> Calling...</>
            ) : (
              <>📞 Call National</>
            )}
          </button>

          <div className="channel-fallback-note">
            Prefer not to call?{" "}
            <a href={`/chat?agent=${selectedAgent || ""}`} className="fallback-link-inline">
              Try browser agent →
            </a>
          </div>
        </div>

        {/* International Calling Card */}
        <div className="calling-channel-card">
          <div className="channel-header">
            <span className="channel-icon">🌐</span>
            <h3>International Call</h3>
          </div>
          <p className="channel-desc">Route calls to any country outside India.</p>

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

          <button
            className={`btn-primary${isCalling && callingMode === "international" ? " calling" : ""}`}
            disabled={!selectedAgent || intlPhone.length < 7 || isCalling}
            onClick={() => handleCall("international")}
          >
            {isCalling && callingMode === "international" ? (
              <><span className="spinner" /> Calling...</>
            ) : (
              <>📞 Call International</>
            )}
          </button>

          <div className="channel-fallback-note warning-note">
            ⚠️ Trunk routing might fail sometimes.{" "}
            <a href={`/chat?agent=${selectedAgent || ""}`} className="fallback-link-inline highlighted">
              Try browser chat →
            </a>
          </div>
        </div>
      </div>

      {callStatus && (
        <div className={`call-status${callStatusType ? ` ${callStatusType}` : ""}`}>
          {callStatus}
        </div>
      )}

      <div className="footer-links">
        <a href="/admin">Admin Dashboard</a>
      </div>
    </div>
  );
}
