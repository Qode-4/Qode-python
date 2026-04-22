# pipeline.py
import time
from langchain_core.documents import Document
from .searcher import search
from .filter import filter_by_threshold
from .dedup import dedup
from .reranker import rerank

async def search_pipeline(query: str, project_id: str, top_k: int) -> dict:
    start_time = time.time()

    try:
        raw_results = search(query, project_id, top_k)
        filtered = filter_by_threshold(raw_results)
        deduped = dedup(filtered)
        reranked = rerank(query, deduped)

        return {
            "chunks": reranked,
            "search_meta": {
                "total_found": len(raw_results),
                "after_filter": len(filtered),
                "after_dedup": len(deduped),
                "final": len(reranked),
                "search_time_ms": int((time.time() - start_time) * 1000),
            }
        }
    except Exception as e:
        return {
            "chunks": [],
            "search_meta": {
                "total_found": 0,
                "error": str(e),
                "search_time_ms": int((time.time() - start_time) * 1000),
            }
        }