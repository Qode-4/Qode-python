# 심볼 한 홉 확장(좁힌 규칙) — 절차·위치 질문에서, 상위 청크가 self.로 부르는 메서드의 같은 파일 정의만 뒤에 붙인다
from langchain_core.documents import Document

import app.retrieval.expand as expand_module
from app.retrieval.expand import expand_symbols

Q = "get() 호출 후 응답까지 절차를 알려줘"


def doc(content, source, start, symbol=None, score=0.5):
    return Document(page_content=content, metadata={"source": source, "start_line": start, "symbol_name": symbol, "score": score})


DEFINITIONS = {
    "send": [("def send(self, request):\n    ...", {"source": "_client.py", "start_line": 900, "symbol_name": "send"}),
             ("async def send(self, request):\n    ...", {"source": "_async.py", "start_line": 900, "symbol_name": "send"})],
    "build_request": [("def build_request(self, method, url):\n    ...", {"source": "_client.py", "start_line": 300, "symbol_name": "build_request"})],
    "get": [("def get(self, url):\n    ...", {"source": "_client.py", "start_line": 1000, "symbol_name": "get"})],
    "__init__": [("def __init__(self):\n    pass", {"source": "_client.py", "start_line": 10, "symbol_name": "__init__"})],
    "join": [("def join(self, url):\n    ...", {"source": "_urls.py", "start_line": 354, "symbol_name": "join"})],
    "URL": [("class URL:\n    ...", {"source": "_urls.py", "start_line": 15, "symbol_name": "URL"})],
    "helper": [("def helper(self):\n    pass", {"source": "a.py", "start_line": 5, "symbol_name": "helper"})],
    "other": [("def other(self):\n    pass", {"source": "a.py", "start_line": 50, "symbol_name": "other"})],
    "third": [("def third(self):\n    pass", {"source": "a.py", "start_line": 70, "symbol_name": "third"})],
    "fourth": [("def fourth(self):\n    pass", {"source": "a.py", "start_line": 90, "symbol_name": "fourth"})],
}


def fake_fetch(project_id, names, include_tests):
    return [row for n in names for row in DEFINITIONS.get(n, [])]


def test_follows_self_method_calls_in_same_file(monkeypatch):
    monkeypatch.setattr(expand_module, "_fetch_definitions", fake_fetch)
    top = doc("def request(self, method, url):\n    request = self.build_request(method, url)\n    return self.send(request)", "_client.py", 500, "request")

    result = expand_symbols([top], "p", include_tests=False, query=Q)

    assert [d.metadata["symbol_name"] for d in result] == ["request", "build_request", "send"], "self. 호출 순서대로 뒤에 붙는다"
    assert all(d.metadata["source"] == "_client.py" for d in result), "다른 파일(_async.py)의 send 는 붙이지 않는다"
    assert result[1].metadata["expanded_from"] == "_client.py"
    assert result[1].metadata["score"] == 0.0


def test_ignores_free_calls_and_constructors(monkeypatch):
    monkeypatch.setattr(expand_module, "_fetch_definitions", fake_fetch)
    top = doc("def get(self, url):\n    u = URL(url).join(url)\n    return join(u)", "_urls.py", 1, "get")

    result = expand_symbols([top], "p", include_tests=False, query=Q)

    assert len(result) == 1, "self. 가 붙지 않은 호출(URL(·join()은 따라가지 않는다 — 3회차에서 잡음의 주범"


def test_skips_present_and_dunder(monkeypatch):
    monkeypatch.setattr(expand_module, "_fetch_definitions", fake_fetch)
    top = doc("class Client:\n    def __init__(self):\n        self.__init__()\n        self.get(url)\n        self.send(1)", "_client.py", 100, "Client")
    already = doc("def get(self, url):\n    ...", "_client.py", 1000, "get")

    result = expand_symbols([top, already], "p", include_tests=False, query=Q)

    names = [d.metadata["symbol_name"] for d in result]
    assert names == ["Client", "get", "send"], "이미 있는 get·던더 __init__ 은 건너뛰고 send 만 붙는다"


def test_limit_and_top_n_sources(monkeypatch):
    monkeypatch.setattr(expand_module, "_fetch_definitions", fake_fetch)
    top1 = doc("self.helper(); self.other()", "a.py", 1, "f1")
    top2 = doc("self.third(); self.fourth()", "a.py", 2, "f2")
    low = doc("self.send()", "_client.py", 3, "f3")

    result = expand_symbols([top1, top2, low], "p", include_tests=False, query=Q)

    assert [d.metadata["symbol_name"] for d in result[3:]] == ["helper", "other", "third"], "상한 3개, 3위 이하 청크의 호출은 무시"


def test_only_for_procedure_or_location_questions(monkeypatch):
    monkeypatch.setattr(expand_module, "_fetch_definitions", lambda *a: (_ for _ in ()).throw(AssertionError("DB 를 부르면 안 된다")))
    top = doc("return self.send(request)", "_client.py", 1, "request")

    for q in ["왜 리다이렉트를 기본으로 따라가지 않게 설계했지?", "follow_redirects 기본값은?"]:
        assert expand_symbols([top], "p", include_tests=False, query=q) == [top], "Why·What 질문에는 확장을 켜지 않는다"
