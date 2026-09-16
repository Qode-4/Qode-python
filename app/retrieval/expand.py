# expand.py - 심볼 한 홉 확장
# 리랭크가 고른 청크 본문에 등장하는 함수·클래스 이름으로, 그 이름을 *정의하는* 청크를 한 홉 더 붙인다.
# "get()이 응답을 받기까지 절차" 같은 질문은 정답이 호출 체인 여러 파일에 흩어져 있는데,
# 유사도 검색은 첫 페이지만 집고 거기서 부르는 send()·build_request() 정의는 가져오지 않았다
# (2026-09-16 4W 측정: How·Where 0.5점 17문항의 사유가 "핵심 절차 일부 누락").
# 심볼 이름은 AST 청킹(ADR-020)이 metadata.symbol_name 에 붙여 둔 것을 쓴다 — 재인덕싱 없이 동작한다.
import re

from langchain_core.documents import Document

from .searcher import get_connection

# `self.이름(` 만 따라간다 — 같은 객체의 메서드 호출, 즉 호출 체인의 다음 단계.
# 1차 시도(괄호 뒤따르는 모든 이름, 상위 3청크, 상한 5)는 join·read·URL(·ByteStream( 같은 범용 이름의 정의를
# 끌어와 4W 종합 76.2 → 73.1% 로 내렸다 (2026-09-16 3회차). Why 문항은 코드 맥락이 늘수록 설계 의도에서 멀어졌다.
CALL_PATTERN = re.compile(r"\bself\.([A-Za-z_][A-Za-z0-9_]{2,})\s*\(")

# 절차·위치를 묻는 질문에만 켠다. ponytail: 한국어 키워드 휴리스틱 — Why·What 에는 확장이 손해라는 3회차 실측이 근거.
PROCEDURE_QUERY = re.compile(r"절차|흐름|과정|순서|단계|어디|호출|전달|경로")

MAX_EXPANDED = 3
SOURCE_TOP_N = 2


def _fetch_definitions(project_id: str, names: list[str], include_tests: bool) -> list[tuple]:
    # (content, metadata) — 이 프로젝트에서 names 중 하나를 정의하는 청크
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT content, metadata
                FROM code_embeddings
                WHERE project_id = %s
                  AND metadata->>'symbol_name' = ANY(%s)
                  AND (%s OR COALESCE((metadata->>'is_test')::boolean, false) = false)
                """,
                (project_id, names, include_tests),
            )
            return cur.fetchall()


def _chunk_key(meta: dict) -> tuple:
    return (meta.get("source"), meta.get("start_line"))


def expand_symbols(docs: list[Document], project_id: str, include_tests: bool, query: str, limit: int = MAX_EXPANDED) -> list[Document]:
    if not docs or limit <= 0 or not PROCEDURE_QUERY.search(query):
        return docs

    present = {_chunk_key(d.metadata) for d in docs}
    known_symbols = {d.metadata.get("symbol_name") for d in docs}

    # 리랭크 상위 SOURCE_TOP_N 개에서, 본문 등장 순서대로 이름을 모은다 — 앞에 있을수록 우선
    wanted: dict[str, str] = {}   # name → 처음 호출한 청크의 source
    for d in docs[:SOURCE_TOP_N]:
        for name in CALL_PATTERN.findall(d.page_content):
            if name.startswith("__") or name in known_symbols or name in wanted:
                continue   # 던더(__init__ 은 클래스마다 있다)·이미 결과에 있는 정의·중복은 건너뛴다
            wanted[name] = d.metadata.get("source")
    if not wanted:
        return docs

    by_name: dict[str, list[tuple]] = {}
    for content, meta in _fetch_definitions(project_id, list(wanted), include_tests):
        by_name.setdefault(meta.get("symbol_name"), []).append((content, meta))

    expanded: list[Document] = []
    for name, mentioned_in in wanted.items():
        if len(expanded) >= limit:
            break
        # 이름 하나에 정의 청크 하나만, 그리고 *같은 파일* 것만 — self.send() 의 send 는 그 클래스가 있는 파일에 있다.
        # 큰 클래스가 여러 조각으로 잘린 경우·Client/AsyncClient 에 같은 이름이 있는 경우 첫 조각만 붙인다
        candidates = sorted(
            (c for c in by_name.get(name, []) if c[1].get("source") == mentioned_in and _chunk_key(c[1]) not in present),
            key=lambda c: c[1].get("start_line") or 0,
        )
        if not candidates:
            continue
        content, meta = candidates[0]
        present.add(_chunk_key(meta))
        expanded.append(Document(
            page_content=content,
            # score 는 코사인이 아니라 0 — 확장 청크는 유사도로 뽑힌 것이 아니다. Node 계약(score: number)은 지킨다
            metadata={**meta, "score": 0.0, "expanded_from": mentioned_in},
        ))
    return docs + expanded
