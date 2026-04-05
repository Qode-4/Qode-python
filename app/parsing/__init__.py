from langchain_core.documents import Document
from app.parsing.loader import collect_documents
from app.parsing.splitter  import split_documents
from app.parsing.filters import filter_chunks

def parse_and_chunk() -> list[Document]:
    # 파일 수집
    # 청크 분할
    # 청크 Filter 

    docs = collect_documents()
    chunks = split_documents()
    chunks = filter_chunks(chunks)

    return chunks