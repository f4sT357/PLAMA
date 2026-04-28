"""
PLAMA v2.0 - PipelineIngest
n8n等からの入力を受け取り、ChromaDBのコーパス（plama_corpus）へ登録します。
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from memory_manager import memory_manager

logger = logging.getLogger(__name__)

CORPUS_COLLECTION = "plama_corpus"

class PipelineIngest:
    """
    外部ソースからの情報をベクトル化して保存する機能を提供します。
    """
    def __init__(self):
        self._mm = memory_manager

    async def ingest_from_n8n(self, source: str, language: str, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        n8nからのドキュメントリストを受け取り、一括でChromaDBに登録します。
        """
        if not documents:
            return {"ingested": 0, "status": "empty"}

        try:
            chroma = self._mm._chroma
            col = chroma.get_or_create_collection(CORPUS_COLLECTION)

            texts = []
            ids = []
            metas = []

            for doc in documents:
                text = doc.get("text", "").strip()
                if not text:
                    continue
                
                url = doc.get("url", "")
                doc_id = f"n8n_{uuid.uuid5(uuid.NAMESPACE_URL, url).hex[:12]}" if url else f"n8n_{uuid.uuid4().hex[:12]}"
                
                texts.append(text[:3000])
                ids.append(doc_id)
                metas.append({
                    "source": source,
                    "language": language,
                    "url": url,
                    "fetched_at": doc.get("fetched_at", datetime.now(timezone.utc).isoformat())
                })

            if texts:
                embeddings = self._mm._embed(texts)
                col.upsert(
                    ids=ids,
                    embeddings=embeddings,
                    documents=texts,
                    metadatas=metas
                )
                logger.info(f"Ingested {len(texts)} documents into {CORPUS_COLLECTION}")

            return {"ingested": len(texts), "status": "success"}

        except Exception as e:
            logger.error(f"Ingest failed: {e}")
            return {"ingested": 0, "status": "error", "message": str(e)}

    def get_corpus_count(self) -> int:
        """現在のコーパス登録件数を取得します。"""
        try:
            col = self._mm._chroma.get_collection(CORPUS_COLLECTION)
            return col.count()
        except:
            return 0

    def rebuild_corpus_index(self) -> dict:
        """コーパスインデックスを再作成します。"""
        try:
            chroma = self._mm._chroma
            try:
                chroma.delete_collection(CORPUS_COLLECTION)
            except:
                pass
            chroma.get_or_create_collection(CORPUS_COLLECTION)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

# Singleton instance
pipeline_ingest = PipelineIngest()
