from langchain_core.documents import Document
from app.retrieval.dedup import dedup

def make_doc(content):
    return Document(page_content=content, metadata={})

def test_no_duplicates():
    docs = [make_doc("doc1"), make_doc("doc2")]
    assert len(dedup(docs)) == 2

def test_exact_duplicate():
    docs = [make_doc("같은 내용"), make_doc("같은 내용")]
    assert len(dedup(docs)) == 1

def test_whitespace_duplicate():
    docs = [make_doc("같은 내용"), make_doc("같은  내용")]  # 공백 2개
    assert len(dedup(docs)) == 1

def test_empty():
    assert dedup([]) == []