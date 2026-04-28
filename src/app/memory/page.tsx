"use client";
import { useCallback, useEffect, useState } from "react";
import { fetchFacts, deleteFact, rebuildMemory, Fact } from "@/lib/api";
import { useApp } from "@/lib/AppContext";

const SOURCE_TYPES = ["", "consolidation", "ingest", "manual"];

export default function MemoryPage() {
  const { toast, refreshHealth } = useApp();
  const [facts, setFacts] = useState<Fact[]>([]);
  const [loading, setLoading] = useState(true);
  const [sourceFilter, setSourceFilter] = useState("");
  const [rebuilding, setRebuilding] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { facts } = await fetchFacts(sourceFilter || undefined);
      setFacts(facts);
    } catch {
      toast("ファクトの取得に失敗しました", "error");
    } finally {
      setLoading(false);
    }
  }, [sourceFilter, toast]);

  useEffect(() => { load(); }, [load]);

  const handleDelete = async (id: string) => {
    setDeletingId(id);
    try {
      await deleteFact(id);
      setFacts(p => p.filter(f => f.id !== id));
      toast("ファクトを削除しました", "success");
      refreshHealth();
    } catch {
      toast("削除に失敗しました", "error");
    } finally {
      setDeletingId(null);
    }
  };

  const handleRebuild = async () => {
    setRebuilding(true);
    try {
      const { indexed_facts } = await rebuildMemory();
      toast(`ChromaDB インデックス再構築完了 (${indexed_facts} facts)`, "success");
    } catch {
      toast("再構築に失敗しました", "error");
    } finally {
      setRebuilding(false);
    }
  };

  const biasCount = facts.filter(f => f.bias_flag).length;

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between" style={{ marginBottom: 20 }}>
        <div>
          <h1>🧠 ファクトビューア</h1>
          <p className="text-secondary text-sm" style={{ marginTop: 4 }}>
            {facts.length} 件のファクト
            {biasCount > 0 && (
              <span className="badge badge-red" style={{ marginLeft: 8 }}>⚠ bias: {biasCount}</span>
            )}
          </p>
        </div>
        <div className="flex gap-2">
          <div className="select-wrapper" style={{ width: 160 }}>
            <select
              id="source-filter-select"
              className="select-native"
              value={sourceFilter}
              onChange={e => setSourceFilter(e.target.value)}
            >
              {SOURCE_TYPES.map(s => (
                <option key={s} value={s}>{s || "すべてのソース"}</option>
              ))}
            </select>
            <span className="select-arrow">▾</span>
          </div>
          <button id="btn-rebuild" className="btn btn-secondary" onClick={handleRebuild} disabled={rebuilding}>
            {rebuilding ? <><span className="spinner" /> 再構築中…</> : "🔄 インデックス再構築"}
          </button>
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <div className="empty-state">
          <span className="spinner" style={{ width: 28, height: 28 }} />
          <p>読み込み中…</p>
        </div>
      ) : facts.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🗂️</div>
          <p>ファクトがありません。チャットを行うとセッション終了時にファクトが生成されます。</p>
        </div>
      ) : (
        <div className="memory-grid">
          {facts.map(fact => (
            <FactCard
              key={fact.id}
              fact={fact}
              onDelete={handleDelete}
              deleting={deletingId === fact.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function FactCard({ fact, onDelete, deleting }: {
  fact: Fact;
  onDelete: (id: string) => void;
  deleting: boolean;
}) {
  const conf = Math.round(fact.confidence * 100);
  const confColor = conf >= 80 ? "var(--accent-green)" : conf >= 50 ? "var(--accent-amber)" : "var(--accent-red)";

  return (
    <div className={`fact-card glass-card ${fact.bias_flag ? "flagged" : ""}`}>
      <div className="fact-content">{fact.content}</div>
      <div className="fact-footer">
        <span className="badge badge-blue">{fact.source_type}</span>
        <span className="badge badge-muted text-mono">{fact.model_origin}</span>
        {fact.bias_flag && <span className="badge badge-red">⚠ bias</span>}
        {fact.tags?.map(tag => (
          <span key={tag} className="badge badge-purple">{tag}</span>
        ))}
        <div style={{ flex: 1 }} />
        <div className="flex items-center gap-2">
          <div className="confidence-bar-track">
            <div
              className="confidence-bar-fill"
              style={{ width: `${conf}%`, background: confColor }}
            />
          </div>
          <span className="text-xs" style={{ color: confColor, minWidth: 32 }}>{conf}%</span>
        </div>
        <button
          id={`btn-delete-fact-${fact.id}`}
          className="btn btn-danger btn-sm btn-icon"
          onClick={() => onDelete(fact.id)}
          disabled={deleting}
          title="削除"
        >
          {deleting ? <span className="spinner" style={{ width: 12, height: 12 }} /> : "🗑"}
        </button>
      </div>
      <div className="text-xs text-muted text-mono" style={{ marginTop: 6 }}>
        {fact.id.slice(0, 16)}… · {new Date(fact.created_at).toLocaleString("ja-JP")}
      </div>
    </div>
  );
}
