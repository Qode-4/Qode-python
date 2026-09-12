from langchain_core.documents import Document

import app.parsing.splitter as splitter_module
from app.parsing.splitter import split_documents


def make_doc(text, language="python"):
    return Document(page_content=text, metadata={"language": language, "project_id": "p1"})


def test_start_line_matches_real_position():
    # 각 청크의 start_line이 원본에서 실제로 그 줄이어야 한다
    src = "\n".join(f"line_{i} = {i}" for i in range(1, 201))
    chunks = split_documents([make_doc(src)], chunk_size=200, chunk_overlap=50)

    lines = src.split("\n")
    for chunk in chunks:
        start = chunk.metadata["start_line"]
        assert start is not None
        first_line_of_chunk = chunk.page_content.split("\n")[0]
        assert lines[start - 1] == first_line_of_chunk


def test_line_numbers_are_never_reused_from_previous_chunk():
    # 열린 과제 13-13 — pos를 못 찾으면 이전 청크의 start_line을 그대로 인용했다
    src = "\n".join(f"def f{i}():\n    return {i}" for i in range(1, 120))
    chunks = split_documents([make_doc(src)], chunk_size=150, chunk_overlap=30)

    starts = [c.metadata["start_line"] for c in chunks if c.metadata["start_line"] is not None]
    assert starts == sorted(starts), "줄 번호가 뒤로 가면 이전 청크 값을 물려받은 것이다"
    assert len(set(starts)) == len(starts), "서로 다른 청크가 같은 줄을 가리킨다"


class _UnlocatableSplitter:
    """원문에 없는 텍스트를 청크로 내놓는 가짜 분할기.

    현재 RecursiveCharacterTextSplitter로는 find 실패가 재현되지 않아
    (실제 레포 400파일·3,610청크에서 0건) 분기를 직접 태운다.
    """

    def split_documents(self, docs):
        return [
            Document(page_content="원문에 없는 텍스트", metadata=dict(docs[0].metadata)),
            Document(page_content=docs[0].page_content[:20], metadata=dict(docs[0].metadata)),
        ]


def test_unlocatable_chunk_has_no_line_range(monkeypatch):
    # 열린 과제 13-13 — 원문에서 못 찾으면 옛 코드는 start_line을 정하지 않았다.
    # 첫 청크면 NameError, 이후 청크면 이전 청크의 줄 번호를 그대로 인용한다.
    monkeypatch.setattr(
        splitter_module, "_build_language_splitter", lambda *_: {"python": _UnlocatableSplitter()}
    )
    chunks = split_documents([make_doc("a = 1\nb = 2\nc = 3\n")], chunk_size=100, chunk_overlap=20)

    # 못 찾은 청크는 줄 범위를 비운다 — 틀린 줄을 붙이지 않는다
    assert chunks[0].metadata["start_line"] is None
    assert chunks[0].metadata["end_line"] is None
    # 뒤 청크는 정상적으로 자기 줄을 찾는다 (앞 청크 실패에 오염되지 않는다)
    assert chunks[1].metadata["start_line"] == 1
