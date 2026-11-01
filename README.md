#  PLAMA 2.0 (Personal Local AI Memory Assistant)

> **「忘れない、コントローラブル、あなただけのAI」**

PLAMA 2.0 は、ローカル LLM (LM Studio) をエンジンとして活用し、ユーザーとの会話から永続的な「記憶（事実）」を構築・活用する次世代のパーソナルアシスタントです。
## Goal:一日中(16h)使い続けて文脈を失わずコンテキスト腐敗が体感不能であること、想定使用環境でllm動作速度が人間の文章を読む速度を常に上回る状態を維持できること

##  主な特徴

### 1. 鉄壁の記憶集約 (Robust Memory Consolidation)
会話の節目に、LLM が内容を分析して重要な事実を抽出します。
- **耐障害パース**: 軽量・高速なモデル（LFM等）が生成する不安定な JSON フォーマットを、独自のアルゴリズムでリアルタイム修復。
- **重複排除 (Dedup)**: ChromaDB によるベクトル検索を用い、既に知っている情報は重複して登録しません。

### 2. 動的モデルルーティング (Dynamic Model Routing)
トピックに応じて、最適な LLM を自動的に指名します。
- **Geopolitics**: 政治・外交に強い Mistral-7B 等
- **Code/Technical**: 専門知識に特化した Qwen-9B 等
- **General**: 日常会話に適した軽量モデル

### 3. バイアス検知 & 信頼性管理 (Bias Checker & Trust Registry)(実装中)
特定の見解に偏った回答や、不自然なトークン注入を検知します。
- **リアルタイム検知**: 回答内容を LFM (Liquid Foundation Model) でスキャンし、バイアススコアを算出。
- **モデル評価**: 各モデルの過去の「誠実さ」をスコアリングし、ルーティングの優先順位に反映。

### 4. ローカルファースト & プライバシー
すべてのデータ、すべての推論はあなたの PC 内で完結します。
- **DB**: SQLite (会話原文の永続保存) + JSON (構造化ファクト・設定) + ChromaDB (再構築可能な検索インデックス)
- **Engine**: LM Studio (Local Server)

## 🚀 クイックスタート

### 前提条件
- [LM Studio](https://lmstudio.ai/) がインストールされ、Local Server (Port 1234) が起動していること。
- Python 3.10 以上
- Node.js 20.9 以上 (Next.js 16 の要件)

### 起動方法
ルートディレクトリにあるバッチファイルを実行するだけで、バックエンドとフロントエンドが同時に立ち上がります。

```bash
./start_plama.bat
```

手動で起動する場合：
- **Backend**: `uvicorn main:app --reload --port 8000`
- **Frontend**: `npm run dev` (リポジトリルートで実行)

## アーキテクチャ

- **Frontend**: Next.js 16, React 19, TypeScript
- **Backend**: FastAPI (Python), SQLite, ChromaDB, Sentence-Transformers
- **Inference**: OpenAI Compatible API (LM Studio)

##  カスタマイズ
`memory_data/config.json` を通じて、メインモデルや集約用モデルを自由に変更可能です。UI の「Models」タブからも直感的に設定できます。

## 安定化ブランチの変更点（2026-11-02）
- 原文をセッション別にSQLiteへ追記保存し、ページ再読み込み後も過去セッションを再開できます。
- 破損した memory.json を空データで上書きせず、エラー停止します。
- 記憶は明示的に訂正でき、旧版を superseded として保存します。
- 意味検索に日本語文字列・英語単語に基づく検索を併用し、期限切れや superseded の事実を通常検索から除外します。
- 記憶抽出の根拠として USER メッセージIDと原文引用を検証します。
- FastAPI は start_plama.bat で localhost にバインドします。
- バックアップ・復旧手順: [RUNBOOK.md](RUNBOOK.md)
- 評価ツール: [benchmarks/README.md](benchmarks/README.md)

**注意:** 16時間利用や4Bモデルによる高精度な記憶抽出は開発目標であり、実測による達成確認は未実施です。クラウド提供モデルの接続は現行コードで汎用実装済みとはみなせません。

## 今後について
○記憶のマネジメントについて
•	タイムスタンプ＋TTL：記憶に有効期限を設定、期限切れは「要確認」フラグに移行
	•	参照頻度による重み減衰：長期間参照されない記憶のスコアを下げる
	•	矛盾検出：新しい記憶が既存記憶と衝突したとき自動フラグ
---
*PLAMA 2.0 - Developed for Personal Growth and Knowledge Management.*
