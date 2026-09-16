# expand.py - 심볼 한 홉 확장
# 리랭크가 고른 청크 본문에 등장하는 함수·클래스 이름으로, 그 이름을 *정의하는* 청크를 한 홉 더 붙인다.
# "get()이 응답을 받기까지 절차" 같은 질문은 정답이 호출 체인 여러 파일에 흩어져 있는데,
# 유사도 검색은 첫 페이지만 집고 거기서 부르는 send()·build_request() 정의는 가져오지 않았다
# (2026-09-16 4W 측정: How·Where 0.5점 17문항의 사유가 "핵심 절차 일부 누락").
# 심볼 이름은 AST 청킹(ADR-020)이 metadata.symbol_name 에 붙여 둔 것을 쓴다 — 재인덕싱 없이 동작한다.
import re

from langchain_core.documents import Document

from .searcher import get_connection

# 뒤에 괄호가 오는 이름만 따라간다 — 실제로 *호출된* 함수·생성된 클래스.
# 타입 표기(`url: URL | str`)·속성 이름까지 따라가면 첫 청크의 시그니처에 있는 URL 클래스 조각이 자리를 다 차지했다 (2026-09-16 실측).
CALL_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\s*\(")

# 붙이는 상한. 흔한 이름(get·read·close)이 많아 한도가 없으면 수십 개가 따라온다.
# ponytail: 상한·우선순위(리랭크 상위 청크의 이름부터)만으로 잡음을 막는다. What 이 내려가면 3으로 줄인다.
MAX_EXPANDED = 5
# 이름을 캐는 출발 청크는 리랭크 상위 몇 개까지만. 10위권 청크(CLI·다른 모듈)의 호출까지 따라가면
# aclose·iter_bytes 같은 무관한 정의가 자리를 채웠다 (2026-09-16 실측).
SOURCE_TOP_N = 3


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


def expand_symbols(docs: list[Document], project_id: str, include_tests: bool, limit: int = MAX_EXPANDED) -> list[Document]:
    if not docs or limit <= 0:
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
        # 이름 하나에 정의 청크 하나만 — 같은 파일 것을 우선하고(Client.get 이 부른 send 는 같은 파일의 send),
        # 큰 클래스가 여러 조각으로 잘린 경우·Client/AsyncClient 에 같은 이름이 있는 경우 첫 조각만 붙인다
        candidates = sorted(
            (c for c in by_name.get(name, []) if _chunk_key(c[1]) not in present),
            key=lambda c: (c[1].get("source") != mentioned_in, c[1].get("source") or "", c[1].get("start_line") or 0),
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
