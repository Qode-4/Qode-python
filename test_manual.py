from app.parsing.loader import collect_documents

docs = collect_documents("tests/fixtures", "test_project", 2)
print(f"수집된 문서의 개수는?: {len(docs)}")

# docs 파일 이름만 추출
file_names = [doc.metadata["source"] for doc in docs]

print(f"파일 이름 : {file_names}")
print(f"문서 출력 : {docs}")