# 🧠 PLAMA 2.0 (Personal Local AI Memory Assistant)

> **「忘れない、偏らない、あなただけのAI」**

PLAMA 2.0 は、ローカル LLM (LM Studio) をエンジンとして活用し、ユーザーとの会話から永続的な「記憶（事実）」を構築・活用する次世代のパーソナルアシスタントです。

## 🌟 主な特徴

### 1. 鉄壁の記憶集約 (Robust Memory Consolidation)
会話の節目に、LLM が内容を分析して重要な事実を抽出します。
- **耐障害パース**: 軽量・高速なモデル（LFM等）が生成する不安定な JSON フォーマットを、独自のアルゴリズムでリアルタイム修復。
- **重複排除 (Dedup)**: ChromaDB によるベクトル検索を用い、既に知っている情報は重複して登録しません。

### 2. 動的モデルルーティング (Dynamic Model Routing)
トピックに応じて、最適な LLM を自動的に指名します。
- **Geopolitics**: 政治・外交に強い Mistral-7B 等
- **Code/Technical**: 専門知識に特化した Qwen-9B 等
- **General**: 日常会話に適した軽量モデル

### 3. バイアス検知 & 信頼性管理 (Bias Checker & Trust Registry)
特定の見解に偏った回答や、不自然なトークン注入を検知します。
- **リアルタイム検知**: 回答内容を LFM (Liquid Foundation Model) でスキャンし、バイアススコアを算出。
- **モデル評価**: 各モデルの過去の「誠実さ」をスコアリングし、ルーティングの優先順位に反映。

### 4. ローカルファースト & プライバシー
すべてのデータ、すべての推論はあなたの PC 内で完結します。
- **DB**: ChromaDB (ベクトル検索) + JSON (構造化データ)
- **Engine**: LM Studio (Local Server)

## 🚀 クイックスタート

### 前提条件
- [LM Studio](https://lmstudio.ai/) がインストールされ、Local Server (Port 1234) が起動していること。
- Python 3.10 以上
- Node.js 18 以上

### 起動方法
ルートディレクトリにあるバッチファイルを実行するだけで、バックエンドとフロントエンドが同時に立ち上がります。

```bash
./start_plama.bat
```

手動で起動する場合：
- **Backend**: `uvicorn main:app --reload --port 8000`
- **Frontend**: `cd frontend && npm run dev`

## 🏗 アーキテクチャ

- **Frontend**: Next.js 14, Tailwind CSS, TypeScript
- **Backend**: FastAPI (Python), ChromaDB, Sentence-Transformers
- **Inference**: OpenAI Compatible API (LM Studio)

## 🛠 カスタマイズ
`memory_data/config.json` を通じて、メインモデルや集約用モデルを自由に変更可能です。UI の「Models」タブからも直感的に設定できます。

---
*PLAMA 2.0 - Developed for Personal Growth and Knowledge Management.*
