from langchain_text_splitters import Language, RecursiveCharacterTextSplitter
from langchain_core.documents import Document

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200

def _build_default_splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    # 기본 분할기 
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""],
    )

def _build_language_splitter(chunk_size: int, chunk_overlap: int) -> dict[str, RecursiveCharacterTextSplitter]:
    # 언어별 분할기 
    return {
        "python": RecursiveCharacterTextSplitter.from_language(Language.PYTHON, chunk_size=chunk_size, chunk_overlap=chunk_overlap),
        "javascript": RecursiveCharacterTextSplitter.from_language(Language.JS, chunk_size=chunk_size, chunk_overlap=chunk_overlap),
        "typescript": RecursiveCharacterTextSplitter.from_language(Language.TS, chunk_size=chunk_size, chunk_overlap=chunk_overlap),
        "java": RecursiveCharacterTextSplitter.from_language(Language.JAVA, chunk_size=chunk_size, chunk_overlap=chunk_overlap),
        "go": RecursiveCharacterTextSplitter.from_language(Language.GO, chunk_size=chunk_size, chunk_overlap=chunk_overlap),
        "rust": RecursiveCharacterTextSplitter.from_language(Language.RUST, chunk_size=chunk_size, chunk_overlap=chunk_overlap),
        "ruby": RecursiveCharacterTextSplitter.from_language(Language.RUBY, chunk_size=chunk_size, chunk_overlap=chunk_overlap),
        "markdown": RecursiveCharacterTextSplitter.from_language(Language.MARKDOWN, chunk_size=chunk_size, chunk_overlap=chunk_overlap),
    }

def split_documents(docs: list[Document], chunk_size: int = DEFAULT_CHUNK_SIZE, chunk_overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[Document]:
    default_splitter = _build_default_splitter(chunk_size, chunk_overlap)
    language_splitters = _build_language_splitter(chunk_size, chunk_overlap)

    all_chunks: list[Document] = []

    for doc in docs:
        # metadata에서 language 추출, 해당 언어에 맞는 분할기가 있으면 사용, 없으면 default_splitter 사용
        language = doc.metadata.get("language", "unknown")
        splitter = language_splitters.get(language, default_splitter)

        chunks = splitter.split_documents([doc])

        search_start = 0
        for i, chunk in enumerate(chunks):
            head = chunk.page_content[:50]

            # 청크 앞 50글자로 원본에서 위치 검색 (search_start 이후에서)
            pos = doc.page_content.find(head, search_start)

            if pos == -1:
                # 분할기가 앞뒤 공백을 정리하면 원문과 글자가 어긋나 못 찾는다.
                # 겹침 구간만큼 되돌려 재검색한다 (음수 시작은 문서 끝에서 찾게 되므로 0으로 자른다).
                pos = doc.page_content.find(head, max(0, search_start - chunk_overlap))

            if pos == -1:
                # 끝내 못 찾으면 줄 번호를 비운다.
                # 틀린 줄을 근거로 인용하느니 줄 범위를 표시하지 않는 쪽이 낫다.
                start_line = None
                end_line = None
            else:
                # pos 앞에 줄바꿈 개수 + 1 = 시작 줄 번호
                start_line = doc.page_content[:pos].count("\n") + 1

                # 시작 줄 + 청크 안의 줄바꿈 수 = 끝 줄
                end_line = start_line + chunk.page_content.count("\n")

                # 다음 청크는 현재 위치 이후에서 찾기 (중복 매칭 방지)
                search_start = pos + 1

            # 청크 메타데이터에 위치 정보 추가
            chunk.metadata.update({
                "chunk_index": i,              # 이 파일에서 몇 번째 청크
                "total_chunks": len(chunks),   # 이 파일 전체 청크 수
                "start_line": start_line,      # 원본 시작 줄
                "end_line": end_line,          # 원본 끝 줄
            })

        all_chunks.extend(chunks)

    return all_chunks

