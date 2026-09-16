# pipeline.py
import time
from langchain_core.documents import Document
from .searcher import hybrid_search, is_test_query
from .expand import expand_symbols
from .filter import filter_by_threshold
from .dedup import dedup
from .reranker import rerank

async def search_pipeline(query: str, project_id: str, top_k: int) -> dict:
    start_time = time.time()

    try:
        raw_results = hybrid_search(query, project_id, top_k)
        filtered = filter_by_threshold(raw_results)
        deduped = dedup(filtered)
        reranked = rerank(query, deduped, top_k)
        # 리랭크 결과 본문이 부르는 함수·클래스의 정의 청크를 한 홉 더 붙인다 (뒤에 덧붙이므로 trimContext 에 잘려도 원래 결과가 먼저 남는다)
        expanded = expand_symbols(reranked, project_id, include_tests=is_test_query(query), query=query)

        return {
            "chunks": expanded,
            "search_meta": {
                "total_found": len(raw_results),
                "after_filter": len(filtered),
                "after_dedup": len(deduped),
                "after_rerank": len(reranked),
                "final": len(expanded),
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