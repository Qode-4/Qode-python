# DB 연결 통합 테스트 — DATABASE_URL 없으면 건너뛴다. 실행마다 임베딩 호출 4번(OpenAI).
import os

import pytest
from dotenv import load_dotenv

from app.retrieval.searcher import get_connection, hybrid_search

load_dotenv()
pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL 없음")


@pytest.fixture(scope="module")
def project_id():
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT project_id FROM code_embeddings LIMIT 1")
        row = cur.fetchone()
    if row is None:
        pytest.skip("code_embeddings 비어 있음")
    return row[0]


def test_search_returns_results(project_id):
    assert len(hybrid_search("function", project_id, 5)) > 0


def test_search_top_k(project_id):
    assert len(hybrid_search("function", project_id, 3)) <= 3


def test_search_document_structure(project_id):
    for doc in hybrid_search("function", project_id, 5):
        assert isinstance(doc.page_content, str) and doc.page_content
        assert "score" in doc.metadata


def test_search_gibberish_query_does_not_crash(project_id):
    assert len(hybrid_search("afadljkajdsdlkfsjd", project_id, 5)) <= 5
