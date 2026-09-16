# dedup.py - 중복 청크 제거
from langchain_core.documents import Document

def dedup(docs: list[Document]) -> list[Document]:
    seen = set()
    result = []
    for doc in docs:
        # 공백 정규화해서 비교함 (완전히 똑같은 텍스트(공백 여부)만 중복으로 보는 걸 방지함)
        normalized = " ".join(doc.page_content.split())
        if normalized not in seen:
            seen.add(normalized)
            result.append(doc)
    return result