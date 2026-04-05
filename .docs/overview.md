# Qode-python 프로젝트 개요

## 이 프로젝트가 뭔가

Qode의 RAG(Retrieval-Augmented Generation) 파이프라인을 담당하는 **Python 서비스**.

기존 Qode 서버(Node.js/Fastify)는 CAG(Cache-Augmented Generation) 방식으로 동작한다. 코드베이스를 통째로 요약해서 캐시에 저장하고, 질문할 때마다 그 캐시 전체를 프롬프트에 넣는 구조다. 이걸 RAG로 전환하려는 것이 이 프로젝트의 목표다.

## 왜 Python인가

- LangChain Python 생태계가 JS보다 성숙함
- 2단계에서 Unstructured(비정형 문서 파싱) 도입 시 Python 필수
- 2단계에서 LlamaIndex(고급 검색) 도입 시 Python 필수
- 처음부터 Python으로 하면 2단계 전환 비용 없음

## 아키텍처

```
[사용자 브라우저]
     ↓
[React 프론트엔드]
     ↓
[Node.js Qode 서버 (Fastify)]  ←── 기존 서버. LLM 호출, SSE 스트리밍, 인증 등 담당
     ↓ HTTP
[Python RAG 서비스 (이 프로젝트)]  ←── 인덱싱 + 검색 담당
     ↓
[Aurora PostgreSQL + pgvector]  ←── 벡터 저장소. 기존 DB에 pgvector 확장 추가
     ↓
[OpenAI API]  ←── 임베딩 생성 (text-embedding-3-small)
```

## 이 서비스가 하는 일

### 1. 인덱싱 (오프라인, Repo Sync 시)
- 파일 수집 → 청킹 → 임베딩 → 벡터 DB 저장
- Node.js 서버가 Repo Sync 완료 후 이 서비스의 인덱싱 API를 호출

### 2. 검색 (온라인, 사용자 질문 시)
- Node.js 서버가 `POST /search`를 호출
- 질문 임베딩 → 벡터 유사도 검색 → 정제/rerank → 관련 청크 반환
- Node.js 서버가 반환된 청크로 프롬프트를 조립해서 LLM에 전달

## 팀 분담

| 담당 | 영역 | 언어 |
|------|------|------|
| 채연 | 파싱 + 청킹 | Python |
| 예지 | 임베딩 + 벡터 저장 + DB 스키마 | Python |
| 혜수 | 검색 + 검증 | Python |
| 수빈 | 질의응답 + LangSmith | TypeScript (기존 Qode 서버) |

상세 작업 내용은 `docs/task/` 폴더 참고.

## 2단계 확장 계획

- **Unstructured**: PDF/DOCX/PPTX 파싱 지원 추가 (채연 담당)
- **LlamaIndex**: 고급 검색 — rerank, 부모-자식 청크 확장, Query Engine (혜수 담당)
