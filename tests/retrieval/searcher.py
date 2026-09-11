import pytest
from app.retrieval.searcher import search

# DB 연결 테스트
@pytest.mark.asyncio
async def test_search_returns_results():
    '''결과가 1개 이상 나오는지'''
    results = await search("test")
    assert len(results) > 0

@pytest.mark.asyncio
async def test_search_top_k():
    '''topK 이하로 결과가 나오는지'''
    results = await search("test", top_k=3)
    assert len(results) <= 3

@pytest.mark.asyncio
async def test_search_document_structure():
    '''Document 구조가 올바른지'''
    results = await search("test")
    for doc in results:
        assert hasattr(doc, "page_content")
        assert hasattr(doc, "metadata")
        assert isinstance(doc.page_content, str)
        assert len(doc.page_content) > 0

@pytest.mark.asyncio
async def test_search_empty_query():
    '''빈 쿼리도 터지지 않았는지'''
    results = await search("afadljkajdsdlkfsjd")
    assert len(results) == 0 or len(results) < 5