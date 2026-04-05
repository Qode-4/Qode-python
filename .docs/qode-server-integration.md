# 기존 Qode 서버(Node.js)와의 연동

## 기존 서버 정보

- **스택**: Fastify 5.0.0 + TypeScript + PostgreSQL
- **아키텍처**: 모듈식 3계층 (route → service → repository)
- **모듈**: auth, chat, project, project-analysis, github-oauth, sample-item
- **포트**: 기본 3000

## Python 서비스가 Node.js 서버에 제공하는 API

### POST /search — 검색

Node.js 서버가 사용자 질문 시 호출한다.

```
Request:
{
  "query": "인증 로직이 어디에 있어?",
  "project_id": "proj_123",
  "top_k": 5
}

Response:
{
  "chunks": [
    {
      "page_content": "export function verifyToken(token) { ... }",
      "score": 0.92,
      "metadata": {
        "source": "src/auth.ts",
        "language": "typescript",
        "chunk_index": 0,
        "total_chunks": 5,
        "start_line": 12,
        "end_line": 30,
        "project_id": "proj_123"
      }
    }
  ],
  "search_meta": {
    "total_found": 15,
    "search_time_ms": 45
  }
}
```

### POST /index — 인덱싱 트리거

Node.js 서버가 Repo Sync 완료 후 호출한다.

```
Request:
{
  "project_id": "proj_123",
  "repo_path": "/path/to/synced/repo"
}

Response:
{
  "status": "completed",
  "chunks_created": 342,
  "elapsed_ms": 8500
}
```

## Node.js 서버의 관련 코드 흐름

### Repo Sync → 인덱싱 트리거

```
1. 사용자가 프로젝트 동기화 요청
2. Node.js: POST /api/projects/:id/sync
3. Node.js: Git clone/pull 실행
4. Node.js: 동기화 완료 콜백 (onJobCompleted)
5. Node.js: Python RAG 서비스의 POST /index 호출  ← 여기서 연결
6. Python: 파일 수집 → 청킹 → 임베딩 → 벡터 저장
```

### 사용자 질문 → 검색 → 응답

```
1. 사용자가 채팅에서 질문
2. Node.js: POST /api/chats/me/:id/messages
3. Node.js: Python RAG 서비스의 POST /search 호출  ← 여기서 연결
4. Python: 질문 임베딩 → 벡터 검색 → rerank → 청크 반환
5. Node.js: 청크 + 질문 → 프롬프트 조립 → OpenAI LLM 호출
6. Node.js: SSE 스트리밍으로 응답 반환
```

## 기존 CAG 방식 (현재 동작 중, 교체 대상)

Node.js 서버의 `ProjectAnalysisService`가 담당:

1. **파일 수집**: 허용 확장자 파일만 수집 (최대 80개, 파일당 12KB, 전체 180KB)
2. **분석**: OpenAI API로 코드베이스 요약 생성 (JSON 형태)
3. **저장**: `project_analysis` 테이블에 JSONB로 저장
4. **사용**: 채팅 시 시스템 프롬프트에 요약 캐시 전체를 주입

### CAG의 한계 (RAG로 전환하는 이유)

- 전체 코드를 요약하니까 세부 정보가 손실됨
- 파일 수/크기 제한이 빡빡함 (프롬프트에 전부 넣어야 하니까)
- Sync할 때마다 전체 재분석 필요 (부분 업데이트 불가)
- 질문과 관련 없는 코드도 프롬프트에 들어감 (토큰 낭비)

## 기존 서버의 SSE 스트리밍 프로토콜

Node.js 서버가 프론트엔드에 응답할 때 사용하는 형식:

```
event: start
data: {"messageId": "msg_123"}

event: token
data: {"token": "인증"}

event: token
data: {"token": " 로직은"}

event: done
data: {"messageId": "msg_123", "content": "인증 로직은..."}

event: error
data: {"error": "LLM 호출 실패"}
```

Python RAG 서비스는 이 프로토콜을 신경 쓸 필요 없다. 청크만 반환하면 Node.js가 나머지를 처리한다.

## 환경 변수 (Python 서비스에서 필요한 것)

```
DATABASE_URL=postgresql://user:pass@host:5432/db
OPENAI_API_KEY=sk-...
```

기존 Node.js 서버와 같은 PostgreSQL 데이터베이스를 공유한다.
pgvector 테이블만 별도로 사용.
