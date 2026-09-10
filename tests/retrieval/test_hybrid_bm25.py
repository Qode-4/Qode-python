from rank_bm25 import BM25Okapi

from app.retrieval.searcher import tokenize, _rrf_merge, _apply_def_boost


def make_row(content, source="a.py", start_line=1, score=0.5):
    return (content, {"source": source, "start_line": start_line}, score)


def test_tokenize_korean_question_keeps_identifiers():
    assert tokenize("httpx에서 follow_redirects 기본값은?") == ["httpx", "follow_redirects"]


def test_tokenize_lowercases():
    assert tokenize("HTTPClient.send()") == ["httpclient", "send"]


def test_bm25_rare_token_beats_common_token():
    # 희귀 식별자(follow_redirects)가 매칭된 문서가
    # 흔한 단어(client)만 잔뜩 매칭된 문서보다 위여야 한다 — IDF 검증
    docs = [
        "def request(client): pass",
        "client = Client(); client.get(); client.post()",
        "def build(follow_redirects=True, client=None): pass",
    ]
    bm25 = BM25Okapi([tokenize(d) for d in docs])
    scores = bm25.get_scores(tokenize("client의 follow_redirects 기본값은?"))
    assert scores.argmax() == 2


def test_rrf_both_lists_wins():
    # 양쪽에 다 나온 청크가 한쪽 1등보다 위로 온다
    both = make_row("both", "b.py", 10)
    vector = [make_row("vec-top", "v.py", 1), both]
    bm25 = [both, make_row("bm-top", "k.py", 2)]
    merged = _rrf_merge([vector, bm25], top_k=3)
    assert merged[0].page_content == "both"
    assert len(merged) == 3


def test_rrf_keeps_cosine_score_in_metadata():
    # RRF 점수가 아니라 코사인 유사도가 score에 남아야 filter.py 계약이 유지된다
    merged = _rrf_merge([[make_row("only", score=0.42)], []], top_k=5)
    assert merged[0].metadata["score"] == 0.42


def test_def_boost_lifts_definition_chunk():
    # 흔한 토큰(headers) 반복으로 사용처 청크가 더 높게 나온 상황에서
    # 정의 청크(class Headers)가 위로 올라와야 한다
    contents = [
        "headers = client.headers; print(headers, headers)",
        "class Headers:\n    def __init__(self): ...",
    ]
    scores = [2.0, 0.5]
    _apply_def_boost(scores, contents, "Headers 자료구조는 어떻게 생겼어?")
    assert scores[1] > scores[0]


def test_def_boost_noop_without_identifiers():
    scores = [1.0, 2.0]
    _apply_def_boost(scores, ["class ABC: pass", "x = 1"], "이 프로젝트 구조 설명해줘")
    assert scores == [1.0, 2.0]


def test_def_boost_is_case_sensitive():
    # 'classify headers'는 'class Headers' 정의가 아니다
    scores = [1.0]
    _apply_def_boost(scores, ["classify headers here"], "Headers 어디에 정의돼 있어?")
    assert scores == [1.0]


def test_rrf_empty_bm25_list():
    # 식별자 없는 한국어 질문 → BM25 빈손이어도 벡터 결과만으로 동작
    rows = [make_row("v1", "a.py", 1), make_row("v2", "a.py", 20)]
    merged = _rrf_merge([rows, []], top_k=5)
    assert [d.page_content for d in merged] == ["v1", "v2"]
