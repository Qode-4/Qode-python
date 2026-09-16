import re
from functools import lru_cache

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from tree_sitter import Node, Parser
from tree_sitter_language_pack import get_parser

from app.parsing.filters import MIN_CHUNK_LENGTH

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200

# ===== 마크다운 (열린 과제 13-1) =====
# LangChain 기본 마크다운 규칙은 닫는 펜스 '```\n' 앞에서 자른다. 그러면 코드블록은 A 청크에,
# 닫는 ``` 는 B 청크 첫 줄에 놓여 B를 마크다운으로 읽으면 그 아래가 전부 코드블록으로 먹힌다.
# 게다가 '\n# ' 헤딩 규칙이 코드블록 안 주석에도 걸려 블록 한가운데를 자른다.
# 해법: 펜스 블록 안의 줄바꿈을 잠시 다른 문자로 바꿔 분할 규칙이 블록 안을 못 보게 하고,
# 자를 자리는 닫는 펜스가 아니라 *여는* 펜스 앞으로 옮긴다.
FENCED_BLOCK = re.compile(r"^```[^\n]*\n.*?^```[ \t]*$", re.MULTILINE | re.DOTALL)
_NL = "\x00"
_MARKDOWN_SEPARATORS = [
    r"\n#{1,6} ",      # 헤딩
    r"\n(?=```)",      # 여는 펜스 앞 (닫는 펜스 앞은 _NL 이라 안 걸린다)
    r"\n\*\*\*+\n", r"\n---+\n", r"\n___+\n",
    "\n\n", "\n",
    _NL + r"(?!```)",   # chunk_size 를 넘는 코드블록만 여기서 줄 단위로 잘린다. 닫는 펜스는 마지막 줄에 붙여 둔다
    " ", "",
]


def _build_markdown_splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap,
        separators=_MARKDOWN_SEPARATORS, is_separator_regex=True,
    )


def _split_markdown(text: str, splitter: RecursiveCharacterTextSplitter) -> list[str]:
    protected = FENCED_BLOCK.sub(lambda m: m.group(0).replace("\n", _NL), text)
    # 복원한 줄바꿈만 벗긴다 — strip() 이면 코드 첫 줄의 들여쓰기까지 사라진다
    return [c.replace(_NL, "\n").strip("\n") for c in splitter.split_text(protected)]


# ===== 코드: tree-sitter AST (ADR-020, 열린 과제 13-21) =====
# 문자 수 기준 분할은 함수 한가운데를 잘랐다. 여기서는 함수·클래스 정의 노드를 청크 하나로 세우고,
# chunk_size 를 넘는 노드만 자식 단위로 내려가 다시 자른다. 줄 번호는 파서가 주므로 역추적이 없다.

# loader 가 붙이는 language 값 → tree-sitter 문법 이름. .tsx 는 JSX 문법이 달라 따로 간다.
_GRAMMARS = {"python", "javascript", "typescript", "java", "go", "rust", "ruby"}

# 청크 하나로 세우는 정의 노드. 여기 없는 노드(import·상수·표현식)는 이웃과 합쳐진다.
_DEFINITION_TYPES = {
    "function_definition", "class_definition", "decorated_definition",                     # python
    "function_declaration", "class_declaration", "method_definition",                      # js/ts
    "interface_declaration", "type_alias_declaration", "enum_declaration", "abstract_class_declaration",
    "method_declaration", "constructor_declaration",                                       # java
    "type_declaration",                                                                    # go
    "function_item", "struct_item", "enum_item", "impl_item", "trait_item", "mod_item",    # rust
    "method", "singleton_method", "class", "module",                                       # ruby
}
# `const foo = () => {}` 는 lexical_declaration 이라 값이 함수·클래스일 때만 정의로 본다.
# 그냥 상수(`const X = 1`)까지 정의로 세우면 50자 미만 청크가 되어 filter_chunks 에서 사라진다.
_FUNCTION_VALUE_TYPES = {"arrow_function", "function_expression", "function", "class"}

# 이보다 작은 정의(한 줄짜리 getter 등)는 홀로 세우지 않고 이웃과 합친다.
# 홀로 세우면 filter_chunks 의 50자 하한에 걸려 통째로 사라지기 때문.
MIN_STANDALONE_DEFINITION = 200


@lru_cache(maxsize=None)
def _parser(grammar: str) -> Parser:
    return get_parser(grammar)


def _grammar_for(language: str, extension: str | None) -> str | None:
    if extension == ".tsx":
        return "tsx"
    return language if language in _GRAMMARS else None


