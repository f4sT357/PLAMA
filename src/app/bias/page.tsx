"use client";
import { useCallback, useEffect, useState } from "react";
import { checkBias, fetchBiasFlags, BiasCheckResponse, Fact } from "@/lib/api";
import { useApp } from "@/lib/AppContext";

export default function BiasPage() {
  const { toast } = useApp();
  const [text, setText] = useState("");
  const [modelOrigin, setModelOrigin] = useState("");
  const [result, setResult] = useState<BiasCheckResponse | null>(null);
  const [checking, setChecking] = useState(false);
  const [flaggedFacts, setFlaggedFacts] = useState<Fact[]>([]);
  const [loadingFlags, setLoadingFlags] = useState(true);

  const loadFlags = useCallback(async () => {
    setLoadingFlags(true);
    try {
      const { flags } = await fetchBiasFlags(undefined, 50);
      setFlaggedFacts(flags);
    } catch {
      // ok
    } finally {
      setLoadingFlags(false);
    }
  }, []);

  useEffect(() => { loadFlags(); }, [loadFlags]);

  const handleCheck = async () => {
    if (!text.trim()) return;
    setChecking(true);
    try {
      const r = await checkBias(text, modelOrigin || undefined);
      setResult(r);
    } catch {
      toast("バイアスチェックに失敗しました", "error");
    } finally {
      setChecking(false);
    }
  };

  const scoreColor = result
    ? result.bias_score >= 0.7 ? "var(--accent-red)"
    : result.bias_score >= 0.3 ? "var(--accent-amber)"
    : "var(--accent-green)"
    : "";

  const scoreLabel = result
    ? result.bias_score >= 0.7 ? "高リスク"
    : result.bias_score >= 0.3 ? "中程度"
    : "低リスク"
    : "";

  return (
    <div className="p-6">
      <h1 style={{ marginBottom: 4 }}>⚖️ バイアスチェック</h1>
      <p className="text-secondary text-sm" style={{ marginBottom: 24 }}>
        v1.4: ルールベース（CJKトークン + キーワード）｜ v2.0: LFM呼び出し予定
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 28 }}>
        {/* Input */}
        <div className="panel">
          <div className="panel-header"><h3>テキスト入力</h3></div>
          <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <textarea
              id="bias-text-input"
              className="textarea"
              placeholder="バイアスチェックしたいテキストを入力…"
              value={text}
              onChange={e => setText(e.target.value)}
              rows={6}
            />
            <input
              id="bias-model-input"
              className="input"
              placeholder="モデル名（省略可）"
              value={modelOrigin}
              onChange={e => setModelOrigin(e.target.value)}
            />
            <button
              id="btn-check-bias"
              className="btn btn-primary"
              onClick={handleCheck}
              disabled={checking || !text.trim()}
            >
              {checking ? <><span className="spinner" /> チェック中…</> : "⚖️ バイアス検出"}
            </button>
          </div>
        </div>

        {/* Result */}
        <div className="panel">
          <div className="panel-header"><h3>チェック結果</h3></div>
          <div className="panel-body">
            {!result ? (
              <div className="empty-state" style={{ padding: "24px 0" }}>
                <div className="empty-icon">⚖️</div>
                <p>テキストを入力してチェックを実行してください</p>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                {/* Score */}
                <div style={{ textAlign: "center", padding: "16px 0" }}>
                  <div style={{
                    fontSize: "3rem",
                    fontWeight: 800,
                    color: scoreColor,
                    lineHeight: 1,
                  }}>
                    {result.bias_score.toFixed(3)}
                  </div>
                  <div className="text-sm" style={{ color: scoreColor, marginTop: 6, fontWeight: 600 }}>
                    {scoreLabel}
                  </div>
                  <div className="confidence-bar-track" style={{ margin: "10px auto", maxWidth: 200 }}>
                    <div
                      className="confidence-bar-fill"
                      style={{ width: `${result.bias_score * 100}%`, background: scoreColor }}
                    />
                  </div>
                </div>

                {/* Flags */}
                {result.flags.length > 0 && (
                  <div>
                    <div className="text-xs text-muted" style={{ marginBottom: 6 }}>検出フラグ</div>
                    <div className="flex gap-2" style={{ flexWrap: "wrap" }}>
                      {result.flags.map(f => (
                        <span key={f} className="badge badge-red">{f}</span>
                      ))}
                    </div>
                  </div>
                )}

                {result.detail && (
                  <div>
                    <div className="text-xs text-muted" style={{ marginBottom: 4 }}>詳細</div>
                    <div className="text-sm" style={{
                      background: "var(--bg-base)",
                      padding: "10px 12px",
                      borderRadius: "var(--radius-md)",
                      border: "1px solid var(--border)",
                      lineHeight: 1.6,
                    }}>
                      {result.detail}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Flagged facts from memory */}
      <h2 style={{ marginBottom: 12 }}>バイアスフラグ済みファクト</h2>
      {loadingFlags ? (
        <div className="empty-state">
          <span className="spinner" /> <p>読み込み中…</p>
        </div>
      ) : flaggedFacts.length === 0 ? (
        <div className="empty-state panel">
          <div className="empty-icon">✅</div>
          <p>フラグ済みファクトはありません</p>
        </div>
      ) : (
        <div className="memory-grid">
          {flaggedFacts.map(fact => (
            <div key={fact.id} className="fact-card flagged">
              <div className="flex items-center gap-2" style={{ marginBottom: 8 }}>
                <span className="badge badge-red">⚠ bias</span>
                <span className="badge badge-muted">{fact.source_type}</span>
                <span className="badge badge-muted text-mono">{fact.model_origin}</span>
              </div>
              <div className="fact-content">{fact.content}</div>
              <div className="text-xs text-muted text-mono" style={{ marginTop: 8 }}>
                {new Date(fact.created_at).toLocaleString("ja-JP")}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
