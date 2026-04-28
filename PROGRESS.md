# PLAMA 実装進捗サマリー（セッション引き継ぎ用）
## 生成日: 2026-04-09

---

## 完了済み（v1.4 バックエンド全体）

### ファイル一覧（backend/）

| ファイル | 状態 | 概要 |
|---|---|---|
| `models.py` | ✅ 完成 | MemorySchema v2.0 全Pydanticモデル定義 |
| `model_router.py` | ✅ 完成 | キーワードベースルーティング + LM Studio動的ロードstub |
| `memory_manager.py` | ✅ 完成 | 記憶CRUD + ChromaDB + 重複検出(cosine) + 中間consolidate |
| `prompt_builder.py` | ✅ 完成 | システムプロンプト生成 + bias_flag警告注入 |
| `bias_checker.py` | ✅ v1.4stub | ルールベース（CJKトークン + キーワード）。v2.0でLFM化 |
| `trust_registry.py` | ✅ 完成 | TrustRegistry CRUD ラッパー |
| `pipeline_ingest.py` | ✅ v1.4stub | n8n受け口 + ChromaDB upsert（埋め込みはPLAMA側で生成） |
| `main.py` | ✅ 完成 | FastAPI全エンドポイント（v1.3継承9本 + v2.0新規9本） |
| `requirements.txt` | ✅ 完成 | fastapi/uvicorn/httpx/pydantic/chromadb/sentence-transformers/torch |
| `start_plama.bat` | ✅ 完成 | Windows起動スクリプト |

---

## 実装済みエンドポイント

### v1.3継承
- GET  /api/health
- POST /api/session/new
- POST /api/chat/stream        (SSEストリーミング)
- POST /api/session/{id}/consolidate
- GET  /api/memory
- GET  /api/memory/facts       (?source_type=)
- DELETE /api/memory/facts/{id}
- POST /api/memory/search
- POST /api/memory/rebuild

### v2.0新規
- GET  /api/models/trust
- POST /api/models/route
- POST /api/models/load
- POST /api/models/unload
- GET  /api/bias/flags         (?model=&limit=)
- POST /api/bias/check
- POST /api/pipeline/n8n-ingest
- GET  /api/pipeline/corpus/stats
- POST /api/pipeline/corpus/rebuild

---

## 未実装（次セッションで着手すべきもの）

### フロントエンド（Next.js）
- `frontend/` ディレクトリ未作成
- 必要なページ: チャット画面 / メモリビューア / ルーティング確認パネル
- SSE受信 + trust_score表示

### v1.5対応（バックエンド追加）
- `bias_checker.py`: LFM呼び出し実装（現在ルールベースのみ）
- `bias_checker.py`: ChromaDBコーパスコサイン類似度スコアリング（threshold 0.75）
- `model_router.py`: unload_model完全実装（keep_alive=0）

### v2.0対応
- `pipeline_ingest.py`: robots.txt確認 + クロール間隔設定
- `main.py`: LFMをbiasチェック専用で常駐（別ポート or Ollama経由）

### 設定・インフラ
- `.env` ファイル（LM Studio URL, モデル名, 閾値を外部化）
- `docker-compose.yml`（ChromaDB永続化 + バックエンド）
- `memory_data/memory.json` 初期ファイル（空のMemorySchema v2.0）

---

## 設計メモ（重要）

### 重複検出の閾値
- `PLAMA_DEDUP_THRESHOLD=0.12`（cosine distance）
- 小さいほど厳しい。0.12は「ほぼ同文」のみ弾く設定
- 調整が必要な場合は memory_manager.py の `DEDUP_THRESHOLD` を変更

### 中間consolidate
- `PLAMA_MID_SESSION_THRESHOLD=20`（メッセージ数）
- 閾値超過 → BackgroundTasksで非同期実行
- consolidate後もshort_termはクリアされる（注意）

### Arc A580構成での現実的な運用
- Qwen3.5 4B Q4_K_M（~5.5GB）1モデルのみGPU
- LFM（v2.0）はCPU推論（embedding専用に徹する）
- consolidationモデルは同じQwen3.5 4Bでも可（9B不要）

### MemorySchema後方互換
- v1.x memory.jsonはそのまま読み込める
- 新フィールド（model_origin等）はデフォルト値で補完

---

## 起動方法（現時点）

```
cd plama/backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

LM Studio: localhost:1234でサーバー起動 + モデルロード済みであること
