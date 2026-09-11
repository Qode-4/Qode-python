# filter.py - 후 처리 필터
import os
from langchain_core.documents import Document

SCORE_THRESHOLD = float(os.getenv("SCORE_THRESHOLD", 0.1))

def filter_by_threshold(docs: list[Document], threshold: float = SCORE_THRESHOLD) -> list[Document]:
    return [doc for doc in docs if doc.metadata.get("score", 0.0) >= threshold] # searcher.py에서 score 메타 데이터 추가 시 threshold 설정