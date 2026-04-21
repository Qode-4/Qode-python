# dedup.py - 중복 청크 제거
from langchain_core.documents import Document

def dedup(docs: list[Document]) -> list[Document]:
    seen = set()
    result = []
    for doc in docs:
        if doc.page_content not in seen:
            seen.add(doc.page_content)
            result.append(doc)
    return result