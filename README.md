# 🧠 PLAMA 2.0 (Persistent Local AI Memory Adapter)

> **"AI Middleware Layer — Trust-Aware Multi-Model Orchestration"**

PLAMA 2.0 は、単なるチャットアシスタントを超え、信頼性の異なる複数の AI コンポーネントを調停し、記憶と信頼性を一元管理する **AI ミドルウェアレイヤー** です。

## 🛠️ v2.0 の設計転換 (Adapter Edition)

v1.x の「ローカル AI チャット with 記憶」という設計を継承しつつ、v2.0 では以下の機能を統合した **調停レイヤー** として再定義されています。

- **名前の再定義**: Assistant → **Adapter** (外部ツール群のコネクターとして機能)
- **Trust-Aware Routing**: 各モデルの信頼スコア（Trust Score）に基づいた動的ルーティング。
- **Bias & Neutrality**: LFM (Liquid Foundation Model) による非同期バイアス検出。
- **Pipeline Integration**: n8n 等の外部自動化ツールからのデータインジェスト対応。

## 🌟 主要コンポーネント

### 1. ModelRouter (Orchestrator)
クエリの内容を分析し、最適なモデル（Mistral, Qwen, LFM 等）に動的に振り分けます。GPU(Arc A580) と CPU(Ryzen/Core i7) のリソース配分を最適化し、複数モデルの常駐を実現します。

### 2. BiasChecker (Guardrail)
LFM を用いて、モデルの出力に含まれるイデオロギー的バイアス、プロパガンダフレーミング、または不自然なトークン注入をリアルタイムで監視・フラグ立てします。

### 3. TrustRegistry (Governance)
モデルごとの出力信頼性を定量的に追跡。バイアス検出履歴に基づき、ルーティングの優先順位を動的に変更します。

### 4. MemorySchema v2.0
モデルの出所（model_origin）、信頼スコア（trust_score）、バイアスフラグ（bias_flag）を保持する拡張スキーマ。

## 🚀 外部連携 (n8n Pipeline)
n8n を介して外部メディア（外交部、国営メディア等）からプロパガンダコーパスを収集し、PLAMA の ChromaDB にインジェスト。回答の「フレーミング類似度」の判定基準として活用します。

---
*PLAMA 2.0 Adapter - AI Middleware for Trusted Intelligence.*
