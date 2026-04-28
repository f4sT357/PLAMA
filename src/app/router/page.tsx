"use client";
import { useState } from "react";
import { routeQuery, RouteQueryResponse } from "@/lib/api";
import { useApp } from "@/lib/AppContext";

const TOPIC_COLORS: Record<string, string> = {
  geopolitics: "badge-red",
  politics: "badge-amber",
  history: "badge-amber",
  code: "badge-blue",
  technical: "badge-blue",
  japanese: "badge-purple",
  general: "badge-muted",
};

const EXAMPLES = [
  "Pythonでfastapi使ったREST APIを実装したい",
  "中国の台湾に対する軍事的姿勢について",
  "今日の天気はどう？",
  "LLMのfine-tuningとQLoRAの違いを説明して",
  "第二次世界大戦のノルマンディー上陸作戦について",
];

export default function RouterPage() {
  const { toast } = useApp();
  const [query, setQuery] = useState("");
  const [context, setContext] = useState("");
  const [result, setResult] = useState<RouteQueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<Array<{ q: string; r: RouteQueryResponse }>>([]);

  const handleRoute = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const r = await routeQuery(query, context || undefined);
      setResult(r);
      setHistory(p => [{ q: query, r }, ...p].slice(0, 10));
    } catch {
      toast("ルーティングに失敗しました", "error");
    } finally {
      setLoading(false);
    }
  };

  const confColor = result
    ? result.confidence >= 0.7 ? "var(--accent-green)"
    : result.confidence >= 0.4 ? "var(--accent-amber)"
    : "var(--accent-red)"
    : "";

  return (
    <div className="p-6">
      <h1 style={{ marginBottom: 4 }}>🔀 ルーティング確認パネル</h1>
      <p className="text-secondary text-sm" style={{ marginBottom: 20 }}>
        クエリに対してどのモデルにルーティングされるかをテストします
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
        {/* Left: Input */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div className="panel">
            <div className="panel-header">
              <h3>クエリ入力</h3>
            </div>
            <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <textarea
                id="router-query-input"
                className="textarea"
                placeholder="ルーティングをテストするクエリを入力…"
                value={query}
                onChange={e => setQuery(e.target.value)}
                rows={3}
              />
              <input
                id="router-context-input"
                className="input"
                placeholder="コンテキスト（省略可）"
                value={context}
                onChange={e => setContext(e.target.value)}
              />
              <button
                id="btn-route"
                className="btn btn-primary"
                onClick={handleRoute}
                disabled={loading || !query.trim()}
              >
                {loading ? <><span className="spinner" /> 解析中…</> : "🔀 ルーティング解析"}
              </button>
            </div>
          </div>

          {/* Examples */}
          <div className="panel">
            <div className="panel-header"><h3>サンプルクエリ</h3></div>
            <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {EXAMPLES.map(ex => (
                <button
                  key={ex}
                  className="btn btn-ghost"
                  style={{ justifyContent: "flex-start", textAlign: "left", fontSize: "0.8rem" }}
                  onClick={() => { setQuery(ex); }}
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Right: Result */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {result ? (
            <div className="route-result-card glass-card" style={{ padding: 20 }}>
              <div className="flex items-center justify-between" style={{ marginBottom: 16 }}>
                <h3>ルーティング結果</h3>
                <span className={`badge ${TOPIC_COLORS[result.topic_category] ?? "badge-muted"}`}>
                  {result.topic_category}
                </span>
              </div>

              <div style={{ display: "grid", gap: 12 }}>
                <StatRow label="選択モデル" value={
                  <span className="badge badge-blue text-mono">{result.model_name}</span>
                } />
                <StatRow label="信頼度" value={
                  <div className="flex items-center gap-2" style={{ flex: 1 }}>
                    <div className="confidence-bar-track" style={{ flex: 1 }}>
                      <div
                        className="confidence-bar-fill"
                        style={{ width: `${result.confidence * 100}%`, background: confColor }}
                      />
                    </div>
                    <span className="text-mono" style={{ color: confColor, fontSize: "0.85rem", minWidth: 40 }}>
                      {(result.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                } />
                <StatRow label="エンドポイント" value={
                  <span className="text-xs text-mono text-muted">{result.model_url}</span>
                } />
                <div>
                  <div className="text-xs text-muted" style={{ marginBottom: 4 }}>ルーティング理由</div>
                  <div className="text-sm" style={{ background: "var(--bg-base)", padding: "10px 12px", borderRadius: "var(--radius-md)", border: "1px solid var(--border)" }}>
                    {result.reason}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="empty-state panel">
              <div className="empty-icon">🔀</div>
              <p>クエリを入力してルーティングをテストしてください</p>
            </div>
          )}

          {/* History */}
          {history.length > 0 && (
            <div className="panel">
              <div className="panel-header"><h3>履歴</h3></div>
              <div style={{ maxHeight: 280, overflowY: "auto" }}>
                {history.map((h, i) => (
                  <div
                    key={i}
                    style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)", cursor: "pointer" }}
                    onClick={() => { setQuery(h.q); setResult(h.r); }}
                  >
                    <div className="text-sm truncate" style={{ marginBottom: 4 }}>{h.q}</div>
                    <div className="flex gap-2">
                      <span className={`badge ${TOPIC_COLORS[h.r.topic_category] ?? "badge-muted"}`} style={{ fontSize: "0.65rem" }}>
                        {h.r.topic_category}
                      </span>
                      <span className="badge badge-blue" style={{ fontSize: "0.65rem" }}>{h.r.model_name}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
      <div className="text-xs text-muted" style={{ minWidth: 110 }}>{label}</div>
      <div style={{ flex: 1 }}>{value}</div>
    </div>
  );
}
