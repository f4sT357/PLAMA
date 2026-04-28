"use client";
import { useCallback, useEffect, useRef, useState, KeyboardEvent } from "react";
import { chatStream, fetchAvailableModels, ChatMeta, consolidateSession } from "@/lib/api";
import { useApp } from "@/lib/AppContext";

interface Message {
  id: number;
  role: "user" | "assistant";
  content: string;
  meta?: ChatMeta;
  status?: string;
  streaming?: boolean;
}

let msgId = 0;

export default function ChatPage() {
  const { sessionId, health, messages, isStreaming, sendMessage, stopStreaming, toast } = useApp();
  const [input, setInput] = useState("");
  const [overrideModel, setOverrideModel] = useState("");
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // LM Studioから動的にモデルリストを取得
  useEffect(() => {
    fetchAvailableModels()
      .then(({ models }) => setModelOptions(models.map(m => m.id)))
      .catch(() => setModelOptions([]));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 180) + "px";
  }, [input]);

  const handleSend = () => {
    if (!input.trim() || isStreaming) return;
    sendMessage(input, overrideModel || undefined);
    setInput("");
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="chat-page">
      {/* Header */}
      <div style={{ padding: "20px 32px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 16 }}>
        <div>
          <h2 style={{ margin: 0 }}>Smart Chat</h2>
          <p className="text-xs text-muted">PLAMA Intelligent Routing Active</p>
        </div>
        <div style={{ flex: 1 }} />
        
        <div className="flex items-center gap-3">
          <button
            className="btn btn-secondary btn-sm"
            onClick={async () => {
              if (!sessionId) return;
              try {
                toast("記憶を定着させています...", "info");
                await consolidateSession(sessionId);
                toast("記憶の定着が完了しました", "success");
              } catch (e) {
                toast("記憶の定着に失敗しました", "error");
              }
            }}
            disabled={messages.length === 0}
          >
            🧠 Consolidate
          </button>
          <div className="select-wrapper" style={{ width: 220 }}>
            <select
              id="model-override-select"
              className="select-native"
              value={overrideModel}
              onChange={e => setOverrideModel(e.target.value)}
            >
              <option value="">Auto Routing</option>
              {modelOptions.map(id => {
                const label = id.split("/").pop() ?? id;
                return <option key={id} value={id}>{label}</option>;
              })}
            </select>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon" style={{ fontSize: "4rem", marginBottom: 20 }}>🧠</div>
            <h1>How can I help you today?</h1>
            <p style={{ maxWidth: 400 }}>PLAMA is ready. Your memory is active and model routing is optimized for your request.</p>
          </div>
        )}

        {messages.map(msg => (
          <div key={msg.id} className={`chat-message ${msg.role}`}>
            <div className="msg-avatar">
              {msg.role === "user" ? "U" : "P"}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6, maxWidth: "100%" }}>
              <div className="msg-bubble">
                <div className="msg-text">{msg.content}</div>
                {msg.status && (
                  <div className="text-xs mt-2 animate-pulse" style={{ color: "var(--accent-purple)" }}>
                    ⚡ {msg.status}
                  </div>
                )}
              </div>
              {msg.meta && (
                <div className="flex gap-2 mt-1">
                  <span className="badge badge-purple"># {msg.meta.topic}</span>
                  <span className="badge badge-blue">@ {msg.meta.model_used}</span>
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="chat-input-area">
        <div className="chat-input-row">
          <textarea
            ref={textareaRef}
            className="textarea"
            placeholder="Ask anything..."
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isStreaming || !sessionId}
            rows={1}
            style={{ paddingRight: 60 }}
          />
          <div style={{ position: "absolute", right: 40, bottom: 42 }}>
             {isStreaming ? (
                <button className="btn btn-danger btn-sm" onClick={stopStreaming}>Stop</button>
             ) : (
                <button 
                  className="btn btn-primary btn-sm" 
                  onClick={handleSend}
                  disabled={!input.trim() || !sessionId}
                >
                  Send
                </button>
             )}
          </div>
        </div>
        {sessionId && (
          <div className="text-xs text-muted text-center mt-3">
            Active Session: <span className="text-mono">{sessionId}</span>
          </div>
        )}
      </div>
    </div>
  );
}
