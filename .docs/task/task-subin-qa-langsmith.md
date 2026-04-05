# 수빈 — 질의응답 + LangSmith

> RAG 파이프라인의 네 번째 단계.
> 검색된 청크를 LLM에 전달하고 답변을 생성하는 역할 + 전체 파이프라인 평가.
> **TypeScript** (기존 Qode 서버) — Python RAG 서비스의 검색 API를 HTTP로 호출

---

## 목표

혜수의 Python RAG 서비스가 제공하는 검색 API를 호출해서 청크를 받고, 프롬프트를 조립하고, 기존 LLM/SSE 스트리밍과 연결한다. LangSmith로 전체 RAG 파이프라인을 추적하고 품질을 평가한다.

---

## 입력 인터페이스 (혜수의 Python 서비스에서 HTTP로 받는 것)

```typescript
// Python 서비스 POST /search 의 응답을 TypeScript 타입으로 정의
interface SearchResult {
  chunks: RetrievedChunk[];
  search_meta: {
    total_found: number;
    search_time_ms: number;
  };
}

interface RetrievedChunk {
  page_content: string;
  score: number;
  metadata: {
    source: string;
    language: string;
    chunk_index: number;
    start_line?: number;
    end_line?: number;
    project_id: string;
  };
}
```

---

## 작업 목록

### 1. Python RAG 서비스 호출 클라이언트

혜수의 Python 서비스를 HTTP로 호출하는 코드.

```typescript
const RAG_SERVICE_URL = process.env.RAG_SERVICE_URL || "http://localhost:8000";

async function searchChunks(
  query: string,
  projectId: string,
  topK: number = 5
): Promise<SearchResult> {
  const response = await fetch(`${RAG_SERVICE_URL}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      project_id: projectId,
      top_k: topK,
    }),
  });

  if (!response.ok) {
    throw new Error(`RAG 검색 실패: ${response.status}`);
  }

  return response.json();
}
```

### 2. prompt template 설계

기존 CAG 프롬프트를 RAG 방식으로 전환한다.

```typescript
// 기존 CAG 방식 (참고)
// 시스템 프롬프트 = "너는 코드 어시스턴트야"
//                + 분석 캐시 전체 (요약된 코드베이스)
//                + 최근 채팅 20개
//                + 사용자 질문

// RAG 방식
function buildRAGPrompt(
  searchResult: SearchResult,
  userQuestion: string,
  chatHistory: Message[]
): string {
  const contextBlock = searchResult.chunks
    .map(chunk => {
      const { source, start_line, end_line } = chunk.metadata;
      const lineInfo = start_line ? ` (L${start_line}-${end_line})` : "";
      return `--- ${source}${lineInfo} ---\n${chunk.page_content}`;
    })
    .join("\n\n");

  return `다음 코드를 참고하여 질문에 답하세요.
출처 파일 경로도 함께 알려주세요.

참고 코드:
${contextBlock}

질문: ${userQuestion}`;
}
```

**결정할 것:**
- 프롬프트 템플릿 구조 (시스템 프롬프트 / 코드 컨텍스트 / 질문의 순서)
- 출처 표시를 프롬프트에서 지시할지, 후처리로 붙일지
- 최근 채팅 히스토리를 어떻게 함께 넣을지

### 3. context 길이 조절

검색된 청크를 전부 넣으면 토큰 제한에 걸릴 수 있다.

```typescript
function trimContext(
  chunks: RetrievedChunk[],
  maxChars: number = 8000
): RetrievedChunk[] {
  const result: RetrievedChunk[] = [];
  let totalChars = 0;

  for (const chunk of chunks) {
    if (totalChars + chunk.page_content.length > maxChars) break;
    result.push(chunk);
    totalChars += chunk.page_content.length;
  }

  return result;
}
```

**결정할 것:**
- context 최대 길이 (토큰 비용 vs 답변 품질 트레이드오프)
- 청크 수 기준으로 자를지, 글자 수 기준으로 자를지

### 4. answer formatting

LLM 응답에 출처 정보를 포함시킨다.

```typescript
interface RAGResponse {
  answer: string;
  sources: SourceInfo[];
}

interface SourceInfo {
  filePath: string;
  lineRange?: string;
  relevanceScore: number;
}

function formatResponse(
  llmAnswer: string,
  searchResult: SearchResult
): RAGResponse {
  const sources = searchResult.chunks.map(chunk => ({
    filePath: chunk.metadata.source,
    lineRange: chunk.metadata.start_line
      ? `L${chunk.metadata.start_line}-${chunk.metadata.end_line}`
      : undefined,
    relevanceScore: chunk.score,
  }));

  const uniqueSources = deduplicateSources(sources);

  return {
    answer: llmAnswer,
    sources: uniqueSources,
  };
}
```

### 5. 기존 LLM/SSE 연결

기존 Qode의 LLM 호출 + SSE 스트리밍 코드에 RAG 프롬프트를 연결한다.

```typescript
// 기존 CAG 코드 (수정 전)
async function handleChat(question: string, projectId: string) {
  const cache = await getAnalysisCache(projectId);     // 요약 캐시 조회
  const history = await getRecentMessages(chatRoomId);  // 최근 채팅
  const prompt = buildCAGPrompt(cache, question, history);
  return streamLLMResponse(prompt);
}

