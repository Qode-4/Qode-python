# 채연 — 파싱 + 청킹 (Document Loader + Text Splitter)

> RAG 파이프라인의 첫 번째 단계.
> 파일을 읽어서 Document로 변환하고, 검색에 적합한 크기로 분할하는 역할.
> **Python** (LangChain Python) — 2단계 Unstructured 도입 대비

---

## 목표

Repo Sync 시 허용된 파일을 수집하고, LangChain Python의 Document 형태로 변환한 뒤, 적절한 크기의 청크로 분할하여 임베딩 단계(예지)에 넘긴다.

---

## 출력 인터페이스 (예지에게 넘기는 것)

```python
# Document 형태 (LangChain 표준)
# Document(
#   page_content="파일 내용...",
#   metadata={
#     "source": "src/auth.ts",
#     "language": "typescript",
#     "extension": ".ts",
#     "chunk_index": 0,
#     "total_chunks": 5,
#     "start_line": 1,
#     "end_line": 30,
#     "project_id": "proj_123",
#   }
# )
```

예지는 이 형태에 맞는 mock 데이터로 임베딩 작업을 병렬 진행할 수 있다.

---

## 작업 목록

### 1. 허용 확장자 및 제외 패턴 정의

기존 CAG의 허용/제외 목록을 기반으로 RAG용 목록을 재설계한다.

```python
ALLOWED_EXTENSIONS = [
    # 코드
    ".ts", ".tsx", ".js", ".jsx", ".py", ".java", ".go", ".rs", ".rb",
    # 문서
    ".md", ".txt", ".yml", ".yaml", ".json", ".sql",
]

EXCLUDE_DIRS = [
    "node_modules", ".git", "dist", "build", ".next",
    "coverage", "__pycache__",
]

EXCLUDE_PATTERNS = [
    ".env", ".env.*", "credentials.*",
    "*.lock", "package-lock.json",
    "*.min.js", "*.map",
]
```

**결정할 것:**
- 기존 CAG의 허용 목록을 그대로 쓸지, 조정할지
- 추가로 제외할 패턴이 있는지

### 2. 파일 크기 제한 정책

```python
# 기존 CAG 제한값
DEFAULT_MAX_FILES = 80
DEFAULT_MAX_FILE_BYTES = 12_000
DEFAULT_MAX_CONTEXT_CHARS = 180_000

# RAG에서는?
# - CAG는 전체를 프롬프트에 넣으니까 제한이 빡빡했음
# - RAG는 청크 단위로 검색하니까 파일 수 제한을 늘릴 수 있음
# - 단, 임베딩 API 비용이 파일 수에 비례하므로 무제한은 안 됨
```

**결정할 것:**
- 파일 수 상한을 얼마로 할지 (80개 → ?)
- 파일당 크기 제한을 유지할지 (청킹으로 쪼개니까 큰 파일도 OK)
- 전체 컨텍스트 제한이 여전히 필요한지

### 3. Document Loader 구현

파일을 읽어서 LangChain Document로 변환한다.

```python
from langchain.document_loaders import TextLoader, DirectoryLoader

# 방법 1: LangChain DirectoryLoader 사용
loader = DirectoryLoader(
    "./repo",
    glob="**/*",
    loader_cls=TextLoader,
    show_progress=True,
)
docs = loader.load()

# 방법 2: 직접 파일 수집 후 Document 변환
import os
from langchain.schema import Document

def collect_documents(repo_path: str, project_id: str) -> list[Document]:
    docs = []
    for root, dirs, files in os.walk(repo_path):
        # 제외 디렉터리 스킵
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        for file in files:
            ext = os.path.splitext(file)[1]
            if ext not in ALLOWED_EXTENSIONS:
                continue
            if any(fnmatch(file, p) for p in EXCLUDE_PATTERNS):
                continue

            file_path = os.path.join(root, file)
            relative_path = os.path.relpath(file_path, repo_path)

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            docs.append(Document(
                page_content=content,
                metadata={
                    "source": relative_path,
                    "language": detect_language(ext),
                    "extension": ext,
                    "file_size": os.path.getsize(file_path),
                    "project_id": project_id,
                }
            ))
    return docs
```

### 4. 언어 감지

