"use client";
import { useState } from "react";
import { searchMemory, Fact } from "@/lib/api";
import { useApp } from "@/lib/AppContext";

export default function MemorySearchPage() {
  const { toast } = useApp();
  const [query, setQuery] = useState("");
  const [n, setN] = useState(5);
  const [results, setResults] = useState<Fact[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const { facts } = await searchMemory(query, n);
      setResults(facts);
      setSearched(true);
    } catch {
      toast("検索に失敗しました", "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6">
      <h1 style={{ marginBottom: 4 }}>🔍 セマンティック検索</h1>
      <p className="text-secondary text-sm" style={{ marginBottom: 20 }}>
        ChromaDB コサイン類似度で関連ファクトを検索します
      </p>

      <div className="panel" style={{ marginBottom: 20 }}>
        <div className="panel-body">
          <div className="flex gap-3 items-center">
            <input
              id="memory-search-input"
              className="input"
              placeholder="検索クエリを入力 (自然言語可)"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSearch()}
              style={{ flex: 1 }}
            />
            <div className="select-wrapper" style={{ width: 100 }}>
              <select
                id="n-results-select"
                className="select-native"
                value={n}
                onChange={e => setN(Number(e.target.value))}
              >
                {[3, 5, 10, 20].map(v => (
                  <option key={v} value={v}>Top {v}</option>
                ))}
              </select>
              <span className="select-arrow">▾</span>
            </div>
            <button
              id="btn-search-memory"
              className="btn btn-primary"
              onClick={handleSearch}
              disabled={loading || !query.trim()}
            >
              {loading ? <><span className="spinner" /> 検索中</> : "検索"}
            </button>
          </div>
        </div>
      </div>

      {searched && results.length === 0 && (
        <div className="empty-state">
          <div className="empty-icon">🔍</div>
          <p>該当するファクトが見つかりませんでした</p>
        </div>
      )}

      {results.length > 0 && (
        <div>
          <p className="text-secondary text-sm" style={{ marginBottom: 12 }}>
            {results.length} 件の関連ファクト
          </p>
          <div className="memory-grid">
            {results.map((fact, i) => (
              <div key={fact.id} className="fact-card glass-card">
                <div className="flex items-center gap-2" style={{ marginBottom: 8 }}>
                  <div className="badge badge-purple" style={{ minWidth: 28 }}>#{i + 1}</div>
                  <span className="badge badge-blue">{fact.source_type}</span>
                  {fact.bias_flag && <span className="badge badge-red">⚠ bias</span>}
                </div>
                <div className="fact-content">{fact.content}</div>
                <div className="fact-footer" style={{ marginTop: 10 }}>
                  <span className="text-xs text-muted text-mono">{fact.model_origin}</span>
                  <div style={{ flex: 1 }} />
                  <div className="confidence-bar-track" style={{ minWidth: 80 }}>
                    <div
                      className="confidence-bar-fill"
                      style={{ width: `${Math.round(fact.confidence * 100)}%` }}
                    />
                  </div>
                  <span className="text-xs text-muted">{Math.round(fact.confidence * 100)}%</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
