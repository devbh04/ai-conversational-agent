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
    id: "doctor-nehra",
    name: "Dr. Nehra's Clinic",
    icon: "🦷",
    description: "Arjun, AI Receptionist. Books dental appointments with slot awareness.",
  },
  {
    id: "eximple-agent",
    name: "Eximple Trade",
    icon: "🚢",
    description: "Arjun, Trade Inquiry Consultant. Collects cross-border shipment inquiries.",
  },
];

export default function Home() {
  const [selectedAgent, setSelectedAgent] = useState("");
  const [phone, setPhone] = useState("");
  const [callStatus, setCallStatus] = useState("");
  const [callStatusType, setCallStatusType] = useState<"" | "active" | "error">("");
  const [isCalling, setIsCalling] = useState(false);

  async function handleCall() {
    if (!selectedAgent || phone.length < 10) return;
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

      <div className="phone-section">
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
      </div>

      <button
        className={`btn-primary${isCalling ? " calling" : ""}`}
        disabled={!selectedAgent || phone.length < 10 || isCalling}
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

      <a href="/chat" className="chat-link">
        💬 Don&apos;t want to call? Chat with the agent directly
      </a>

      <div className="footer-links">
        <a href="/admin">Admin Dashboard</a>
      </div>
    </div>
  );
}
