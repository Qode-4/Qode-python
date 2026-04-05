from app.parsing.loader import collect_documents
from langchain_core.documents import Document
from app.parsing.splitter  import split_documents
from app.parsing.filters import filter_chunks

docs = collect_documents("tests/fixtures", "test_project", 200)
print(f"수집된 문서의 개수는?: {len(docs)}")

# docs 파일 이름만 추출
file_names = [doc.metadata["source"] for doc in docs]

print(f"파일 이름 : {file_names}")

chunks = split_documents(docs, chunk_size=100, chunk_overlap=20)
chunks = filter_chunks(chunks)

print(chunks)