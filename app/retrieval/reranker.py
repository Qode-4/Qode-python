# reranker.py - 재정렬
import logging
import os

from langchain_cohere import CohereRerank
from langchain_core.documents import Document
from langsmith import traceable

RERANKER_ENABLED = os.getenv("RERANKER_ENABLED", "true").lower() == "true"
logger = logging.getLogger(__name__)

_reranker = None

def _get_reranker():
    global _reranker
    if _reranker is None :
        _reranker = CohereRerank(model="rerank-v3.5")
    return _reranker

def _fallback(docs: list[Document]) -> list[Document]:
    return sorted(docs, key=lambda d: d.metadata.get("score", 0.0), reverse=True)

@traceable(name="rerank")
def rerank(query: str, docs: list[Document], top_k: int | None = None) -> list[Document]:
    # Cross-encoder로 재정렬
    # 실패하거나 비활성화된 경우 백터 검색 점수 순으로 폴백
    if not docs:
        return []

    if not RERANKER_ENABLED:
        result = _fallback(docs)
        return result[:top_k] if top_k else result

    try:
        reranker = _get_reranker()
        # CohereRerank 의 top_n 기본값은 3 이다 — 그대로 두면 top_k 를 몇으로 올려도 LLM 에는 3개만 간다
        # (2026-09-16 실측: top_k 10 → final 3). 전부 돌려받고 아래에서 top_k 로 자른다.
        reranker.top_n = len(docs)
        reranked_docs = reranker.compress_documents(documents=docs, query=query)

        for d in reranked_docs:
            d.metadata["vector_score"] = d.metadata.get("score", 0.0)
            d.metadata["rerank_score"] = d.metadata.get("relevance_score", 0.0)

        result = reranked_docs

    except Exception:
        logger.exception("rerank failed, falling back to vector score")
        result = _fallback(docs)

    return result[:top_k] if top_k else result