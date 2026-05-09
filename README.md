# Qode-python

Qode의 RAG(Retrieval-Augmented Generation) 파이프라인을 담당하는 Python 서비스.

기존 Qode 서버(Node.js)의 CAG 방식을 RAG로 전환하기 위한 프로젝트입니다.

## 아키텍처

```
[Node.js Qode 서버] → HTTP → [Python RAG 서비스 (이 프로젝트)]
                                    ↓
                              [Aurora PostgreSQL + pgvector]
                                    ↓
                              [OpenAI API (임베딩)]
```

## 팀 분담

| 담당 | 영역 | 모듈 |
|------|------|------|
| 채연 | 파싱 + 청킹 | `app/parsing/` |
| 예지 | 임베딩 + 벡터 저장 | `app/embedding/` |
| 혜수 | 검색 + 검증 | `app/retrieval/` |
| 수빈 | 질의응답 + LangSmith | 기존 Qode 서버 (TypeScript) |

## 시작하기

### 1. 가상환경 생성 및 의존성 설치

```bash
python -m venv venv
source venv/bin/activate    # Mac/Linux
# venv\Scripts\activate     # Windows

pip install -r requirements.txt
```

### 2. 환경 변수 설정

```bash
cp .env.example .env
# .env 파일을 열어 DATABASE_URL, OPENAI_API_KEY 채우기
```

### 3. 서버 실행

```bash
uvicorn app.api.main:app --reload --port 8000
```

## 모듈별 사용법

### 파싱 + 청킹 (채연)

레포지토리 파일을 수집하고 검색에 적합한 크기의 청크로 분할합니다.

```python
from app.parsing import parse_and_chunk

chunks = parse_and_chunk(
    repo_path="/path/to/repo",   # 레포지토리 경로
    project_id="proj_123",       # 프로젝트 ID
)

# 결과: list[Document]
for chunk in chunks:
    print(chunk.metadata["source"])      # 파일 경로
    print(chunk.metadata["language"])    # 프로그래밍 언어
    print(chunk.page_content[:100])      # 청크 내용
```

**옵션 파라미터:**

```python
chunks = parse_and_chunk(
    repo_path="/path/to/repo",
    project_id="proj_123",
    max_files=200,          # 최대 파일 수 (기본: 무제한)
    chunk_size=1000,        # 청크 크기 (기본: 1000자)
    chunk_overlap=200,      # 청크 겹침 (기본: 200자)
)
```

## 테스트 실행

```bash
# 전체 테스트
pytest tests/ -v

# 모듈별 테스트
pytest tests/retrieval/filter.py -v      # 검색 결과 필터
pytest tests/retrieval/dedup.py -v       # 중복 제거
pytest tests/retrieval/searcher.py -v    # 검색
```

## 디렉터리 구조

```
app/
├── parsing/                 # 파싱 + 청킹 (채연)
│   ├── __init__.py          # parse_and_chunk() 진입점
│   ├── filters.py           # 허용/제외 상수 + 유틸리티
│   ├── loader.py            # 파일 수집 + Document 변환
│   └── splitter.py          # 언어별 청킹
├── embedding/               # 임베딩 + 벡터 저장 (예지) — 추후
├── retrieval/               # 검색 + 검증 (혜수)
└── api/                     # API 엔드포인트 — 추후
tests/
├── fixtures/                # 테스트용 mock 파일
└── retrieval/
    ├── filter.py
    ├── dedup.py
    ├── searcher.py
    ├── pipeline.py
    └── reranker.py
.docs/
├── overview.md              # 프로젝트 개요
├── rag-pipeline.md          # RAG 파이프라인 상세
├── tech-stack.md            # 기술 스택
├── database-schema.md       # DB 스키마
├── api-contracts.md         # API 인터페이스
└── task/                    # 팀원별 작업 명세
```

## 기술 스택

- **Python** 3.11+
- **LangChain** (langchain-core, langchain-text-splitters)
- **FastAPI** + uvicorn
- **PostgreSQL** + pgvector (추후)
- **OpenAI** text-embedding-3-small

## 문서

- [프로젝트 개요](.docs/overview.md)
- [RAG 파이프라인 상세](.docs/rag-pipeline.md)
- [API 인터페이스](.docs/api-contracts.md)
- [데이터베이스 스키마](.docs/database-schema.md)
