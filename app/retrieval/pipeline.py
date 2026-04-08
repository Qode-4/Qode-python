# pipeline.py
import time
from langchain_core.documents import Document
from .searcher import search
from .filter import filter_by_threshold
from .dedup import dedup
from .reranker import rerank

async def search_pipeline(query: str) -> dict:
    start_time = time.time()

    raw_results = await search(query)
    filtered = filter_by_threshold(raw_results)
    deduped = dedup(filtered)
    reranked = rerank(query, deduped)

    return {
        "chunks": reranked,
        "search_meta": {
            "total_found": len(raw_results),
            "search_time_ms": int((time.time() - start_time) * 1000),
        }
    }