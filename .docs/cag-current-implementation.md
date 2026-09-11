# 현재 CAG 구현 상세 (교체 대상)

> 기존 Node.js Qode 서버의 CAG 동작 방식을 기록한 문서.
> RAG로 전환할 때 기존 동작을 이해하고 대응하기 위함.

## CAG 흐름 요약

```
[Repo Sync]
     ↓
[허용파일 수집] → 최대 80개, 파일당 12KB, 전체 180KB
     ↓
[OpenAI로 분석] → gpt-4.1-mini, temperature 0.1, JSON 응답
     ↓
[project_analysis 테이블에 JSONB로 저장]
     ↓
[채팅 시 시스템 프롬프트에 캐시 전체 주입]
```

## 파일 수집 규칙

`ProjectAnalysisService.collectRepositorySnapshot`에서 처리.

### 허용 확장자

```
.ts, .tsx, .js, .jsx, .json, .md, .sql, .yml, .yaml, .sh
```

### 제외 디렉터리

```
.git, node_modules, dist, build, .next, .turbo
```

### 제외 파일 패턴

```
.env, SSH 키, PEM 파일 등 민감 파일
```

### 크기 제한

| 항목 | 값 | RAG에서는? |
|------|-----|----------|
| 최대 파일 수 | 80개 | 늘릴 수 있음 (청크 단위 검색이니까) |
| 파일당 최대 크기 | 12,000 바이트 | 필요 없을 수 있음 (청킹으로 분할) |
| 전체 컨텍스트 최대 | 180,000자 | 필요 없음 (프롬프트에 전부 넣지 않으니까) |

## 분석 결과 구조

OpenAI가 반환하는 JSON (ProjectAnalysisSummary):

```json
{
    "project_overview": "이 프로젝트는...",
    "architecture": ["Fastify 기반 3계층 구조", "모듈식 라우팅"],
    "core_modules": [
        {"path": "src/modules/auth", "purpose": "JWT 기반 인증"}
    ],
    "key_flows": ["사용자 로그인 → 토큰 발급 → API 호출"],
    "risks": ["환경 변수 하드코딩 발견"],
    "recommended_next_steps": ["테스트 커버리지 확대"]
}
```

## 채팅 시 프롬프트 구조

```
시스템 프롬프트:
"You are Qode coding assistant.
Use only the provided project analysis cache as ground truth.
If information is not in cache, say it is not present in analysis cache.

Project analysis cache:
{위의 JSON 전체}"

+ 최근 채팅 20개
+ 사용자 질문
```

## CAG의 한계 (RAG 전환 동기)

| 문제 | 설명 | RAG에서 해결 |
|------|------|------------|
| 정보 손실 | 코드를 요약하면서 세부 구현이 날아감 | 원본 청크를 직접 전달 |
| 크기 제한 | 80파일/180KB 제한이 빡빡 | 청크 단위 검색이라 제한 완화 가능 |
| 전체 재분석 | Sync할 때마다 전체 재분석 (느림, 비용) | 변경 파일만 재인덱싱 가능 |
| 토큰 낭비 | 질문과 무관한 코드도 프롬프트에 포함 | 관련 청크만 선별 포함 |
| 할루시네이션 | 요약 과정에서 정보 왜곡 가능 | 원본 코드 그대로 전달 |

## 기존 코드 위치 (Node.js 서버 참고)

| 파일 | 역할 |
|------|------|
| `src/modules/project-analysis/project-analysis.service.ts` | 분석 캐시 생성/관리 |
| `src/modules/project-analysis/project-analysis.repository.ts` | DB 저장/조회 |
| `src/modules/chat/chat.service.ts` | 채팅 시 캐시 조회 + 프롬프트 조립 |
| `src/lib/openai-client.ts` | OpenAI API 호출 (분석 + 스트리밍) |

## 전환 시 변경 포인트

Node.js 서버에서 수빈이 수정할 부분:

```typescript
// 변경 전 (CAG)
const cache = await getAnalysisCache(projectId);
const prompt = buildCAGPrompt(cache, question, history);

// 변경 후 (RAG)
const searchResult = await fetch("http://rag-service:8000/search", { ... });
const prompt = buildRAGPrompt(searchResult, question, history);
```

기존 `streamLLMResponse()` 코드는 변경 없이 그대로 사용한다.
