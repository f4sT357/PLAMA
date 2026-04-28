/**
 * PLAMA v2.0 API Client
 * Wraps all 18 backend endpoints with full TypeScript types.
 */

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string;
  lm_studio_connected: boolean;
  active_models: string[];
  memory_stats: {
    total_facts: number;
    total_sessions: number;
    short_term_messages: number;
    schema_version: string;
  };
}

export interface NewSessionResponse {
  session_id: string;
  created_at: string;
}

export interface ChatRequest {
  session_id: string;
  message: string;
  override_model?: string;
}

export interface ChatMeta {
  model_used: string;
  topic: string;
  session_id: string;
}

export interface Fact {
  id: string;
  content: string;
  source_type: string;
  confidence: number;
  bias_flag: boolean;
  model_origin: string;
  created_at: string;
  tags: string[];
}

export interface FactList {
  facts: Fact[];
  count: number;
}

export interface RouteQueryResponse {
  model_name: string;
  model_url: string;
  topic_category: string;
  confidence: number;
  reason: string;
}

export interface TrustEntry {
  model_name: string;
  total_outputs: number;
  bias_flags: number;
  trust_score: number;
  last_updated: string;
}

export interface LMStudioModel {
  id: string;
  loaded: boolean;
  source: "v0" | "v1";  // v0 = all installed, v1 = loaded only
}

export interface AvailableModelsResponse {
  models: LMStudioModel[];
  count: number;
  lm_studio_reachable: boolean;
}

export interface BiasCheckResponse {
  bias_score: number;
  flags: string[];
  detail: string;
}

export interface PlamaConfig {
  main_model: string;
  sub_model: string;
  bias_model: string;
  last_updated: string;
}

export interface UpdateConfigRequest {
  main_model?: string;
  sub_model?: string;
  bias_model?: string;
}

export interface CorpusStats {
  total_documents: number;
  sources: string[];
  last_rebuilt: string | null;
}

// ─── Core endpoints ───────────────────────────────────────────────────────────

export async function fetchHealth(): Promise<HealthResponse> {
  const r = await fetch(`${API_BASE}/api/health`);
  if (!r.ok) throw new Error("Health check failed");
  return r.json();
}

export async function newSession(): Promise<NewSessionResponse> {
  const r = await fetch(`${API_BASE}/api/session/new`, { method: "POST" });
  if (!r.ok) throw new Error("Failed to create session");
  return r.json();
}

/** SSE streaming chat. Yields delta strings; last event includes meta. */
export async function* chatStream(
  req: ChatRequest,
  signal?: AbortSignal
): AsyncGenerator<{ delta?: string; done?: boolean; meta?: ChatMeta; error?: string; status?: string }> {
  const r = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal,
  });
  if (!r.ok || !r.body) throw new Error("Chat stream failed");

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() ?? "";
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          yield JSON.parse(line.slice(6));
        } catch {
          // skip malformed
        }
      }
    }
  }
}

export async function consolidateSession(sessionId: string): Promise<unknown> {
  const r = await fetch(`${API_BASE}/api/session/${sessionId}/consolidate`, { method: "POST" });
  if (!r.ok) throw new Error("Consolidation failed");
  return r.json();
}

// ─── Memory endpoints ─────────────────────────────────────────────────────────

export async function fetchMemory(): Promise<unknown> {
  const r = await fetch(`${API_BASE}/api/memory`);
  if (!r.ok) throw new Error("Failed to fetch memory");
  return r.json();
}

export async function fetchFacts(sourceType?: string): Promise<FactList> {
  const url = new URL(`${API_BASE}/api/memory/facts`);
  if (sourceType) url.searchParams.set("source_type", sourceType);
  const r = await fetch(url.toString());
  if (!r.ok) throw new Error("Failed to fetch facts");
  return r.json();
}

export async function deleteFact(factId: string): Promise<{ deleted: string }> {
  const r = await fetch(`${API_BASE}/api/memory/facts/${factId}`, { method: "DELETE" });
  if (!r.ok) throw new Error("Failed to delete fact");
  return r.json();
}

export async function searchMemory(query: string, n_results = 5): Promise<FactList> {
  const r = await fetch(`${API_BASE}/api/memory/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, n_results }),
  });
  if (!r.ok) throw new Error("Memory search failed");
  return r.json();
}

export async function rebuildMemory(): Promise<{ status: string; indexed_facts: number }> {
  const r = await fetch(`${API_BASE}/api/memory/rebuild`, { method: "POST" });
  if (!r.ok) throw new Error("Rebuild failed");
  return r.json();
}

// ─── Model endpoints ──────────────────────────────────────────────────────────

export async function fetchAvailableModels(): Promise<AvailableModelsResponse> {
  const r = await fetch(`${API_BASE}/api/models/available`);
  if (!r.ok) throw new Error("Failed to fetch available models");
  return r.json();
}

export async function fetchTrust(): Promise<{ trust_registry: Record<string, TrustEntry> }> {
  const r = await fetch(`${API_BASE}/api/models/trust`);
  if (!r.ok) throw new Error("Failed to fetch trust registry");
  return r.json();
}

export async function routeQuery(query: string, context?: string): Promise<RouteQueryResponse> {
  const r = await fetch(`${API_BASE}/api/models/route`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, context }),
  });
  if (!r.ok) throw new Error("Route query failed");
  return r.json();
}

export async function loadModel(model_name: string, keep_alive = -1): Promise<unknown> {
  const r = await fetch(`${API_BASE}/api/models/load`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model_name, keep_alive }),
  });
  if (!r.ok) throw new Error("Load model failed");
  return r.json();
}

export async function unloadModel(model_name: string): Promise<unknown> {
  const r = await fetch(`${API_BASE}/api/models/unload`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model_name }),
  });
  if (!r.ok) throw new Error("Unload model failed");
  return r.json();
}

// ─── Bias endpoints ───────────────────────────────────────────────────────────

export async function fetchBiasFlags(model?: string, limit = 50): Promise<{ flags: Fact[]; count: number }> {
  const url = new URL(`${API_BASE}/api/bias/flags`);
  if (model) url.searchParams.set("model", model);
  url.searchParams.set("limit", String(limit));
  const r = await fetch(url.toString());
  if (!r.ok) throw new Error("Failed to fetch bias flags");
  return r.json();
}

export async function checkBias(text: string, model_origin?: string): Promise<BiasCheckResponse> {
  const r = await fetch(`${API_BASE}/api/bias/check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, model_origin }),
  });
  if (!r.ok) throw new Error("Bias check failed");
  return r.json();
}

// ─── Pipeline endpoints ───────────────────────────────────────────────────────

export async function fetchCorpusStats(): Promise<CorpusStats> {
  const r = await fetch(`${API_BASE}/api/pipeline/corpus/stats`);
  if (!r.ok) throw new Error("Failed to fetch corpus stats");
  return r.json();
}

export async function rebuildCorpus(): Promise<unknown> {
  const r = await fetch(`${API_BASE}/api/pipeline/corpus/rebuild`, { method: "POST" });
  if (!r.ok) throw new Error("Corpus rebuild failed");
  return r.json();
}

// ─── Config endpoints ────────────────────────────────────────────────────────

export async function fetchConfig(): Promise<PlamaConfig> {
  const r = await fetch(`${API_BASE}/api/config`);
  if (!r.ok) throw new Error("Config fetch failed");
  return r.json();
}

export async function updateConfig(config: UpdateConfigRequest): Promise<PlamaConfig> {
  const r = await fetch(`${API_BASE}/api/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (!r.ok) throw new Error("Config update failed");
  return r.json();
}

