"use client";
import { useCallback, useEffect, useState } from "react";
import { fetchCorpusStats, rebuildCorpus, CorpusStats } from "@/lib/api";
import { useApp } from "@/lib/AppContext";

export default function PipelinePage() {
  const { toast } = useApp();
  const [stats, setStats] = useState<CorpusStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [rebuilding, setRebuilding] = useState(false);

  const loadStats = useCallback(async () => {
    setLoading(true);
    try {
      const s = await fetchCorpusStats();
      setStats(s);
    } catch {
      // ok
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadStats(); }, [loadStats]);

  const handleRebuild = async () => {
    setRebuilding(true);
    try {
      await rebuildCorpus();
      toast("コーパスインデックスを再構築しました", "success");
      await loadStats();
    } catch {
      toast("再構築に失敗しました", "error");
    } finally {
      setRebuilding(false);
    }
  };

  return (
    <div className="p-6">
      <h1 style={{ marginBottom: 4 }}>🔧 パイプライン</h1>
      <p className="text-secondary text-sm" style={{ marginBottom: 24 }}>
        n8n インジェスト受け口 & コーパス管理
      </p>

      {/* Stats */}
      <div className="stats-grid" style={{ marginBottom: 24 }}>
        <div className="stat-card">
          <div className="stat-value" style={{ color: "var(--accent-blue)" }}>
            {loading ? "—" : (stats?.total_documents ?? 0)}
          </div>
          <div className="stat-label">総ドキュメント数</div>
          <div className="stat-sub">ChromaDB corpus</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: "var(--accent-purple)" }}>
            {loading ? "—" : (stats?.sources?.length ?? 0)}
          </div>
          <div className="stat-label">ソース数</div>
          <div className="stat-sub">ユニークソース</div>
        </div>
        <div className="stat-card" style={{ gridColumn: "span 2" }}>
          <div className="stat-label">最終インデックス再構築</div>
          <div className="stat-value" style={{ fontSize: "1.1rem", marginTop: 4 }}>
            {loading ? "—" : stats?.last_rebuilt
              ? new Date(stats.last_rebuilt).toLocaleString("ja-JP")
              : "未実行"}
          </div>
        </div>
      </div>

      {/* Sources */}
      {stats?.sources && stats.sources.length > 0 && (
        <div className="panel" style={{ marginBottom: 20 }}>
          <div className="panel-header"><h3>インジェスト済みソース</h3></div>
          <div className="panel-body">
            <div className="flex gap-2" style={{ flexWrap: "wrap" }}>
              {stats.sources.map(s => (
                <span key={s} className="badge badge-blue">{s}</span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="panel">
        <div className="panel-header"><h3>操作</h3></div>
        <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="glass-card" style={{ padding: "16px 18px" }}>
            <div className="flex items-center justify-between">
              <div>
                <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>コーパスインデックス再構築</div>
                <div className="text-xs text-secondary" style={{ marginTop: 4 }}>
                  ChromaDB の全インジェストドキュメントを再インデックス化します
                </div>
              </div>
              <button
                id="btn-rebuild-corpus"
                className="btn btn-secondary"
                onClick={handleRebuild}
                disabled={rebuilding}
              >
                {rebuilding ? <><span className="spinner" /> 再構築中…</> : "🔄 再構築"}
              </button>
            </div>
          </div>

          <div className="glass-card" style={{ padding: "16px 18px", opacity: 0.6 }}>
            <div className="flex items-center justify-between">
              <div>
                <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>n8n Webhook エンドポイント</div>
                <div className="text-xs text-secondary" style={{ marginTop: 4 }}>
                  <span className="text-mono">POST http://localhost:8000/api/pipeline/n8n-ingest</span>
                </div>
                <div className="text-xs text-muted" style={{ marginTop: 2 }}>
                  v1.4 スタブ実装 / v2.0 で robots.txt チェック + クロール間隔設定追加予定
                </div>
              </div>
              <span className="badge badge-amber">v1.4 stub</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
