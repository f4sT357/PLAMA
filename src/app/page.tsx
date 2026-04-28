"use client";
import Link from "next/link";
import { useApp } from "@/lib/AppContext";

export default function Dashboard() {
  const { health, sessionId } = useApp();

  const stats = health?.memory_stats;
  const isOnline = health?.lm_studio_connected;

  return (
    <div className="p-8" style={{ maxWidth: 1200, margin: "0 auto" }}>
      <header style={{ marginBottom: 40 }}>
        <h1>PLAMA 2.0 Dashboard</h1>
        <p>Persistent Local AI Memory Adapter — System Overview</p>
      </header>

      {/* Main Stats Grid */}
      <div className="stats-grid" style={{ marginBottom: 40 }}>
        <div className="stat-card">
          <span className="stat-label">Memory Facts</span>
          <span className="stat-value">{stats?.total_facts ?? 0}</span>
          <span className="text-xs text-muted">Stored in ChromaDB</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Active Session</span>
          <span className="text-xs text-mono truncate" style={{ fontSize: "0.8rem", margin: "10px 0" }}>
            {sessionId ?? "No active session"}
          </span>
          <span className="text-xs text-muted">{stats?.total_sessions ?? 0} total sessions</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">LM Studio</span>
          <span className={`stat-value ${isOnline ? "text-green" : "text-red"}`} style={{ color: isOnline ? "var(--accent-green)" : "var(--accent-red)" }}>
            {isOnline ? "Connected" : "Offline"}
          </span>
          <span className="text-xs text-muted">API localhost:1234</span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Active Models</span>
          <span className="stat-value">{health?.active_models.length ?? 0}</span>
          <span className="text-xs text-muted">In-flight routing active</span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 32 }}>
        {/* Quick Actions */}
        <section>
          <h2 style={{ marginBottom: 20 }}>Quick Actions</h2>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <ActionCard 
              title="Smart Chat" 
              desc="Start a context-aware conversation with automatic model routing."
              href="/chat"
              icon="💬"
              color="var(--accent-purple)"
            />
            <ActionCard 
              title="Memory Search" 
              desc="Search through your long-term memory using vector similarity."
              href="/memory/search"
              icon="🔍"
              color="var(--accent-blue)"
            />
            <ActionCard 
              title="Model Trust" 
              desc="Evaluate and manage the reliability of your local LLM models."
              href="/models"
              icon="🤖"
              color="var(--accent-green)"
            />
            <ActionCard 
              title="Bias Check" 
              desc="Analyze text for biases and safety flags using rule-based LFM."
              href="/bias"
              icon="⚖️"
              color="var(--accent-amber)"
            />
          </div>
        </section>

        {/* System Health */}
        <section>
          <h2 style={{ marginBottom: 20 }}>System Status</h2>
          <div className="panel" style={{ padding: 24 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <StatusRow label="Backend API" status="OK" />
              <StatusRow label="ChromaDB" status={stats ? "Connected" : "Pending"} />
              <StatusRow label="LM Studio (v0)" status={isOnline ? "Available" : "Missing"} />
              <div className="divider" />
              <div className="text-xs text-muted">
                PLAMA Version: v2.0.0-alpha<br />
                Schema Version: {stats?.schema_version ?? "unknown"}
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function ActionCard({ title, desc, href, icon, color }: { title: string, desc: string, href: string, icon: string, color: string }) {
  return (
    <Link href={href} style={{ textDecoration: "none" }}>
      <div className="glass-card" style={{ padding: 24, height: "100%", display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ fontSize: "1.5rem", marginBottom: 8 }}>{icon}</div>
        <h3 style={{ color }}>{title}</h3>
        <p className="text-xs">{desc}</p>
      </div>
    </Link>
  );
}

function StatusRow({ label, status }: { label: string, status: string }) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-sm font-semibold">{label}</span>
      <span className={`badge ${status === "OK" || status === "Connected" || status === "Available" ? "badge-green" : "badge-amber"}`}>
        {status}
      </span>
    </div>
  );
}
