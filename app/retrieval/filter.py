# filter.py
import os
from langchain_core.documents import Document

SCORE_THRESHOLD = float(os.getenv("SCORE_THRESHOLD", 0.7))

def filter_by_threshold(docs: list[Document], threshold: float = SCORE_THRESHOLD) -> list[Document]:
    return [doc for doc in docs if doc.metadata.get("score", 1.0) >= threshold]