import re

from langchain_core.documents import Document

from app.parsing.splitter import split_documents

FENCE_LINE = re.compile(r"^```", re.MULTILINE)


def md_doc(text):
    return Document(page_content=text, metadata={"language": "markdown", "project_id": "p1", "source": "README.md"})


def test_code_fence_stays_in_one_chunk():
    # 열린 과제 13-1 — 기본 마크다운 분할 규칙은 닫는 ``` 앞에서 자른다.
    # 코드블록은 A 청크에, 닫는 ``` 는 B 청크 첫 줄에 놓여 B를 마크다운으로
    # 읽으면 그 아래가 전부 코드블록으로 먹힌다("백틱 뒤가 잘린다").
    # 또 '\n# ' 헤딩 규칙이 코드블록 안의 파이썬 주석에도 걸려 블록 한가운데를 자른다.
    sections = []
    for i in range(12):
        sections.append(
            f"## Step {i}\n\n설명 문장 {i}.\n\n"
            f"```python\n# 주석 {i}\nvalue_{i} = compute({i})\nprint(value_{i})\n```\n\n"
            f"펜스 뒤 문장 {i}은 살아야 한다.\n"
        )
    src = "\n".join(sections)

    chunks = split_documents([md_doc(src)], chunk_size=300, chunk_overlap=0)

    for c in chunks:
        text = c.page_content
        assert not text.startswith("```\n"), f"닫는 펜스가 청크 첫 줄에 떨어졌다: {text[:40]!r}"
        assert len(FENCE_LINE.findall(text)) % 2 == 0, f"펜스가 짝이 안 맞는다: {text[:60]!r}"
        assert not text.startswith("# 주석"), "코드블록 안 주석을 헤딩으로 보고 잘랐다"

    # 텍스트 손실 없음 + 줄 번호 정확
    lines = src.split("\n")
    for line in lines:
        if line.strip():
            assert any(line in c.page_content for c in chunks), f"사라진 줄: {line!r}"
    for c in chunks:
        start = c.metadata["start_line"]
        assert start is not None
        assert lines[start - 1].startswith(c.page_content.split("\n")[0])


def test_oversized_code_block_is_split_on_lines_only():
    # chunk_size를 넘는 코드블록은 어쩔 수 없이 잘리지만, 줄 중간(공백)에서 자르지는 않는다
    body = "\n".join(f"item_{i} = load_something_reasonably_long({i})" for i in range(40))
    src = f"# Big\n\n```python\n{body}\n```\n"
    chunks = split_documents([md_doc(src)], chunk_size=300, chunk_overlap=0)
    assert len(chunks) > 1
    for c in chunks:
        for line in c.page_content.split("\n"):
            assert line in src.split("\n"), f"줄 중간에서 잘렸다: {line!r}"
