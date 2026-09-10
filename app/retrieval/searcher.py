# searcher.py
import os
import re
import json
import psycopg
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from rank_bm25 import BM25Okapi
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


# ===== 하이브리드 검색 (벡터 + BM25 → RRF 병합) =====

# 코드 식별자 단위 토큰화. 질문과 청크를 같은 규칙으로 잘라야 매칭된다.
# 한국어 토큰은 코드에 없으므로 버린다 — 한국어만 있는 질문이면 벡터 검색만 동작.
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")

# 병합 전 각 검색이 뽑는 후보 수. top_k(5)보다 넉넉히 잡아야
# "정답이 6~20위에 있던" 청크가 병합에서 구제된다.
CANDIDATE_K = 20


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


def _rrf_merge(ranked_lists: list[list[tuple]], top_k: int, k: int = 60) -> list[Document]:
    """(content, metadata, cosine_score) 행 목록들을 등수 기반(RRF)으로 병합.

    점수 단위가 서로 다른 두 검색을 등수로만 합산한다: 1/(k + 등수).
    metadata의 score에는 코사인 유사도를 그대로 유지한다 —
    filter.py의 threshold(코사인 기준)와 Node 쪽 relevanceScore 계약을 지키기 위함.
    """
    rrf_scores: dict = {}
    docs: dict = {}
    for rows in ranked_lists:
        for rank, row in enumerate(rows):
            content, meta, cosine = row[0], row[1], row[2]
            key = (meta.get("source"), meta.get("start_line"), content[:50])
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            if key not in docs:
                docs[key] = Document(page_content=content, metadata={**meta, "score": cosine})
    ordered = sorted(rrf_scores, key=rrf_scores.get, reverse=True)[:top_k]
    return [docs[key] for key in ordered]


def hybrid_search(query: str, project_id: str, top_k: int, include_tests: bool | None = None) -> list[Document]:
    query_vector = embed_query(query)
    if include_tests is None:
        include_tests = is_test_query(query)

    # 프로젝트 청크 전체를 코사인 점수와 함께 한 번에 가져와 두 랭킹(벡터/BM25)에 재사용.
    # ponytail: 전체 로드 + 쿼리마다 BM25 재빌드 — 수천 청크면 수십 ms. 느려지면 project_id별 인덱스 캐시.
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT content, metadata,
                       1 - (embedding <=> %s::vector) AS score
                FROM code_embeddings
                WHERE project_id = %s
                  AND (%s OR COALESCE((metadata->>'is_test')::boolean, false) = false)
                """,
                (query_vector, project_id, include_tests),
            )
            rows = cur.fetchall()

    # 1) 벡터 랭킹: 코사인 내림차순 (기존 검색과 동일한 순서)
    vector_rows = sorted(rows, key=lambda r: r[2], reverse=True)[:CANDIDATE_K]

    # 2) BM25 랭킹: 어휘 매칭 점수 내림차순, 0점(질문 토큰이 하나도 없는 청크)은 제외
    bm25_rows = []
    query_tokens = tokenize(query)
    if rows and query_tokens:
        bm25 = BM25Okapi([tokenize(r[0]) for r in rows])
        scores = bm25.get_scores(query_tokens)
        ranked = sorted(range(len(rows)), key=scores.__getitem__, reverse=True)
        bm25_rows = [rows[i] for i in ranked[:CANDIDATE_K] if scores[i] > 0]

    return _rrf_merge([vector_rows, bm25_rows], top_k)