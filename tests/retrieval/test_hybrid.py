from app.retrieval.searcher import extract_keywords, _rrf_merge


def make_row(content, source="a.py", start_line=1, score=0.5):
    return (content, {"source": source, "start_line": start_line}, score)


def test_extract_keywords_korean_question():
    kws = extract_keywords("httpx에서 재시도(retries)를 설정하는 방법은?")
    assert kws == ["httpx", "retries"]


def test_extract_keywords_underscore_and_dedup():
    kws = extract_keywords("follow_redirects 기본값은? follow_redirects 말이야")
    assert kws == ["follow_redirects"]


def test_extract_keywords_short_tokens_dropped():
    assert extract_keywords("L1 은 is 뭐야?") == []


def test_rrf_both_lists_wins():
    # 양쪽에 다 나온 청크가 한쪽 1등보다 위로 온다
    both = make_row("both", "b.py", 10)
    vector = [make_row("vec-top", "v.py", 1), both]
    keyword = [both, make_row("kw-top", "k.py", 2)]
    merged = _rrf_merge([vector, keyword], top_k=3)
    assert merged[0].page_content == "both"
    assert len(merged) == 3


def test_rrf_keeps_cosine_score_in_metadata():
    # RRF 점수가 아니라 코사인 유사도가 score에 남아야 filter.py 계약이 유지된다
    merged = _rrf_merge([[make_row("only", score=0.42)], []], top_k=5)
    assert merged[0].metadata["score"] == 0.42


def test_rrf_respects_top_k():
    rows = [make_row(f"c{i}", "a.py", i) for i in range(10)]
    assert len(_rrf_merge([rows, []], top_k=5)) == 5


def test_rrf_empty_keyword_list():
    # 식별자 없는 질문 → 키워드 결과 빈손이어도 벡터 결과만으로 동작
    rows = [make_row("v1", "a.py", 1), make_row("v2", "a.py", 20)]
    merged = _rrf_merge([rows, []], top_k=5)
    assert [d.page_content for d in merged] == ["v1", "v2"]
