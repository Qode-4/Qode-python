# 기술 스택 및 환경 설정

## Python 환경

- **Python**: 3.11+
- **패키지 관리**: pip (또는 poetry)
- **웹 프레임워크**: FastAPI
- **ASGI 서버**: uvicorn

## 주요 의존성

```
# 웹 프레임워크
fastapi
uvicorn

# LangChain
langchain
langchain-openai
langchain-community

# 데이터베이스
psycopg2-binary      # PostgreSQL 드라이버
pgvector             # pgvector Python 바인딩

# OpenAI
openai               # 임베딩 API

# 유틸리티
python-dotenv        # 환경 변수 로딩
pydantic             # 데이터 모델 (FastAPI에서 사용)

# 2단계 추가 예정
# unstructured        # 비정형 문서 파싱 (PDF, DOCX)
# llama-index         # 고급 검색 (rerank, 부모-자식 청크)
# langsmith           # 파이프라인 트레이싱/평가
```

## 환경 변수

```env
# 데이터베이스 (기존 Qode 서버와 동일한 Aurora PostgreSQL)
DATABASE_URL=postgresql://user:pass@host:5432/db

# OpenAI (임베딩 생성용)
OPENAI_API_KEY=sk-...

# 서버 설정
HOST=0.0.0.0
PORT=8000

# LangSmith (선택, 수빈 담당)
# LANGCHAIN_TRACING_V2=true
# LANGCHAIN_API_KEY=ls__...
# LANGCHAIN_PROJECT=qode-rag
```

## 기존 Qode 서버 스택 (참고)

Python RAG 서비스가 연동하는 기존 서버:

| 항목 | 값 |
|------|-----|
| 런타임 | Node.js 22.22.0 |
| 패키지 관리 | pnpm 10.x |
| 프레임워크 | Fastify 5.0.0 |
| 언어 | TypeScript |
| DB | PostgreSQL (pg 8.16.3) |
| 인증 | JWT (jsonwebtoken 9.0.3) |
| 검증 | Zod 3.23.8 |
| LLM | OpenAI API (gpt-4.1-mini 기본) |
| 배포 | PM2 + AWS EC2 |

## 디렉터리 구조 (예상)

```
Qode-python/
├── app/
│   ├── main.py              # FastAPI 앱 진입점
│   ├── config.py             # 환경 변수 설정
│   ├── parsing/              # 채연: 파싱 + 청킹
│   │   ├── loader.py         # Document Loader
│   │   ├── splitter.py       # Text Splitter
│   │   └── filters.py        # 확장자/패턴 필터
│   ├── embedding/            # 예지: 임베딩 + 벡터 저장
│   │   ├── embedder.py       # OpenAI 임베딩
│   │   ├── vectorstore.py    # PGVector 저장
│   │   └── schema.sql        # 테이블 DDL
│   ├── retrieval/            # 혜수: 검색 + 검증
│   │   ├── retriever.py      # Retriever
│   │   ├── reranker.py       # Rerank 로직
│   │   └── validator.py      # 검색 검증
│   └── api/                  # API 엔드포인트
│       ├── search.py         # POST /search
│       └── index.py          # POST /index
├── tests/
│   ├── test_parsing.py
│   ├── test_embedding.py
│   ├── test_retrieval.py
│   └── fixtures/             # 테스트용 mock 파일
├── docs/
│   ├── overview.md
│   ├── rag-pipeline.md
│   ├── database-schema.md
│   ├── qode-server-integration.md
│   ├── tech-stack.md
│   ├── api-contracts.md
│   └── task/                 # 팀원별 작업 명세
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## 로컬 개발 환경 셋업

```bash
# 1. 가상환경 생성
python -m venv venv
source venv/bin/activate

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 환경 변수 설정
cp .env.example .env
# DATABASE_URL, OPENAI_API_KEY 채우기

# 4. 서버 실행
uvicorn app.main:app --reload --port 8000
```
