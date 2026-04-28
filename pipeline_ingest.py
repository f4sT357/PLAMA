"""
PLAMA v1.4 - PipelineIngest (stub)
n8n → PLAMA corpus ingest endpoint handler.
Full ChromaDB embedding in v2.0.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import chromadb

from memory_manager import CORPUS_DIR, memory_manager

logger = logging.getLogger(__name__)

CORPUS_COLLECTION = "plama_corpus"


class PipelineIngest:
    def __init__(self):
        self._mm = memory_manager

    def ingest(self, source: str, language: str, documents: list[dict]) -> dict:
        """
        Accept documents from n8n and store in ChromaDB corpus collection.
        documents: [{text, url, fetched_at}]
        v2.0 TODO: use PLAMA embedding model + cosine similarity in BiasChecker.
        """
        if not documents:
            return {"ingested": 0, "skipped": 0}

        try:
            chroma = self._mm._chroma
            col = chroma.get_or_create_collection(CORPUS_COLLECTION)

            ingested = 0
            skipped = 0
            texts, ids, metas = [], [], []

            for doc in documents:
                text = doc.get("text", "").strip()
                if not text:
                    skipped += 1
                    continue
                url = doc.get("url", "")
                ts = doc.get("fetched_at", datetime.now(timezone.utc).isoformat())
                doc_id = f"corpus_{source}_{hash(url + text[:30]) & 0xFFFFFF:06x}"

                texts.append(text[:2000])  # cap at 2000 chars per chunk
                ids.append(doc_id)
                metas.append({"source": source, "language": language, "url": url, "fetched_at": ts})
                ingested += 1

            if texts:
                embs = self._mm._embed(texts)
                # Upsert to avoid duplicates on re-ingest
                col.upsert(ids=ids, embeddings=embs, documents=texts, metadatas=metas)

            logger.info("PipelineIngest: source=%s ingested=%d skipped=%d", source, ingested, skipped)
            return {"ingested": ingested, "skipped": skipped}

        except Exception as e:
            logger.error("PipelineIngest error: %s", e)
            return {"ingested": 0, "skipped": len(documents), "error": str(e)}

    def get_corpus_stats(self) -> dict:
        try:
            chroma = self._mm._chroma
            col = chroma.get_or_create_collection(CORPUS_COLLECTION)
            count = col.count()
            return {"total_documents": count, "collection": CORPUS_COLLECTION}
        except Exception as e:
            return {"total_documents": 0, "error": str(e)}

    def rebuild_corpus_index(self) -> dict:
        """Drop and rebuild corpus collection. (v2.0: will re-embed all stored docs.)"""
        try:
            chroma = self._mm._chroma
            chroma.delete_collection(CORPUS_COLLECTION)
            chroma.get_or_create_collection(CORPUS_COLLECTION)
            return {"success": True, "message": "Corpus index cleared. Re-ingest via n8n to repopulate."}
        except Exception as e:
            return {"success": False, "error": str(e)}


pipeline_ingest = PipelineIngest()
