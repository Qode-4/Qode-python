from langchain_core.documents import Document

def recall_at_k(
        retrieved: list[Document],
        keywords: list[str],
        k: int
) -> float:
    '''top-k 안에 키워드를 포함한 청크가 있나?'''
    top_k = retrieved[:k]
    for doc in top_k:
        if any(kw.lower() in doc.page_content.lower() for kw in keywords):
            return 1.0
    return 0.0

def mrr(retrieved: list[Document], keywords: list[str]) -> float:
    '''정답 청크가 몇 번째 순위'''
    for rank, doc in enumerate(retrieved, 1):
        if any(kw.lower() in doc.page_content.lower() for kw in keywords):
            return 1.0 / rank
    return 0.0