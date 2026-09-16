# ADR-020 · 열린 과제 13-21 — 코드는 tree-sitter AST 로 함수·클래스 단위로 자른다
from langchain_core.documents import Document

from app.parsing.splitter import split_documents


def code_doc(text, language, extension):
    return Document(page_content=text, metadata={"language": language, "extension": extension, "project_id": "p1", "source": f"f{extension}"})


def assert_covers_and_lines_match(src, chunks):
    lines = src.split("\n")
    for line in lines:
        if line.strip():
            assert any(line.rstrip() in c.page_content for c in chunks), f"사라진 줄: {line!r}"
    for c in chunks:
        start, end = c.metadata["start_line"], c.metadata["end_line"]
        first, last = c.page_content.split("\n")[0], c.page_content.split("\n")[-1]
        assert lines[start - 1].strip() == first.strip(), (start, first)
        assert lines[end - 1].strip() == last.strip(), (end, last)


def whole_in_one_chunk(chunks, text):
    owners = [c for c in chunks if text in c.page_content]
    assert len(owners) == 1, f"{text[:30]!r} 가 {len(owners)}개 청크에 있다"
    return owners[0]


BIG_BODY = "\n".join(f"    value_{i} = compute_something(value_{i - 1}, factor={i})" for i in range(1, 12))
METHOD_BODY = BIG_BODY.replace("\n    ", "\n        ").replace("    value_1 ", "        value_1 ", 1)
PY_SRC = f'''import os
from typing import Any

DEFAULT_TIMEOUT = 5.0


def tiny(x):
    return x


def big_function(arg: int) -> int:
    """긴 함수 — 문자 기준이면 한가운데가 잘렸다"""
    value_0 = arg
{BIG_BODY}
    return value_11


class Client:
    """클래스는 chunk_size 를 넘으므로 메서드 단위로 내려간다"""

    def __init__(self, base_url: str):
        self.base_url = base_url

    def request(self, method: str, path: str) -> dict:
        url = self.base_url + path
{METHOD_BODY}
        return {{"method": method, "url": url}}

    def close(self):
        pass
'''


def test_python_functions_are_not_cut_in_the_middle():
    chunks = split_documents([code_doc(PY_SRC, "python", ".py")], chunk_size=900)

    assert_covers_and_lines_match(PY_SRC, chunks)
    for c in chunks:
        assert len(c.page_content) <= 900

    big = whole_in_one_chunk(chunks, "def big_function(arg: int) -> int:\n" + '    """긴 함수')
    assert big.metadata["symbol_name"] == "big_function"
    assert big.metadata["symbol_kind"] == "function_definition"
    assert big.metadata["start_line"] == PY_SRC.split("\n").index("def big_function(arg: int) -> int:") + 1
    assert "return value_11" in big.page_content

    request = whole_in_one_chunk(chunks, "def request(self, method: str, path: str) -> dict:")
    assert request.metadata["symbol_name"] == "request"
    assert 'return {"method": method, "url": url}' in request.page_content

    # 작은 것(import·상수·한 줄 함수)은 홀로 서지 않고 이웃과 합쳐져 50자 하한에 안 걸린다
    consts = whole_in_one_chunk(chunks, "DEFAULT_TIMEOUT = 5.0")
    assert "import os" in consts.page_content
    assert all(len(c.page_content) >= 50 for c in chunks)


def test_oversized_function_splits_on_lines_and_keeps_symbol():
    body = "\n".join(f"    step_{i} = run_step_number({i}, previous=step_{i - 1})" for i in range(1, 60))
    src = f"def huge(step_0):\n{body}\n    return step_59\n"
    chunks = split_documents([code_doc(src, "python", ".py")], chunk_size=500)

    assert len(chunks) > 1
    assert_covers_and_lines_match(src, chunks)
    assert {c.metadata["symbol_name"] for c in chunks} == {"huge"}
    src_lines = src.split("\n")
    for c in chunks:
        for line in c.page_content.split("\n"):
            assert line in src_lines, f"줄 중간에서 잘렸다: {line!r}"


TS_SRC = '''import { useEffect, useState } from "react";

export const CONFIG = { retries: 3, timeoutMs: 5000 };

export const useThing = (id: string) => {
  const [state, setState] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetchThing(id).then((value) => {
      if (!cancelled) setState(value);
    });
    return () => {
      cancelled = true;
    };
  }, [id]);
  return state;
};

export default function Page({ id }: { id: string }) {
  const thing = useThing(id);
  return <section className="page"><h1>{thing ?? "loading"}</h1></section>;
}
'''


def test_tsx_arrow_components_get_symbol_names():
    chunks = split_documents([code_doc(TS_SRC, "typescript", ".tsx")], chunk_size=400)

    assert_covers_and_lines_match(TS_SRC, chunks)
    hook = whole_in_one_chunk(chunks, "export const useThing = (id: string) => {")
    assert hook.metadata["symbol_name"] == "useThing"
    page = whole_in_one_chunk(chunks, "export default function Page")
    assert page.metadata["symbol_name"] == "Page"
    # 상수는 정의로 세우지 않는다 — 홀로 서면 50자 하한에 걸려 사라진다
    assert whole_in_one_chunk(chunks, "export const CONFIG").metadata["symbol_name"] != "CONFIG"


def test_unknown_language_falls_back_to_character_splitter():
    src = "\n".join(f"key_{i}: value_{i}" for i in range(80))
    chunks = split_documents([code_doc(src, "yaml", ".yml")], chunk_size=200, chunk_overlap=0)
    assert len(chunks) > 1
    assert "symbol_name" not in chunks[0].metadata
    assert chunks[0].metadata["start_line"] == 1
