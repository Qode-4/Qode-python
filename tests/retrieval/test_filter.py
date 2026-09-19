from langchain_core.documents import Document
from app.retrieval.filter import filter_by_threshold

def make_doc(score=None):
    metadata = {"score": score} if score is not None else {}
    return Document(page_content="테스트", metadata=metadata)

def test_above_threshold():
    docs = [make_doc(0.9), make_doc(0.8)]
    result = filter_by_threshold(docs, threshold=0.7)
    assert len(result) == 2