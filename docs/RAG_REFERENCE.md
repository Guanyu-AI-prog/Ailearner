# RAG Systems — Quick Reference for Codex

> Hybrid retrieval (Vector + BM25 + Rerank), pure Python / LangChain, eval methodology.
> Extracted from Hermes `rag-systems` skill. Use as context when building RAG systems.

## 1. When to Use RAG

| Signal | RAG | Direct Context |
|--------|-----|----------------|
| < 10 docs / < 50K chars | ❌ Overhead | ✅ Just send everything |
| 1000+ docs | ✅ Required | ❌ Won't fit |
| Dynamic data | ✅ Re-embed cheap | ❌ Re-send expensive |
| Source citations | ✅ Exact chunks | ❌ |

**Rule**: If you can paste everything into one prompt under 100K tokens, don't build RAG.

## 2. Architecture — Hybrid Retrieval Pipeline

```
Query → [Classifier]
  ├─ Single → vector(k=10) + BM25(k=10) → dedup → rerank(top_n=3) → LLM
  └─ Comparison → split per-entity queries → each: vector+BM25 → merge → rerank → LLM
```

### Key code: BM25 Chinese Tokenizer (critical!)

```python
def _tokenize(self, text: str) -> list[str]:
    tokens = []
    for char in text:
        if '\u4e00' <= char <= '\u9fff':
            tokens.append(char)  # Chinese char-by-char
        elif char.isalnum():
            tokens.append(char.lower())
    tokens.extend(re.findall(r'[a-zA-Z]+', text.lower()))
    return tokens
```

**⚠️ CRITICAL**: `text.split()` does NOT work for Chinese. Always use char-level tokenization.

### Key code: Hybrid Search (parallel)

```python
from concurrent.futures import ThreadPoolExecutor

def hybrid_search(query, vector_k=10, bm25_k=10):
    with ThreadPoolExecutor(max_workers=2) as pool:
        v_future = pool.submit(vectorstore.similarity_search, query, k=vector_k)
        b_future = pool.submit(bm25.search, query, top_k=bm25_k)
        return deduplicate_docs(v_future.result() + b_future.result())
```

### Key code: Comparison Query Splitting

```python
def split_comparison(query):
    # "99元和129元区别" → ["99元套餐 流量 通话 宽带", "129元套餐 流量 通话 宽带"]
    numbers = re.findall(r'(\d+)', query)
    return [f'{n}元套餐 流量 通话 宽带 副卡 月租' for n in numbers]
```

**⚠️ CRITICAL**: Don't search with the full comparison query — it biases toward one entity. Search each entity separately, merge with dedup.

### Key code: Safe Embedding Client (batch + retry)

```python
def embed_documents(self, texts):
    all_embeddings = []
    for i in range(0, len(texts), self.chunk_size):
        batch = texts[i:i + self.chunk_size]
        try:
            all_embeddings.extend(self._call_api(batch))
        except Exception:
            for t in batch:  # Fallback: single-item retry
                try:
                    all_embeddings.append(self._call_api([t])[0])
                except:
                    all_embeddings.append([0.0] * 1024)  # Zero vector
    return all_embeddings
```

### Key code: Rerank

```python
def rerank(query, docs, top_n=3):
    resp = requests.post(f'{BASE_URL}/rerank',
        headers={'Authorization': f'Bearer {API_KEY}'},
        json={'model': RERANK_MODEL, 'query': query, 'documents': docs, 'top_n': top_n},
        timeout=10)
    return resp.json().get('results', [])
```

### Key code: State Machine (replaces LangGraph StateGraph)

```python
def run(initial_state):
    state = dict(initial_state)
    state.update(_translate_node(state))
    state.update(_classify_node(state))
    while True:
        route = _route_by_type(state)
        state.update(_retrieve_node(state, route))
        if _evaluate_retrieval(state) == "rewrite":
            state.update(_rewrite_query(state))
            continue
        state.update(_answer_node(state))
        break
    return state
```

## 3. Component Mapping: LangChain → Pure Python

| LangChain | Pure Python |
|-----------|-------------|
| `Document` | `@dataclass(page_content, metadata)` |
| `ChatOpenAI` | `requests.post()` to `/chat/completions` |
| `OpenAIEmbeddings` | `requests.post()` to `/embeddings` |
| `Chroma` | `chromadb.PersistentClient` |
| `BM25Retriever` | `rank_bm25.BM25Okapi` + custom tokenizer |
| `ContextualCompressionRetriever` | Direct reranker API call |
| `StateGraph` | Manual `while True` state machine |
| `ChatPromptTemplate` | `format_prompt()` returning `List[Dict]` |

