"use client";
import React, {
  createContext, useCallback, useContext, useEffect, useRef, useState,
} from "react";
import { 
  fetchHealth, newSession, HealthResponse, chatStream, ChatMeta, consolidateSession,
  fetchAvailableModels, fetchTrust, fetchConfig, LMStudioModel, TrustEntry, PlamaConfig
} from "@/lib/api";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface Message {
  id: number;
  role: "user" | "assistant";
  content: string;
  meta?: ChatMeta;
  status?: string;
  streaming?: boolean;
}

type ToastType = "success" | "error" | "info";
interface Toast { id: number; msg: string; type: ToastType; }

interface AppCtx {
  sessionId: string | null;
  health: HealthResponse | null;
  toasts: Toast[];
  toast: (msg: string, type?: ToastType) => void;
  startNewSession: () => Promise<void>;
  refreshHealth: () => Promise<void>;
  
  // Cached Global Data
  models: LMStudioModel[];
  config: PlamaConfig | null;
  trust: Record<string, TrustEntry>;
  loadModels: () => Promise<void>;
  loadConfig: () => Promise<void>;
  loadTrust: () => Promise<void>;

  // Global Chat State
  messages: Message[];
  isStreaming: boolean;
  sendMessage: (text: string, overrideModel?: string) => Promise<void>;
  stopStreaming: () => void;
  clearMessages: () => void;
}

const Ctx = createContext<AppCtx>({} as AppCtx);
export const useApp = () => useContext(Ctx);

let toastId = 0;
let msgId = 0;

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  
  // Cached Global Data
  const [models, setModels] = useState<LMStudioModel[]>([]);
  const [config, setConfig] = useState<PlamaConfig | null>(null);
  const [trust, setTrust] = useState<Record<string, TrustEntry>>({});

  // Global Chat State
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  const toast = useCallback((msg: string, type: ToastType = "info") => {
    const id = ++toastId;
    setToasts(p => [...p, { id, msg, type }]);
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 3500);
  }, []);

  /* ─── Data Loaders ─────────────────────────────────────────────── */

  const loadModels = useCallback(async () => {
    try {
      const data = await fetchAvailableModels();
      setModels(data.models);
    } catch { /* skip */ }
  }, []);

  const loadConfig = useCallback(async () => {
    try {
      const c = await fetchConfig();
      setConfig(c);
    } catch { /* skip */ }
  }, []);

  const loadTrust = useCallback(async () => {
    try {
      const { trust_registry } = await fetchTrust();
      setTrust(trust_registry);
    } catch { /* skip */ }
  }, []);

  const refreshHealth = useCallback(async () => {
    try {
      const h = await fetchHealth();
      setHealth(h);
    } catch {
      setHealth(null);
    }
  }, []);

  const startNewSession = useCallback(async () => {
    try {
      // 1. もし現在のセッションにメッセージがあるなら、集約処理を完了まで待機
      if (sessionId && messages.length > 0) {
        toast("記憶を定着させています...", "info");
        try {
          await consolidateSession(sessionId);
          toast("会話から新しいファクトを記憶しました", "success");
          await refreshHealth();
        } catch (err) {
          console.error("Consolidation failed:", err);
          toast("記憶の定着に失敗しました", "error");
          // 失敗してもセッション更新は進めるか、ここで止めるか選択可能
          // 今回は確実に新しい会話を始められるよう継続します
        }
      }

      // 2. 新しいセッションを開始
      const { session_id } = await newSession();
      setSessionId(session_id);
      setMessages([]); 
      toast("新しいセッションを開始しました", "success");
    } catch {
      toast("セッション作成に失敗しました", "error");
    }
  }, [sessionId, messages.length, toast, refreshHealth]);

  // 初回起動時の初期化
  useEffect(() => {
    const init = async () => {
      await refreshHealth();
      // セッションがない場合のみ新しく作成
      const { session_id } = await newSession();
      setSessionId(session_id);
    };
    init();
    
    // Initial data load (Only once)
    loadModels();
    loadConfig();
    loadTrust();

    const timer = setInterval(refreshHealth, 15_000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // 空の依存配列で一度だけ実行

  // --- Global Chat Logic ---
  
  const stopStreaming = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsStreaming(false);
    }
  }, []);

  const clearMessages = useCallback(() => setMessages([]), []);

  const sendMessage = useCallback(async (text: string, overrideModel?: string) => {
    if (!text.trim() || isStreaming || !sessionId) return;
    
    setIsStreaming(true);
    const userMsg: Message = { id: ++msgId, role: "user", content: text };
    const botMsg: Message = { id: ++msgId, role: "assistant", content: "", streaming: true };
    
    setMessages(p => [...p, userMsg, botMsg]);
    
    abortControllerRef.current = new AbortController();

    try {
      for await (const chunk of chatStream(
        { session_id: sessionId, message: text, override_model: overrideModel },
        abortControllerRef.current.signal
      )) {
        if (chunk.status) {
          setMessages(p =>
            p.map(m => m.id === botMsg.id ? { ...m, status: chunk.status } : m)
          );
        }
        if (chunk.delta) {
          setMessages(p =>
            p.map(m => m.id === botMsg.id ? { ...m, content: m.content + chunk.delta, status: undefined } : m)
          );
        }
        if (chunk.done && chunk.meta) {
          setMessages(p =>
            p.map(m => m.id === botMsg.id ? { ...m, streaming: false, meta: chunk.meta, status: undefined } : m)
          );
        }
      }
    } catch (e: any) {
      if (e?.name !== "AbortError") {
        toast("ストリームエラーが発生しました", "error");
        setMessages(p => p.map(m => m.id === botMsg.id ? { ...m, content: m.content + "\n[Error occurred during stream]" } : m));
      }
    } finally {
      setIsStreaming(false);
      setMessages(p => p.map(m => m.id === botMsg.id ? { ...m, streaming: false } : m));
      abortControllerRef.current = null;
    }
  }, [sessionId, isStreaming, toast]);


  return (
    <Ctx.Provider value={{ 
      sessionId, health, toasts, toast, startNewSession, refreshHealth,
      models, config, trust, loadModels, loadConfig, loadTrust,
      messages, isStreaming, sendMessage, stopStreaming, clearMessages
    }}>
      {children}
      <div className="toast-container">
        {toasts.map(t => (
          <div key={t.id} className={`toast toast-${t.type}`}>{t.msg}</div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
