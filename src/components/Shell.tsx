"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useApp } from "@/lib/AppContext";

const NAV = [
  { section: "Main" },
  { href: "/", label: "Dashboard", icon: "📊" },
  { href: "/chat", label: "Smart Chat", icon: "💬" },
  { section: "Memory" },
  { href: "/memory", label: "Fact Viewer", icon: "🧠" },
  { href: "/memory/search", label: "Search", icon: "🔍" },
  { section: "Models" },
  { href: "/models", label: "Trust & Models", icon: "🤖" },
  { href: "/router", label: "Model Router", icon: "🔀" },
  { section: "Analysis" },
  { href: "/bias", label: "Bias Checker", icon: "⚖️" },
  { href: "/pipeline", label: "Data Pipeline", icon: "🔧" },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { health, sessionId, startNewSession } = useApp();

  const isOnline = health?.lm_studio_connected === true;

  return (
    <div className="layout-shell">
      {/* Topbar */}
      <header className="topbar">
        <div className="topbar-logo">
          <div className="logo-icon">P</div>
          <span>PLAMA</span>
        </div>
        
        <div className="topbar-spacer" />

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 bg-glass px-3 py-1.5 rounded-md border border-subtle">
            <div className={`status-dot ${isOnline ? "online" : ""}`} />
            <span className="text-xs font-semibold text-secondary">
              {isOnline ? "LM Studio Active" : "Disconnected"}
            </span>
          </div>

          <button
            className="btn btn-primary btn-sm"
            onClick={startNewSession}
            id="btn-new-session"
          >
            + New Session
          </button>
        </div>
      </header>

      {/* Sidebar */}
      <nav className="sidebar">
        {NAV.map((item, i) =>
          "section" in item ? (
            <div className="nav-section" key={i}>{item.section}</div>
          ) : (
            <Link
              key={item.href}
              href={item.href!}
              className={`nav-item ${pathname === item.href ? "active" : ""}`}
            >
              <span className="nav-icon">{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          )
        )}
      </nav>

      {/* Main Content */}
      <main className="main-content">
        {children}
      </main>
    </div>
  );
}