## 4. Eval Methodology

### 6-Type Question Taxonomy

| Type | Example |
|------|---------|
| 单点查询 | "29元套餐多少流量？" |
| 对比型 | "99元和129元区别？" |
| 多跳推理 | "129元+300M宽带+2张副卡总价？" |
| 流程型 | "如何办理携号转网？" |
| 场景型 | "一家三口推荐什么套餐？" |
| 边界/异常 | "联通套餐多少钱？" |

Generate 30 questions (5 per type), two phrasing variants (formal + colloquial).

### Eval Flow
```
questions.json → for each Q: retrieve → LLM answer → score → save to results.json
```
- Incremental save after EACH question (crash-safe)
- 3s delay between questions (rate-limit)
- Thread-based timeout (signal.alarm doesn't work in subprocess)

### Scoring Dimensions

| Dimension | Weight |
|-----------|--------|
| 准确率 | 30% |
| 幻觉率 | 20% |
| 检索能力 | 25% |
| 完整性 | 15% |
| 平均耗时 | 10% |

### Error Analysis

| Error | Fix Location |
|-------|-------------|
| 概念/价格混淆 | Prompt: add disambiguation rules |
| 幻觉编造 | Prompt: "only use KB data" |
| 检索失败 | Retrieval: add BM25, query expansion |
| 角色越界 | Prompt: add role boundary |

**Key insight**: Most errors are LLM reasoning failures AFTER correct retrieval, not retrieval failures. Fix is in PROMPT, not retrieval.

## 5. SiliconFlow API

- Base: `https://api.siliconflow.cn/v1/`
- Embedding: `BAAI/bge-m3` (no char limit) or `BAAI/bge-large-zh-v1.5` (500-char limit!)
- Rerank: `BAAI/bge-reranker-v2-m3`
- Speed pick: `THUDM/GLM-4-32B-0414` (4-5x faster than DeepSeek V4 Flash)

## 6. CRITICAL Pitfalls Checklist

- [ ] BM25 MUST use char-level tokenizer for Chinese, NOT `text.split()`
- [ ] ChromaDB metadata: values must be `str|int|float|bool`, NO `None`, NO nested dicts
- [ ] Batch embedding ≤ 32 items per call (avoid 400 error)
- [ ] `bge-large-zh-v1.5` truncate at 500 chars (char limit, not token limit)
- [ ] Rerank timeout 10s (NOT 5s), max_retries ≤ 1
- [ ] LLM timeout 15s, max_retries=0 (prevents timeout×retries multiplication)
- [ ] Rerank failure: degrade gracefully (return unranked docs), don't fail
- [ ] Cache BM25 index (rebuilding every query = 10+min delays)
- [ ] Comparison queries: search PER ENTITY, not full comparison query
- [ ] Verify data completeness BEFORE `build_vectors.py`
- [ ] Dynamic model names: `os.getenv("LLM_MODEL", "default")`, NOT hardcoded
- [ ] HuggingFace blocked in China → `HF_ENDPOINT=https://hf-mirror.com`

## 7. Dependencies

```bash
# Pure Python
pip install chromadb rank_bm25 pymupdf requests python-dotenv

# LangChain
pip install langchain langchain-openai langchain-community langchain-chroma chromadb
```

## 8. Config Template

```env
LLM_MODEL=deepseek-ai/DeepSeek-V4-Flash
LLM_API_KEY=sk-xxx
EMBED_MODEL=BAAI/bge-m3
RERANK_MODEL=BAAI/bge-reranker-v2-m3
BASE_URL=https://api.siliconflow.cn/v1
MAX_WORKERS=2
CHUNK_SIZE=500
RETRIEVAL_K=3
```

## 9. Related: Agent Harness

For production RAG, also design the **Agent Harness** around it:
- **Prompt constraints** → role, behavior boundaries, disambiguation rules
- **Tool definitions** → what the agent can call
- **Routing** → simple vs comparison vs complex query paths
- **Degradation** → agent fail → fast_path fail → graceful fallback
- **Circuit breaker** → consecutive failures auto-disable

See `AGENT_HARNESS.md` for full Agent Harness patterns.
