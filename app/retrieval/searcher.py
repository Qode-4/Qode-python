# searcher.py
import os
import re
import json
import psycopg
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from app.embedding.embedder import embed_query

load_dotenv(override=True)

def get_connection():
    return psycopg.connect(os.getenv("DATABASE_URL"))

# 테스트 코드를 묻는 질의 판별용 키워드
# 영어는 단어 경계로 매칭 (latest, contest 같은 오탐 방지)
TEST_QUERY_PATTERN = re.compile(
    r"테스트|단위\s*테스트|통합\s*테스트|모킹|목\s*객체|픽스처|스텁|커버리지"
    r"|\b(tests?|testing|specs?|mocks?|mocking|stubs?|fixtures?|asserts?|assertions?"
    r"|pytest|unittest|jest|vitest|junit|rspec|e2e|tdd|coverage)\b",
    re.IGNORECASE,
)


def is_test_query(query: str) -> bool:
    # 질의가 테스트 코드를 겨냥하는지 판단
    return bool(TEST_QUERY_PATTERN.search(query))


class CodeRetriever(BaseRetriever):
    project_id: str
    top_k: int = 5
    include_tests: bool | None = None  # None이면 질의 내용으로 자동 판단

    def _get_relevant_documents(self, query: str) -> list[Document]:
        query_vector = embed_query(query)
        include_tests = (
            is_test_query(query) if self.include_tests is None else self.include_tests
        )

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT content, metadata,
                           1 - (embedding <=> %s::vector) AS score
                    FROM code_embeddings
                    WHERE project_id = %s
                      AND (%s OR COALESCE((metadata->>'is_test')::boolean, false) = false)
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (query_vector, self.project_id, include_tests, query_vector, self.top_k)
                )
                rows = cur.fetchall()
        
        return [
            Document(
                page_content=row[0],
                metadata={**row[1], "score": row[2]}
            )
            for row in rows
        ]

def search(query: str, project_id: str, top_k: int, include_tests: bool | None = None) -> list[Document]:
    retriever = CodeRetriever(project_id=project_id, top_k=top_k, include_tests=include_tests)
    return retriever.invoke(query)