def _is_definition(node: Node) -> bool:
    if node.type == "export_statement":
        decl = node.child_by_field_name("declaration")
        return decl is not None and _is_definition(decl)
    if node.type in ("lexical_declaration", "variable_declaration"):
        return any(
            (value := d.child_by_field_name("value")) is not None and value.type in _FUNCTION_VALUE_TYPES
            for d in node.named_children
        )
    return node.type in _DEFINITION_TYPES


def _symbol_name(node: Node) -> str | None:
    name = node.child_by_field_name("name")
    if name is not None:
        return name.text.decode()
    for field in ("declaration", "definition", "type"):   # export/decorated 래퍼, rust impl
        child = node.child_by_field_name(field)
        if child is not None:
            return child.text.decode() if child.named_child_count == 0 else _symbol_name(child)
    for child in node.named_children:                      # const foo = ..., go type_spec
        if child.type in ("variable_declarator", "type_spec"):
            return _symbol_name(child)
    return None


def _split_code_ast(doc: Document, grammar: str, chunk_size: int) -> list[Document]:
    src = doc.page_content.encode()
    tree = _parser(grammar).parse(src)
    spans: list[tuple] = []   # 청크 = (start_byte, end_byte, symbol)
    buf: list[tuple] = []     # 조각 = (start_byte, end_byte, symbol). 문서 순서대로, 빈틈 없이 이어진다.

    def text_len(start: int, end: int) -> int:
        return len(src[start:end].decode())

    def line_start(pos: int) -> int:
        # 조각이 들여쓰기 뒤에서 시작하면 줄 앞으로 당긴다 — 들여쓰기를 살리고, 줄 시작인지도 여기서 판정
        while pos > 0 and src[pos - 1] in b" \t":
            pos -= 1
        return pos

    def line_end(pos: int) -> int:
        nl = src.find(b"\n", pos)
        return len(src) if nl == -1 else nl

    def flush() -> None:
        nonlocal buf
        if not buf:
            return
        start, end = line_start(buf[0][0]), buf[-1][1]
        symbols = {p[2] for p in buf if p[2] is not None}
        buf = []
        if src[start:end].strip():
            spans.append((start, end, symbols.pop() if len(symbols) == 1 else None))   # 정의가 섞이면 이름 없음

    def to_document(start: int, end: int, symbol) -> Document:
        raw = src[start:end].decode()
        text = raw.strip("\n").rstrip()
        start_line = src[:start].count(b"\n") + 1 + (len(raw) - len(raw.lstrip("\n")))
        return Document(page_content=text, metadata={
            **doc.metadata,
            "start_line": start_line,
            "end_line": start_line + text.count("\n"),
            "symbol_name": symbol[0] if symbol else None,
            "symbol_kind": symbol[1] if symbol else None,
        })

    def add(start: int, end: int, symbol, standalone: bool = False) -> None:
        # 이웃 조각을 chunk_size 까지 붙인다. 자를 수 있는 자리는 줄 시작만이다 —
        # 한 줄 안의 조각들(이름·괄호·`} catch {`)은 넘치더라도 붙인다.
        nonlocal buf
        at_line_start = (ls := line_start(start)) == 0 or src[ls - 1:ls] == b"\n"
        # 줄 시작 조각은 그 줄 끝까지 들어온다고 보고 잰다 — 뒤따르는 같은 줄 조각은 자를 수 없으므로
        if buf and at_line_start and text_len(line_start(buf[0][0]), max(end, line_end(start))) > chunk_size:
            flush()
        # 홀로 설 정의: 앞의 자잘한 것(주석·import·`export ` 래퍼)만 앞에 붙인다 — 다른 이름의 정의와는 섞지 않는다
        if standalone and any(p[2] is not None and p[2][0] != symbol[0] for p in buf):
            flush()
        buf.append((start, end, symbol))
        if standalone:
            flush()

    def add_lines(start: int, end: int, symbol) -> None:
        # 자식이 없는 노드(문자열·배열 리터럴)가 버퍼에 안 들어가면 줄 단위로 나눈다.
        # ponytail: 한 줄이 chunk_size 를 넘으면(minified) 그대로 한 조각 — 코드 파일에선 드물다.
        for m in re.finditer(rb"[^\n]*\n?", src[start:end]):
            if m.end() > m.start():
                add(start + m.start(), start + m.end(), symbol)

    def walk(node: Node, owner) -> None:
        symbol = owner
        is_definition = _is_definition(node)
        if is_definition:
            symbol = (_symbol_name(node), node.type)
        length = text_len(node.start_byte, node.end_byte)
        fits_in_buf = not buf or text_len(line_start(buf[0][0]), node.end_byte) <= chunk_size
        # 통째로 들어가면 한 조각. 정의는 버퍼에 안 들어가도 통째로 — 잘리는 대신 새 청크로 선다.
        # 정의가 아닌 것(함수 본문 block·객체 리터럴)은 버퍼에 안 들어가면 자식으로 내려간다 —
        # 그래야 "def foo(...):" 헤더가 본문 첫 문장들과 한 청크에 남는다.
        if length <= chunk_size and (is_definition or fits_in_buf):
            add(node.start_byte, node.end_byte, symbol, standalone=is_definition and length >= MIN_STANDALONE_DEFINITION)
            return
        # chunk_size 를 넘는 정의는 앞뒤와 섞이지 않게 경계를 세우고 자식 단위로 내려간다.
        # 단 `export …`·`@decorator` 래퍼 안의 같은 이름 정의는 래퍼가 이미 세웠으므로 다시 세우지 않는다 —
        # 세우면 "export " 한 조각이나 데코레이터 줄만 따로 떨어져 나간다.
        boundary = is_definition and not (owner and owner[0] == symbol[0])
        if boundary:
            flush()
        if node.named_child_count == 0:
            add_lines(node.start_byte, node.end_byte, symbol)
        else:
            cursor = node.start_byte
            for child in node.named_children:
                if child.start_byte > cursor:      # 헤더("def foo(...):")·자식 사이 구두점·주석
                    add(cursor, child.start_byte, symbol)
                walk(child, symbol)
                cursor = child.end_byte
            if cursor < node.end_byte:
                add(cursor, node.end_byte, symbol)
        if boundary:
            flush()

    walk(tree.root_node, None)
    flush()

    # 끝에 남은 자투리(한 줄짜리 메서드, `if __name__` 블록)는 filter_chunks 의 하한에 걸려 사라지므로 앞 청크에 붙인다
    merged: list[tuple] = []
    for span in spans:
        if merged and text_len(span[0], span[1]) < MIN_CHUNK_LENGTH and text_len(merged[-1][0], span[1]) <= chunk_size:
            prev = merged.pop()
            span = (prev[0], span[1], prev[2])
        merged.append(span)
    return [to_document(*span) for span in merged]


