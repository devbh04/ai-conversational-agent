"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useVoiceAssistant,
  useChat,
  useRoomContext,
} from "@livekit/components-react";
import "@livekit/components-styles";
import "./chat.css";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8001";
const MAX_TURNS = 10;
const MAX_TIME_SECS = 150; // 2:30

const AGENTS = [
  { id: "real-estate-agent", name: "Real Estate", icon: "🏢", desc: "Property enquiries & site visits" },
  { id: "real-estate-ny-agent", name: "NY Real Estate", icon: "🗽", desc: "David, NY Real Estate Agent (EN/ES/DE/FR)" },
  { id: "doctor-nehra", name: "Dr. Nehra", icon: "🦷", desc: "Dental appointments & availability" },
];

type Stage = "cooldown" | "select" | "chat" | "summary";
type Availability = "available" | "busy" | "unknown";

export default function ChatPage() {
  const [stage, setStage] = useState<Stage>("select");
  const [availability, setAvailability] = useState<Availability>("unknown");
  const [selectedAgent, setSelectedAgent] = useState("");
  const [token, setToken] = useState("");
  const [lkUrl, setLkUrl] = useState("");
  const [roomName, setRoomName] = useState("");
  const [error, setError] = useState("");
  const [summaryData, setSummaryData] = useState<{ call_benefits: string[]; contact_url: string } | null>(null);
  const [starting, setStarting] = useState(false);

  // Check cooldown cookie on mount
  useEffect(() => {
    if (document.cookie.includes("web_chat_used=1")) {
      setStage("cooldown");
    }
  }, []);

  // SSE availability stream
  useEffect(() => {
    if (stage !== "select") return;

    const evtSource = new EventSource(`${BACKEND_URL}/api/web-chat/status`);

    evtSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.status === "available") setAvailability("available");
        else if (data.status === "busy") setAvailability("busy");
        // ignore heartbeats
      } catch { /* ignore parse errors */ }
    };

    evtSource.onerror = () => {
      setAvailability("unknown");
    };

    return () => evtSource.close();
  }, [stage]);

  // Start chat
  async function handleStart() {
    if (!selectedAgent) return;
    setStarting(true);
    setError("");

    try {
      const res = await fetch(`${BACKEND_URL}/api/web-chat/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ agent_type: selectedAgent }),
      });

      if (res.status === 409) {
        setAvailability("busy");
        setStarting(false);
        return;
      }

      const data = await res.json();
      if (data.error) {
        setError(data.error);
        setStarting(false);
        return;
      }

      setToken(data.token);
      setLkUrl(data.livekit_url);
      setRoomName(data.room_name);
      setStage("chat");
    } catch {
      setError("Cannot connect to backend");
    }
    setStarting(false);
  }

  // End chat
  const handleEnd = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/web-chat/end`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ room_name: roomName }),
      });
      const data = await res.json();
      setSummaryData(data);
    } catch {
      setSummaryData({
        call_benefits: [
          "📱 WhatsApp confirmation with booking details",
          "🔔 Follow-up reminders",
          "👤 Direct connection to our team",
          "⚡ Priority scheduling and support",
        ],
        contact_url: "https://devbhangale.vercel.app",
      });
    }

    // Set 3-day cooldown cookie
    document.cookie = "web_chat_used=1; path=/; max-age=259200; SameSite=Lax";
    setStage("summary");
  }, [roomName]);

  // ── Render ─────────────────────────────────────────────────────────────

  // Cooldown
  if (stage === "cooldown") {
    return (
      <div className="chat-container">
        <div className="cooldown-screen">
          <div className="icon">🎤</div>
          <h2>Demo Already Used</h2>
          <p>
            You&apos;ve already tried the voice demo. For an extended
            demo or to learn more, reach out to us.
          </p>
          <a href="https://devbhangale.vercel.app" className="btn-contact">
            Contact for More →
          </a>
          <a href="/" style={{ fontSize: "0.8rem", marginTop: "0.5rem" }}>← Back to Home</a>
        </div>
      </div>
    );
  }

  // Summary
  if (stage === "summary") {
    return (
      <div className="chat-container">
        <div className="summary-screen">
          <div className="icon">✅</div>
          <h2>Chat Complete</h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem" }}>
            With a real phone call, you&apos;d also get:
          </p>
          <ul className="benefits-list">
            {(summaryData?.call_benefits || []).map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
          <div className="summary-actions">
            <a href="/" className="btn-secondary" style={{ textDecoration: "none" }}>← Home</a>
            <a href={summaryData?.contact_url || "https://devbhangale.vercel.app"} className="btn-primary" style={{ textDecoration: "none", width: "auto", padding: "0.6rem 1.25rem" }}>
              Contact for More →
            </a>
          </div>
        </div>
      </div>
    );
  }

  // Voice chat
  if (stage === "chat" && token && lkUrl) {
    return (
      <div className="chat-container">
        <LiveKitRoom
          token={token}
          serverUrl={lkUrl}
          connect={true}
          onDisconnected={handleEnd}
        >
          <RoomAudioRenderer />
          <ActiveChat
            maxTurns={MAX_TURNS}
            maxTime={MAX_TIME_SECS}
            onEnd={handleEnd}
          />
        </LiveKitRoom>
      </div>
    );
  }

  // Agent selection
  return (
    <div className="chat-container">
      <h1 className="page-title">Voice Chat</h1>
      <p className="page-subtitle">Talk to our AI agent directly from your browser</p>

      <div className="demo-banner">
        ⏱️ Demo: {MAX_TURNS} messages max · {Math.floor(MAX_TIME_SECS / 60)}:{(MAX_TIME_SECS % 60).toString().padStart(2, "0")} time limit · 1 session every 3 days
      </div>

      {availability === "busy" && (
        <div className="busy-banner">
          <span className="spinner" />
          Agent is in another conversation. Please wait — this will update automatically.
        </div>
      )}

      <div className="agent-grid">
        {AGENTS.map((agent) => (
          <div
            key={agent.id}
            className={`agent-card${selectedAgent === agent.id ? " selected" : ""}`}
            onClick={() => setSelectedAgent(agent.id)}
          >
            <div className="agent-icon">{agent.icon}</div>
            <h3>{agent.name}</h3>
            <p>{agent.desc}</p>
          </div>
        ))}
      </div>

      <button
        className="btn-primary"
        disabled={!selectedAgent || availability !== "available" || starting}
        onClick={handleStart}
      >
        {starting ? (
          <><span className="spinner" /> Connecting...</>
        ) : availability === "busy" ? (
          "Agent Busy — Please Wait"
        ) : (
          "🎤 Start Voice Chat"
        )}
      </button>

      {error && <div className="call-status error">{error}</div>}

      <div className="footer-links">
        <a href="/">← Back to Call</a>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════════
// Active Chat Component — inside LiveKitRoom context
// ═══════════════════════════════════════════════════════════════════════════════

function ActiveChat({
  maxTurns,
  maxTime,
  onEnd,
}: {
  maxTurns: number;
  maxTime: number;
  onEnd: () => void;
}) {
  const { state, agentTranscriptions } = useVoiceAssistant();
  const room = useRoomContext();
  const { send, chatMessages } = useChat();
  const [timeLeft, setTimeLeft] = useState(maxTime);
  const [textInput, setTextInput] = useState("");
  const transcriptRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Count turns: each final agent transcription segment = 1 turn pair
  // agentTranscriptions has only agent segments; each segment with isFinal=true is a completed response
  const turnCount = agentTranscriptions.filter((t) => t.final).length + chatMessages.filter((m) => m.from?.isLocal).length;

  // Timer countdown
  useEffect(() => {
    timerRef.current = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          room.disconnect();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [room]);

  // Auto-close on max turns
  useEffect(() => {
    if (turnCount >= maxTurns) {
      setTimeout(() => room.disconnect(), 1500);
    }
  }, [turnCount, maxTurns, room]);

  // Auto-scroll transcript
  useEffect(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [agentTranscriptions, chatMessages]);

  // Send text message
  function handleSendText() {
    if (!textInput.trim()) return;
    send(textInput.trim());
    setTextInput("");
  }

  const minutes = Math.floor(timeLeft / 60);
  const seconds = timeLeft % 60;
  const timerStr = `${minutes}:${seconds.toString().padStart(2, "0")}`;

  const stateLabel: Record<string, string> = {
    disconnected: "Connecting...",
    connecting: "Connecting...",
    initializing: "Connecting...",
    listening: "Listening",
    thinking: "Thinking...",
    speaking: "Speaking",
  };

  const orbClass =
    state === "listening" ? "listening"
    : state === "thinking" ? "thinking"
    : state === "speaking" ? "speaking"
    : "connecting";

  return (
    <div className="voice-chat">
      <div className="chat-header">
        <h2>Voice Chat</h2>
        <div className="chat-meta">
          <span className={`timer${timeLeft <= 30 ? " warning" : ""}`}>{timerStr}</span>
          <span className="turns">{turnCount}/{maxTurns}</span>
        </div>
      </div>

      <div className="visualizer-section">
        <div className="orb-container">
          <div className={`orb ${orbClass}`} />
        </div>
        <span className="agent-state">{stateLabel[state] || state}</span>
      </div>

      <div className="transcript" ref={transcriptRef}>
        {agentTranscriptions.length === 0 && chatMessages.length === 0 ? (
          <div className="transcript-empty">
            Conversation will appear here...
          </div>
        ) : (
          <>
            {agentTranscriptions.map((t, i) => (
              <div key={`t-${i}`} className="transcript-msg agent">
                <div className="role">Agent</div>
                <div className="text">{t.text}</div>
              </div>
            ))}
            {chatMessages.map((m, i) => (
              <div key={`c-${i}`} className={`transcript-msg ${m.from?.isLocal ? "user" : "agent"}`}>
                <div className="role">{m.from?.isLocal ? "You (text)" : "Agent"}</div>
                <div className="text">{m.message}</div>
              </div>
            ))}
          </>
        )}
      </div>

      <div className="text-input-wrapper">
        <input
          className="text-input"
          type="text"
          placeholder="Or type your message..."
          value={textInput}
          onChange={(e) => setTextInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSendText()}
        />
        <button className="btn-send" onClick={handleSendText} disabled={!textInput.trim()}>
          Send
        </button>
      </div>

      <div className="chat-actions">
        <button className="btn-end" onClick={() => room.disconnect()}>
          End Chat
        </button>
      </div>
    </div>
  );
}

