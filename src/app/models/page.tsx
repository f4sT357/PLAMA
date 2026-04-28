"use client";
import { useCallback, useEffect, useState } from "react";
import {
  fetchAvailableModels, fetchTrust, loadModel, unloadModel,
  fetchConfig, updateConfig,
  LMStudioModel, TrustEntry, PlamaConfig,
} from "@/lib/api";
import { useApp } from "@/lib/AppContext";

export default function ModelsPage() {
  const { toast, health, refreshHealth, models, trust, config, loadModels, loadTrust, loadConfig } = useApp();
  const [loadingModels, setLoadingModels] = useState(false);
  const [loadingTrust, setLoadingTrust] = useState(false);
  const [reachable, setReachable] = useState(true);
  const [actionModel, setActionModel] = useState<string | null>(null);
  const [savingConfig, setSavingConfig] = useState(false);
  const [hasInitializedConfig, setHasInitializedConfig] = useState(false);
  const [editedConfig, setEditedConfig] = useState<{
    main_model: string;
    sub_model: string;
    bias_model: string;
    consolidation_model: string;
  }>({ main_model: "", sub_model: "", bias_model: "", consolidation_model: "" });

  // Sync local editor state when global config is updated (Initial sync only)
  useEffect(() => {
    if (config && !hasInitializedConfig) {
      setEditedConfig({
        main_model: config.main_model || "",
        sub_model: config.sub_model || "",
        bias_model: config.bias_model || "",
        consolidation_model: config.consolidation_model || "",
      });
      setHasInitializedConfig(true);
    }
  }, [config, hasInitializedConfig]);

  /* ─── Load / Unload actions ───────────────────────────────────────── */
  const handleLoad = async (id: string) => {
    setActionModel(id);
    try {
      await loadModel(id);
      toast(`${id} のロードリクエストを送信しました`, "success");
      // 少し待ってから状態更新（LM Studioがロードするまでのラグ）
      setTimeout(async () => { await loadModels(); refreshHealth(); }, 1500);
    } catch {
      toast("ロードに失敗しました", "error");
    } finally {
      setActionModel(null);
    }
  };

  const handleUnload = async (id: string) => {
    setActionModel(id);
    try {
      await unloadModel(id);
      toast(`${id} のアンロードリクエストを送信しました`, "info");
      setTimeout(async () => { await loadModels(); refreshHealth(); }, 1500);
    } catch {
      toast("アンロードに失敗しました", "error");
    } finally {
      setActionModel(null);
    }
  };

  const handleRefresh = () => { loadModels(); loadTrust(); loadConfig(); refreshHealth(); };

  const handleSaveConfig = async () => {
    if (!hasInitializedConfig) {
      toast("設定を読み込み中です。しばらくお待ちください", "info");
      return;
    }
    
    // 全て空の場合は、初期ロード失敗の可能性が高いため保存を阻止
    if (!editedConfig.main_model && !editedConfig.consolidation_model) {
      toast("設定値が空です。モデルを選択してください", "warning");
      return;
    }

    setSavingConfig(true);
    try {
      await updateConfig(editedConfig);
      toast("設定を保存しました", "success");
      // AppContext側の状態を最新にする
      await loadConfig();
    } catch {
      toast("設定の保存に失敗しました", "error");
    } finally {
      setSavingConfig(false);
    }
  };

  /* ─── Derived ─────────────────────────────────────────────────────── */
  const activeIds = health?.active_models ?? [];
  // Merge: health active list が最も信頼性が高い（LM Studio /v1/models）
  const mergedModels = models.map(m => ({
    ...m,
    loaded: activeIds.includes(m.id) || m.loaded,
  }));
  const loadedModels = mergedModels.filter(m => m.loaded);
  const unloadedModels = mergedModels.filter(m => !m.loaded);

  /* ─── Trust score helpers ─────────────────────────────────────────── */
  const scoreClass = (score: number) =>
    score >= 0.8 ? "score-high" : score >= 0.5 ? "score-mid" : "score-low";

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between" style={{ marginBottom: 24 }}>
        <div>
          <h1>🤖 モデル & Trust スコア</h1>
          <p className="text-secondary text-sm" style={{ marginTop: 4 }}>
            LM Studioのインストール済みモデルをリアルタイムで取得・管理します
          </p>
        </div>
        <button id="btn-refresh-all" className="btn btn-secondary" onClick={handleRefresh}>
          ↻ 一覧を更新
        </button>
      </div>

      {/* LM Studio status banner */}
      {!loadingModels && !reachable && (
        <div style={{
          padding: "12px 16px",
          borderRadius: "var(--radius-md)",
          background: "var(--accent-amber-dim)",
          border: "1px solid rgba(246,173,85,0.25)",
          marginBottom: 20,
          fontSize: "0.85rem",
          color: "var(--accent-amber)",
        }}>
          ⚠ LM Studio に接続できません。localhost:1234 でサーバーが起動しているか確認してください。
        </div>
      )}

      {/* Model Role Settings (v2.0 NEW) */}
      <div className="panel" style={{ 
        marginBottom: 28, 
        border: "1px solid rgba(139,92,246,0.3)",
        position: "relative",
        overflow: "hidden"
      }}>
        {/* Loading Overlay */}
        {!hasInitializedConfig && (
          <div style={{
            position: "absolute",
            inset: 0,
            background: "rgba(10,10,15,0.7)",
            backdropFilter: "blur(4px)",
            zIndex: 10,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 12
          }}>
            <span className="spinner" style={{ width: 32, height: 32 }} />
            <p className="text-sm font-medium">設定を読み込み中…</p>
          </div>
        )}

        <div className="panel-header" style={{ background: "rgba(139,92,246,0.05)" }}>
          <div className="flex items-center gap-2">
            <span style={{ fontSize: "1.1rem" }}>⚙️</span>
            <h3>モデル役割設定</h3>
          </div>
        </div>
        <div className="panel-body">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 20 }}>
            {/* Main Model */}
            <div>
              <label className="text-xs font-semibold text-muted" style={{ display: "block", marginBottom: 6 }}>
                メインモデル (General / Daily)
              </label>
              <select
                className="select-styled"
                value={editedConfig.main_model}
                onChange={(e) => setEditedConfig({ ...editedConfig, main_model: e.target.value })}
              >
                <option value="">未設定 (自動選択)</option>
                {models.map(m => (
                  <option key={m.id} value={m.id}>{m.id.split("/").pop()}</option>
                ))}
              </select>
            </div>

            {/* Sub Model */}
            <div>
              <label className="text-xs font-semibold text-muted" style={{ display: "block", marginBottom: 6 }}>
                サブモデル (Technical / Code)
              </label>
              <select
                className="select-styled"
                value={editedConfig.sub_model}
                onChange={(e) => setEditedConfig({ ...editedConfig, sub_model: e.target.value })}
              >
                <option value="">未設定 (自動選択)</option>
                {models.map(m => (
                  <option key={m.id} value={m.id}>{m.id.split("/").pop()}</option>
                ))}
              </select>
            </div>

            {/* Bias Model */}
            <div>
              <label className="text-xs font-semibold text-muted" style={{ display: "block", marginBottom: 6 }}>
                バイアス検知モデル (LFM / Analyzing)
              </label>
              <select
                className="select-styled"
                value={editedConfig.bias_model}
                onChange={(e) => setEditedConfig({ ...editedConfig, bias_model: e.target.value })}
              >
                <option value="">未設定 (ルールベースのみ)</option>
                {models.map(m => (
                  <option key={m.id} value={m.id}>{m.id.split("/").pop()}</option>
                ))}
              </select>
            </div>

            {/* Consolidation Model (Memory Keeper) */}
            <div>
              <label className="text-xs font-semibold text-muted" style={{ display: "block", marginBottom: 6 }}>
                記憶集約モデル (Memory Keeper / Consolidation)
              </label>
              <select
                className="select-styled"
                value={editedConfig.consolidation_model}
                onChange={(e) => setEditedConfig({ ...editedConfig, consolidation_model: e.target.value })}
              >
                <option value="">未設定 (Qwen3.5-9b)</option>
                {models.map(m => (
                  <option key={m.id} value={m.id}>{m.id.split("/").pop()}</option>
                ))}
              </select>
            </div>
          </div>

          <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--border-subtle)", display: "flex", justifyContent: "flex-end" }}>
            <button
              className="btn btn-primary"
              onClick={handleSaveConfig}
              disabled={savingConfig || !hasInitializedConfig}
            >
              {savingConfig ? <span className="spinner" /> : "設定を保存"}
            </button>
          </div>
        </div>
      </div>

      {/* Currently loaded models */}
      <div className="panel" style={{ marginBottom: 20 }}>
        <div className="panel-header">
          <div className="flex items-center gap-2">
            <h3>ロード済みモデル</h3>
            {loadedModels.length > 0 && (
              <span className="badge badge-green">{loadedModels.length}</span>
            )}
          </div>
        </div>
        <div className="panel-body">
          {loadingModels ? (
            <div className="flex items-center gap-2 text-muted text-sm">
              <span className="spinner" style={{ width: 14, height: 14 }} />
              取得中…
            </div>
          ) : loadedModels.length === 0 ? (
            <p className="text-muted text-sm">現在ロードされているモデルはありません</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {loadedModels.map(m => (
                <ModelRow
                  key={m.id}
                  model={m}
                  isLoaded
                  isActing={actionModel === m.id}
                  onLoad={handleLoad}
                  onUnload={handleUnload}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Unloaded / all available models */}
      {!loadingModels && unloadedModels.length > 0 && (
        <div className="panel" style={{ marginBottom: 28 }}>
          <div className="panel-header">
            <div className="flex items-center gap-2">
              <h3>インストール済み（未ロード）</h3>
              <span className="badge badge-muted">{unloadedModels.length}</span>
            </div>
          </div>
          <div className="panel-body">
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {unloadedModels.map(m => (
                <ModelRow
                  key={m.id}
                  model={m}
                  isLoaded={false}
                  isActing={actionModel === m.id}
                  onLoad={handleLoad}
                  onUnload={handleUnload}
                />
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Empty: LM Studio reachable but no models */}
      {!loadingModels && reachable && models.length === 0 && (
        <div className="empty-state panel" style={{ marginBottom: 28 }}>
          <div className="empty-icon">📦</div>
          <p>LM Studioにインストール済みのモデルが見つかりません</p>
        </div>
      )}

      {/* Trust Registry */}
      <h2 style={{ marginBottom: 12 }}>Trust Registry</h2>
      {loadingTrust ? (
        <div className="empty-state">
          <span className="spinner" />
          <p>読み込み中…</p>
        </div>
      ) : Object.keys(trust).length === 0 ? (
        <div className="empty-state panel">
          <div className="empty-icon">📊</div>
          <p>まだスコアデータがありません。チャットを行うとスコアが蓄積されます。</p>
        </div>
      ) : (
        <div className="trust-list">
          {Object.entries(trust).map(([name, entry]) => {
            const score = typeof entry.trust_score === "number" ? entry.trust_score : 1.0;
            const biasRate = entry.total_outputs > 0
              ? ((entry.bias_flags / entry.total_outputs) * 100).toFixed(1)
              : "0.0";
            const isActive = activeIds.includes(name);
            return (
              <div key={name} className="trust-row">
                <div className={`trust-score-ring ${scoreClass(score)}`}>
                  {(score * 100).toFixed(0)}
                </div>
                <div style={{ flex: 1 }}>
                  <div className="flex items-center gap-2">
                    <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>{name}</span>
                    {isActive && <span className="badge badge-green">ロード済み</span>}
                  </div>
                  <div className="text-xs text-secondary" style={{ marginTop: 2 }}>
                    Total: {entry.total_outputs} outputs · Bias flags: {entry.bias_flags} ({biasRate}%)
                  </div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{
                    fontSize: "1.3rem",
                    fontWeight: 700,
                    color: score >= 0.8 ? "var(--accent-green)"
                      : score >= 0.5 ? "var(--accent-amber)"
                      : "var(--accent-red)",
                  }}>
                    {score.toFixed(3)}
                  </div>
                  <div className="text-xs text-muted">trust score</div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ─── ModelRow component ──────────────────────────────────────────────── */
function ModelRow({
  model, isLoaded, isActing, onLoad, onUnload,
}: {
  model: LMStudioModel;
  isLoaded: boolean;
  isActing: boolean;
  onLoad: (id: string) => void;
  onUnload: (id: string) => void;
}) {
  // モデルIDからわかりやすい表示名を作る
  const displayName = model.id.split("/").pop() ?? model.id;
  const fullPath = model.id;

  return (
    <div
      className="glass-card"
      style={{
        padding: "12px 16px",
        display: "flex",
        alignItems: "center",
        gap: 14,
        borderColor: isLoaded ? "rgba(104,211,145,0.2)" : undefined,
      }}
    >
      {/* Status indicator */}
      <div style={{
        width: 8,
        height: 8,
        borderRadius: "50%",
        background: isLoaded ? "var(--accent-green)" : "var(--text-muted)",
        boxShadow: isLoaded ? "0 0 8px var(--accent-green)" : undefined,
        flexShrink: 0,
      }} />

      {/* Model info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="text-mono" style={{ fontWeight: 600, fontSize: "0.875rem" }}>
          {displayName}
        </div>
        {fullPath !== displayName && (
          <div className="text-xs text-muted truncate" title={fullPath}>
            {fullPath}
          </div>
        )}
      </div>

      {/* Source badge */}
      <span className={`badge ${model.source === "v0" ? "badge-muted" : "badge-blue"}`}>
        {model.source === "v0" ? "installed" : "v1/models"}
      </span>

      {/* Actions */}
      <div className="flex gap-2">
        {!isLoaded && (
          <button
            id={`btn-load-${model.id.replace(/[^a-zA-Z0-9]/g, "-")}`}
            className="btn btn-primary btn-sm"
            onClick={() => onLoad(model.id)}
            disabled={isActing}
          >
            {isActing
              ? <><span className="spinner" style={{ width: 12, height: 12 }} /> ロード中</>
              : "↑ ロード"}
          </button>
        )}
        {isLoaded && (
          <button
            id={`btn-unload-${model.id.replace(/[^a-zA-Z0-9]/g, "-")}`}
            className="btn btn-ghost btn-sm"
            onClick={() => onUnload(model.id)}
            disabled={isActing}
          >
            {isActing
              ? <><span className="spinner" style={{ width: 12, height: 12 }} /> 処理中</>
              : "↓ アンロード"}
          </button>
        )}
      </div>
    </div>
  );
}