# ===== 그 외 (yaml·json·sql·unknown): 문자 기준 =====

def _build_default_splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""],
    )


def _locate_lines(doc: Document, chunks: list[Document], chunk_overlap: int) -> None:
    # 문자 기준 분할기는 위치를 안 주므로 청크 앞 50글자로 원본에서 되찾는다
    search_start = 0
    for chunk in chunks:
        head = chunk.page_content[:50]
        pos = doc.page_content.find(head, search_start)
        if pos == -1:
            # 분할기가 앞뒤 공백을 정리하면 원문과 글자가 어긋나 못 찾는다.
            # 겹침 구간만큼 되돌려 재검색한다 (음수 시작은 문서 끝에서 찾게 되므로 0으로 자른다).
            pos = doc.page_content.find(head, max(0, search_start - chunk_overlap))
        if pos == -1:
            # 끝내 못 찾으면 줄 번호를 비운다. 틀린 줄을 근거로 인용하느니 표시하지 않는 쪽이 낫다.
            start_line = end_line = None
        else:
            start_line = doc.page_content[:pos].count("\n") + 1
            end_line = start_line + chunk.page_content.count("\n")
            search_start = pos + 1   # 다음 청크는 현재 위치 이후에서 찾기 (중복 매칭 방지)
        chunk.metadata.update({"start_line": start_line, "end_line": end_line})


def split_documents(docs: list[Document], chunk_size: int = DEFAULT_CHUNK_SIZE, chunk_overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[Document]:
    default_splitter = _build_default_splitter(chunk_size, chunk_overlap)
    markdown_splitter = _build_markdown_splitter(chunk_size, chunk_overlap)

    all_chunks: list[Document] = []

    for doc in docs:
        language = doc.metadata.get("language", "unknown")
        grammar = _grammar_for(language, doc.metadata.get("extension"))

        if language == "markdown":
            chunks = [
                Document(page_content=text, metadata=dict(doc.metadata))
                for text in _split_markdown(doc.page_content, markdown_splitter) if text
            ]
            _locate_lines(doc, chunks, chunk_overlap)
        elif grammar:
            chunks = _split_code_ast(doc, grammar, chunk_size)
        else:
            chunks = default_splitter.split_documents([doc])
            _locate_lines(doc, chunks, chunk_overlap)

        for i, chunk in enumerate(chunks):
            chunk.metadata.update({
                "chunk_index": i,              # 이 파일에서 몇 번째 청크
                "total_chunks": len(chunks),   # 이 파일 전체 청크 수
            })

        all_chunks.extend(chunks)

    return all_chunks
