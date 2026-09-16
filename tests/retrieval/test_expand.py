# 심볼 한 홉 확장 — 리랭크 결과 본문이 부르는 함수의 정의 청크를 뒤에 붙인다
from langchain_core.documents import Document

import app.retrieval.expand as expand_module
from app.retrieval.expand import expand_symbols


def doc(content, source, start, symbol=None, score=0.5):
    return Document(page_content=content, metadata={"source": source, "start_line": start, "symbol_name": symbol, "score": score})


# DB 흉내: 이 프로젝트가 정의하는 심볼들
DEFINITIONS = {
    "send": ("def send(self, request):\n    return self._send_handling_auth(request)", {"source": "_client.py", "start_line": 900, "symbol_name": "send"}),
    "build_request": ("def build_request(self, method, url):\n    ...", {"source": "_client.py", "start_line": 300, "symbol_name": "build_request"}),
    "get": ("def get(self, url):\n    return self.request('GET', url)", {"source": "_client.py", "start_line": 1000, "symbol_name": "get"}),
    "__init__": ("def __init__(self):\n    pass", {"source": "_models.py", "start_line": 10, "symbol_name": "__init__"}),
    "helper": ("def helper():\n    pass", {"source": "_utils.py", "start_line": 5, "symbol_name": "helper"}),
    "other": ("def other():\n    pass", {"source": "_utils.py", "start_line": 50, "symbol_name": "other"}),
}


def fake_fetch(project_id, names, include_tests):
    return [DEFINITIONS[n] for n in names if n in DEFINITIONS]


def test_appends_definitions_mentioned_in_results(monkeypatch):
    monkeypatch.setattr(expand_module, "_fetch_definitions", fake_fetch)
    top = doc("def request(self, method, url):\n    request = self.build_request(method, url)\n    return self.send(request)", "_client.py", 500, "request")

    result = expand_symbols([top], "p", include_tests=False)

    assert [d.metadata["symbol_name"] for d in result] == ["request", "build_request", "send"], "본문 등장 순서대로 뒤에 붙는다"
    assert result[1].metadata["expanded_from"] == "_client.py"
    assert result[1].metadata["score"] == 0.0


def test_skips_already_present_and_dunder(monkeypatch):
    monkeypatch.setattr(expand_module, "_fetch_definitions", fake_fetch)
    top = doc("class Client:\n    def __init__(self):\n        self.get(url)\n        self.send(1)", "_client.py", 100, "Client")
    already = doc("def get(self, url):\n    return self.request('GET', url)", "_client.py", 1000, "get")

    result = expand_symbols([top, already], "p", include_tests=False)

    names = [d.metadata["symbol_name"] for d in result]
    assert names.count("get") == 1, "이미 결과에 있는 정의는 다시 붙이지 않는다"
    assert "__init__" not in names[2:], "던더는 클래스마다 있어 잡음이다"
    assert names[2:] == ["send"]


def test_respects_limit(monkeypatch):
    monkeypatch.setattr(expand_module, "_fetch_definitions", fake_fetch)
    top = doc("send(); build_request(); get(); helper(); other()", "a.py", 1, "main")

    result = expand_symbols([top], "p", include_tests=False, limit=2)

    assert len(result) == 3
    assert [d.metadata["symbol_name"] for d in result[1:]] == ["send", "build_request"], "리랭크 상위 청크에서 먼저 나온 이름부터"


def test_no_mentions_returns_input(monkeypatch):
    monkeypatch.setattr(expand_module, "_fetch_definitions", lambda *a: (_ for _ in ()).throw(AssertionError("DB 를 부르면 안 된다")))
    top = doc("x = 1", "a.py", 1, "main")
    assert expand_symbols([top], "p", include_tests=False) == [top]


def test_only_called_names_not_type_annotations(monkeypatch):
    calls = []
    def fetch(project_id, names, include_tests):
        calls.append(sorted(names)); return fake_fetch(project_id, names, include_tests)
    monkeypatch.setattr(expand_module, "_fetch_definitions", fetch)
    top = doc("def get(url: URL | str, params: helper = None):\n    return send(url)", "_api.py", 1, "get")

    result = expand_symbols([top], "p", include_tests=False)

    assert calls == [["send"]], "타입 표기에 나온 URL·helper 는 따라가지 않는다"
    assert [d.metadata["symbol_name"] for d in result[1:]] == ["send"]


def test_one_chunk_per_name_prefers_same_file(monkeypatch):
    def fetch(project_id, names, include_tests):
        return [
            ("part 1", {"source": "_urls.py", "start_line": 15, "symbol_name": "URL"}),
            ("part 2", {"source": "_urls.py", "start_line": 42, "symbol_name": "URL"}),
            ("same file", {"source": "_api.py", "start_line": 300, "symbol_name": "URL"}),
        ]
    monkeypatch.setattr(expand_module, "_fetch_definitions", fetch)
    top = doc("u = URL(raw)", "_api.py", 1, "get")

    result = expand_symbols([top], "p", include_tests=False)

    assert len(result) == 2, "같은 이름의 조각 여러 개 중 하나만 붙인다"
    assert result[1].page_content == "same file", "같은 파일의 정의를 우선한다"


def test_names_only_from_top_ranked_chunks(monkeypatch):
    monkeypatch.setattr(expand_module, "_fetch_definitions", fake_fetch)
    top3 = [doc(f"x{i} = 1", "a.py", i, f"f{i}") for i in range(3)]
    low = doc("helper(); other()", "z.py", 99, "cli")

    result = expand_symbols(top3 + [low], "p", include_tests=False)

    assert len(result) == 4, "4위 이하 청크가 부르는 이름은 따라가지 않는다"
