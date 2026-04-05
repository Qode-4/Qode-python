from app.parsing.filters import detect_language, is_allowed_file,filter_chunks
from langchain_core.documents import Document

print(detect_language(".py"))  # Expected: "python"
print(detect_language(".123123"))  # Expected: "unknown"

print(is_allowed_file("test.py"))  # Expected: True
print(is_allowed_file("test.env"))  # Expected: False
print(is_allowed_file("node_modules/test.js"))  # Expected: False

chunks = [
    Document(page_content="짧은 청크", metadata={"source": "file1.py"}),
    Document(page_content="엄청엄청엄청엄청엄청엄청엄청엄청엄청엄청엄청엄청엄청엄청엄청엄청엄청엄청엄청엄청엄청엄청엄청엄청 길게해보자", metadata={"source": "file2.py"}),
    Document(page_content="   ", metadata={"source": "file3.py"}),
]
filtered_chunks = filter_chunks(chunks)
print(f"청크 : {filtered_chunks}")
print(f"수집된 청크의 개수는?: {len(filtered_chunks)}")