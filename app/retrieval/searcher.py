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


# ===== 하이브리드 검색 (벡터 + 키워드 → RRF 병합) =====

# 질문 속 코드 식별자 후보: 영문자로 시작하는 3글자 이상 토큰 (retries, follow_redirects 등)
IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")

# 병합 전 각 검색이 뽑는 후보 수. top_k(5)보다 넉넉히 잡아야
# "정답이 6~20위에 있던" 청크가 병합에서 구제된다.
CANDIDATE_K = 20

# 프로젝트 청크의 이 비율 이상에 등장하는 키워드는 변별력이 없으므로 버린다.
# (예: httpx 레포에서 'httpx'는 청크의 39%에 등장 — 매칭 순위만 오염시킨다)
MAX_KEYWORD_DF_RATIO = 0.2


def extract_keywords(query: str, max_keywords: int = 8) -> list[str]:
    # 등장 순서를 유지한 중복 제거. 한국어 단어는 코드에 없으므로 버린다.
    return list(dict.fromkeys(IDENTIFIER_PATTERN.findall(query)))[:max_keywords]


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
    keywords = extract_keywords(query)

    with get_connection() as conn:
        with conn.cursor() as cur:
            # 1) 벡터 검색 (기존과 동일, 후보만 CANDIDATE_K로 확대)
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
                (query_vector, project_id, include_tests, query_vector, CANDIDATE_K),
            )
            vector_rows = cur.fetchall()

            # 2) 너무 흔한 키워드 제거: 매칭 청크 비율이 MAX_KEYWORD_DF_RATIO를 넘으면 버림
            if keywords:
                counts_expr = ", ".join(["count(*) FILTER (WHERE content ILIKE %s)"] * len(keywords))
                cur.execute(
                    f"SELECT {counts_expr}, count(*) FROM code_embeddings WHERE project_id = %s",
                    ([f"%{kw}%" for kw in keywords] + [project_id]),
                )
                *df_counts, total = cur.fetchone()
                plain_keywords = [
                    kw for kw, df in zip(keywords, df_counts)
                    if total > 0 and df / total <= MAX_KEYWORD_DF_RATIO
                ]
            else:
                plain_keywords = []

            # 3) 키워드 검색: 식별자가 글자 그대로 들어 있는 청크.
            #    - 일반 매칭(ILIKE): df 필터를 통과한 키워드만. LIKE의 '_'는 아무 글자 1개와
            #      매칭되지만(follow_redirects → followXredirects도 매칭) 진짜 매칭도 항상
            #      잡히므로 recall 손실은 없다.
            #    - 정의 매칭(class X / def X, 대소문자 구분): 모든 키워드 대상, 가중치 3배.
            #      'Headers'처럼 너무 흔해서 df 필터에 버려진 키워드도 정의 청크는 희소해서
            #      "어디에 정의돼 있어?" 질문의 정답을 정확히 끌어올린다.
            # ponytail: ILIKE 전체 스캔 — 프로젝트당 수천 청크라 ms 단위. 수만 청크가 되면 pg_trgm 인덱스 추가.
            keyword_rows = []
            plain_patterns = [f"%{kw}%" for kw in plain_keywords]
            def_patterns = [p for kw in keywords for p in (f"%class {kw}%", f"%def {kw}%")]
            if plain_patterns or def_patterns:
                hits_expr = " + ".join(
                    ["(content ILIKE %s)::int"] * len(plain_patterns)
                    + ["3 * (content LIKE %s)::int"] * len(def_patterns)
                )
                like_clauses = " OR ".join(
                    ["content ILIKE %s"] * len(plain_patterns)
                    + ["content LIKE %s"] * len(def_patterns)
                )
                cur.execute(
                    f"""
                    SELECT content, metadata,
                           1 - (embedding <=> %s::vector) AS score,
                           {hits_expr} AS hits
                    FROM code_embeddings
                    WHERE project_id = %s
                      AND (%s OR COALESCE((metadata->>'is_test')::boolean, false) = false)
                      AND ({like_clauses})
                    ORDER BY hits DESC, score DESC
                    LIMIT %s
                    """,
                    (
                        query_vector, *plain_patterns, *def_patterns,
                        project_id, include_tests, *plain_patterns, *def_patterns,
                        CANDIDATE_K,
                    ),
                )
                keyword_rows = cur.fetchall()

    return _rrf_merge([vector_rows, keyword_rows], top_k)