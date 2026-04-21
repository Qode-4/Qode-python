# reranker.py - 재정렬
from langchain_core.documents import Document

def rerank(query: str, docs: list[Document]) -> list[Document]:
    # TODO: 나중에 Cross-encoder 붙임
    # score 기준 정렬
    return sorted(
        docs,
        key= lambda doc: doc.metadata.get("score", 0.0),
        reverse=True
    )