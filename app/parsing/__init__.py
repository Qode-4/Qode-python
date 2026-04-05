from langchain_core.documents import Document
from app.parsing.loader import collect_documents
from app.parsing.splitter import split_documents, DEFAULT_CHUNK_SIZE, DEFAULT_CHUNK_OVERLAP
from app.parsing.filters import filter_chunks


def parse_and_chunk(
    repo_path: str,
    project_id: str,
    max_files: int | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Document]:
    # 1. 파일 수집
    docs = collect_documents(repo_path, project_id, max_files=max_files)
    # 2. 청크 분할
    chunks = split_documents(docs, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    # 3. 짧은 청크 제거
    chunks = filter_chunks(chunks)

    return chunks