// RAG 코드 (수정 후)
async function handleChat(question: string, projectId: string) {
  // ★ Python RAG 서비스 HTTP 호출
  const searchResult = await searchChunks(question, projectId, 5);

  const history = await getRecentMessages(chatRoomId);
  const trimmed = trimContext(searchResult.chunks, 8000);
  const prompt = buildRAGPrompt(
    { ...searchResult, chunks: trimmed },
    question,
    history
  );
  const llmAnswer = await streamLLMResponse(prompt);
  return formatResponse(llmAnswer, searchResult);
}
```

**핵심:**
- 기존 `getAnalysisCache()` → `searchChunks()` (Python 서비스 HTTP 호출)로 교체
- 기존 `buildCAGPrompt()` → `buildRAGPrompt()` 로 교체
- 기존 `streamLLMResponse()` 는 그대로 사용

### 6. LangSmith 연동

전체 RAG 파이프라인을 추적하고 품질을 평가한다.

#### 셋업

```typescript
// .env
// LANGCHAIN_TRACING_V2=true
// LANGCHAIN_API_KEY=ls__xxxx
// LANGCHAIN_PROJECT=qode-rag

// LangSmith JS SDK 사용
import { Client } from "langsmith";
import { traceable } from "langsmith/traceable";

const client = new Client();
```

#### 수동 트레이싱

```typescript
// 검색 단계 추적 (Python 서비스 호출 포함)
const tracedSearch = traceable(
  async (query: string, projectId: string) => {
    return await searchChunks(query, projectId, 5);
  },
  { name: "rag-search", run_type: "retriever" }
);

// 전체 파이프라인 추적
const tracedRAGPipeline = traceable(
  async (question: string, projectId: string) => {
    const searchResult = await tracedSearch(question, projectId);
    const prompt = buildRAGPrompt(searchResult, question, []);
    const answer = await streamLLMResponse(prompt);
    return formatResponse(answer, searchResult);
  },
  { name: "rag-pipeline", run_type: "chain" }
);
```

#### LangSmith에서 볼 수 있는 것

```
LangSmith 대시보드:
├ 각 질문별 전체 파이프라인 trace
│  ├ 검색 단계: Python 서비스 호출 시간, 반환된 청크, 유사도 점수
│  ├ 프롬프트: 실제 조립된 프롬프트 전문
│  ├ LLM 호출: 토큰 사용량, 응답 시간
│  └ 최종 응답
├ 비용 추적 (토큰 사용량 기반)
└ 품질 평가 (아래 7번)
```

### 7. LangSmith 평가 (Evaluation)

```typescript
import { evaluate } from "langsmith/evaluation";

// 평가용 데이터셋 생성
const dataset = await client.createDataset("qode-rag-eval");

// 테스트 케이스 추가
await client.createExamples({
  datasetId: dataset.id,
  inputs: [
    { question: "인증 로직이 어디에 있어?" },
    { question: "데이터베이스 연결은 어떻게 해?" },
    { question: "라우팅 구조 설명해줘" },
  ],
  outputs: [
    { expected_sources: ["src/auth.ts"] },
    { expected_sources: ["src/config/database.ts"] },
    { expected_sources: ["src/routes/index.ts"] },
  ],
});

// 평가 실행
await evaluate(
  async (input) => {
    return await tracedRAGPipeline(input.question, "test-project");
  },
  {
    data: "qode-rag-eval",
    evaluators: [
      (run, example) => ({
        key: "source_included",
        score: run.outputs.sources.some(
          s => example.outputs.expected_sources.includes(s.filePath)
        ) ? 1 : 0,
      }),
      (run) => ({
        key: "answer_length",
        score: run.outputs.answer.length > 50 ? 1 : 0,
      }),
    ],
  }
);
```

---

## 병렬 작업

채연, 예지, 혜수와 **병렬 가능**하다.

수빈은 mock SearchResult로 프롬프트 설계와 LangSmith 셋업을 먼저 할 수 있다:

```typescript
// mock SearchResult (수빈이 테스트용으로 직접 만듦)
const mockSearchResult: SearchResult = {
  chunks: [
    {
      page_content: "export function verifyToken(token: string) {\n  return jwt.verify(token, SECRET);\n}",
      score: 0.92,
      metadata: {
        source: "src/auth.ts",
        language: "typescript",
        chunk_index: 0,
        start_line: 12,
        end_line: 15,
        project_id: "test",
      },
    },
  ],
  search_meta: { total_found: 5, search_time_ms: 45 },
};

// 이걸로 프롬프트 설계 + answer formatting 테스트
const prompt = buildRAGPrompt(mockSearchResult, "인증 로직 어디에 있어?", []);
console.log(prompt);
```

---

## 전체 피드백 루프에서의 역할

수빈은 **최종 출력을 보는 사람**이라 전체 파이프라인의 문제를 먼저 발견할 수 있다:

```
수빈: LangSmith에서 답변 품질 확인
  │
  ├ 검색 결과가 관련 없음 → 혜수에게: "threshold 올려야 할 것 같아요"
  ├ 관련 청크는 맞는데 너무 작음 → 채연에게: "chunk_size 늘려야 할 것 같아요"
  ├ 임베딩 품질 자체가 낮음 → 예지에게: "모델을 large로 바꿔볼까요?"
  └ 프롬프트 구조 문제 → 수빈 본인이 수정
```

---

## 타임라인

| 주차 | 작업 | 비고 |
|------|------|------|
| Week 1 | prompt template 초안 설계 + Python 서비스 호출 클라이언트 구현 | mock SearchResult로 실험 |
| Week 1-2 | context 길이 조절 로직 + answer formatting | |
| Week 2 | LangSmith 셋업 (환경 변수, 프로젝트 생성) | |
| Week 3 | 혜수의 Python 검색 API와 연결 | 실제 데이터로 프롬프트 테스트 |
| Week 3-4 | 기존 LLM/SSE 코드에 RAG 프롬프트 연결 | CAG → RAG 전환 핵심 |
| Week 4 | LangSmith 트레이싱 + 평가 데이터셋 구축 | |
| Week 4-5 | 전체 파이프라인 평가 + 피드백 루프 | 전원 협업 |
