# reranker.py - 재정렬
import logging
import os
import threading
import torch

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
RERANKER_ENABLED = os.getenv("RERANKER_ENABLED", "true").lower() == "true"

_reranker = None
_lock = threading.Lock()


def _get_reranker():
    #임포트 시점에 2.2GB를 로드하면 지연시간이 길어지기 때문에 첫 요청 때만 로드하도록 전역 변수
    #중복 로드 방지를 위해 락을 걸음
    global _reranker
    if _reranker is None :
        with _lock:
            if _reranker is None: 
                from FlagEmbedding import FlagReranker
                logger.info("loading reranker: %s", RERANKER_MODEL)
                _reranker = FlagReranker(RERANKER_MODEL, use_fp16=torch.cuda.is_available())
                # _reranker = FlagReranker(RERANKER_MODEL, use_fp16=False)
    return _reranker

def _fallback(docs: list[Document]) -> list[Document]:
    return sorted(docs, key=lambda d: d.metadata.get("score", 0.0), reverse=True)

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
        scores = reranker.compute_score(
            [[query, d.page_content] for d in docs],
            normalize=True,
        )
        if not isinstance(scores, list): # 문서 1개 -> float
            scores = [scores]

        for d, s in zip(docs, scores):
            d.metadata["vector_score"] = d.metadata.get("score", 0.0)
            d.metadata["rerank_score"] = float(s)

        result = sorted(docs, key=lambda d: d.metadata["rerank_score"], reverse=True)

    except Exception:
        logger.exception("rerank failed, falling back to vector score")
        result = _fallback(docs)

    return result[:top_k] if top_k else result