```python
EXTENSION_TO_LANGUAGE = {
    ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript",
    ".py": "python",     ".java": "java",
    ".go": "go",         ".md": "markdown",
    ".json": "json",     ".yml": "yaml",
    ".yaml": "yaml",     ".sql": "sql",
}

def detect_language(extension: str) -> str:
    return EXTENSION_TO_LANGUAGE.get(extension, "unknown")
```

### 5. 청킹 전략 선택 및 실험

#### 전략 A: RecursiveCharacterTextSplitter (기본)

```python
from langchain.text_splitter import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
    separators=["\n\n", "\n", " ", ""],
)

chunks = splitter.split_documents(docs)
```

#### 전략 B: 언어별 코드 인식 분할

```python
from langchain.text_splitter import Language

ts_splitter = RecursiveCharacterTextSplitter.from_language(
    language=Language.JS,
    chunk_size=1500,
    chunk_overlap=200,
)

py_splitter = RecursiveCharacterTextSplitter.from_language(
    language=Language.PYTHON,
    chunk_size=1500,
    chunk_overlap=200,
)

def get_splitter(language: str):
    if language in ("typescript", "javascript"):
        return ts_splitter
    elif language == "python":
        return py_splitter
    else:
        return default_splitter
```

#### 전략 C: 코드 vs 문서 이원화

```python
def split_document(doc: Document) -> list[Document]:
    language = doc.metadata["language"]

    if language in ("markdown", "yaml", "json"):
        return markdown_splitter.split_documents([doc])
    else:
        return get_splitter(language).split_documents([doc])
```

**결정할 것:**
- 어떤 전략으로 갈지 (A로 시작 → 점진적으로 B, C도 가능)
- 청크 크기 (500 ~ 1500자 범위에서 실험)
- overlap 크기 (보통 chunk_size의 10~20%)

### 6. 메타데이터 부여

각 청크에 검색과 출처 표시에 필요한 메타데이터를 추가한다.

```python
def add_chunk_metadata(chunks: list[Document], original_doc: Document) -> list[Document]:
    for i, chunk in enumerate(chunks):
        chunk.metadata.update({
            "chunk_index": i,
            "total_chunks": len(chunks),
            "start_line": calculate_start_line(chunk, original_doc),
            "end_line": calculate_end_line(chunk, original_doc),
        })
    return chunks

def calculate_start_line(chunk: Document, original: Document) -> int:
    content = original.page_content
    chunk_start = content.find(chunk.page_content)
    return content[:chunk_start].count("\n") + 1
```

### 7. 빈 청크 / 너무 작은 청크 필터링

```python
def filter_chunks(chunks: list[Document]) -> list[Document]:
    return [
        chunk for chunk in chunks
        if len(chunk.page_content.strip()) >= 50
    ]
```

### 8. 기존 Repo Sync와의 통합 지점

```
[기존 Repo Sync 흐름]
Repo Sync 트리거 (Node.js)
     ↓
Git clone / pull
     ↓
Python RAG 서비스 호출 ← ★ Node.js에서 HTTP로 트리거
     ↓
허용파일 수집 + Document 변환 + 청킹
     ↓
Chunk[] 반환 → 예지의 임베딩 단계로 전달
```

Node.js Qode 서버가 Repo Sync 시 Python RAG 서비스의 인덱싱 API를 호출하는 구조.

---

## 2단계 확장 (Unstructured 도입 시)

이미 Python이니까 Unstructured를 바로 import해서 쓸 수 있다:

```python
from unstructured.partition.auto import partition

# 텍스트 파일 → TextLoader (기존)
# PDF/DOCX → Unstructured (바로 추가)
if ext in (".pdf", ".docx", ".pptx"):
    elements = partition(filename=file_path, strategy="hi_res")
    # → Document 형태로 변환
else:
    # 기존 TextLoader 로직
```

---

## 타임라인

| 주차 | 작업 | 비고 |
|------|------|------|
| Week 1 | 허용 확장자/제외 패턴 정의, Document Loader 구현 | 예지와 Chunk 인터페이스 합의 |
| Week 1-2 | 청킹 전략 A 구현 + 실험 | mock 파일로 테스트 |
| Week 2 | 메타데이터 부여 + 필터링 로직 | |
| Week 2-3 | 예지의 임베딩 파이프라인과 연결 | 실제 데이터로 통합 테스트 |
| Week 3~ | 혜수의 검색 검증 결과 보면서 청킹 전략 튜닝 | 피드백 루프 |
