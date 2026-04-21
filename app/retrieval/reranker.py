# reranker.py - 재정렬
from langchain_core.documents import Document

def rerank(query: str, docs: list[Document]) -> list[Document]:
    # TODO: rerank 모델 붙일 자리
    return docs