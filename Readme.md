# ResearchLens

A multi-capability RAG system for academic research — upload a paper, get a structured summary, identify research gaps, ask questions grounded in the document, and compare insights across multiple papers.

## What it does

- **Upload a PDF** → extracts text, generates embeddings, caches summary + research gaps
- **Ask questions** → RAG pipeline retrieves relevant chunks, generates cited answers
- **Off-topic guardrail** → LLM classifier blocks non-paper questions before they hit the pipeline
- **Web search fallback** → triggers Tavily if the paper can't answer the query
- **Compare multiple papers simultaneously** → select any number of past sessions and get a structured cross-paper breakdown: extracted facts table (datasets, metrics, model type, limitations), dimensional ratings (Novelty, Rigor, Generalization, Scalability), core differences, and a contextual verdict on which paper is stronger for what problem
- **Auth + sessions** → every user's papers, chats, and summaries are persisted and reloadable

## Tech Stack

| Layer       | Tech                                        |
| ----------- | ------------------------------------------- |
| LLM         | Groq llama-3.3-70b-versatile                |
| Embeddings  | HuggingFace sentence-transformers (384-dim) |
| Vector DB   | Qdrant Cloud                                |
| Reranking   | Cohere rerank-english-v3.0                  |
| Graph       | LangGraph                                   |
| Backend     | FastAPI                                     |
| Frontend    | Streamlit                                   |
| Database    | Supabase (PostgreSQL)                       |
| Web Search  | Tavily                                      |
| PDF Parsing | PyMuPDF                                     |

## Query Flow

```
/query
  │
  ├── summary / gap?  →  DB cache  →  return
  │
  └── QA?
        │
      guardrail (LLM) — off-topic? → reject
        │
      chunk_loader → retriever (vector search → Cohere rerank) → grader
        │
        ├── low confidence? → web_search
        │
      generator → citation_builder → return
```

## Retrieval Evaluation

Built an evaluation harness (`eval/recall_eval.py`) to measure retrieval quality with Hit Rate@5 and MRR, and to quantify the effect of adding a Cohere reranking stage.

Ground truth: 10 hand-curated question/answer-chunk pairs across 2 papers (_Deep Residual Learning for Image Recognition_, and _Phase Transitions in Attention_), verified against actual stored chunk indices via direct Qdrant inspection — not estimated.

| Metric     | Baseline (vector search only) | With Cohere Rerank |
| ---------- | ----------------------------- | ------------------ |
| Hit Rate@5 | 0.700                         | 0.700              |
| MRR        | 0.412                         | 0.475              |

**Takeaway:** Reranking improved the ranking quality of retrieved hits (MRR +15%) but did not increase raw hit coverage at this sample size — 3 of 10 questions never surfaced the correct chunk in the top 5, with or without reranking.

**Planned:** expand ground truth to 15–20 questions, add a third paper, and test cross-document retrieval (current sessions are single-paper; multi-paper contamination has not yet been evaluated).

## Project Structure

```
ResearchLens/
├── api/
│   ├── server.py
│   └── auth_router.py
├── graph/
│   ├── builder.py
│   └── state.py
├── nodes/
│   ├── guardrail.py         ← input classifier (new)
│   ├── chunk_loader.py
│   ├── retriever.py          ← vector search + Cohere reranking
│   ├── grader.py
│   ├── generator.py
│   ├── citation_builder.py
│   ├── web_search.py
│   ├── pdf_parser.py
│   ├── embedder.py
│   ├── summarizer.py
│   ├── gap_finder.py
│   └── metadata_extractor.py
├── eval/
│   ├── ground_truth.json
│   └── recall_eval.py
├── services/
├── config.py
└── app_frontend.py
```

## Setup

```bash
git clone https://github.com/YashAgarwalTheWiz/ResearchLens-
cd ResearchLens
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file:

```
GROQ_API_KEY=
QDRANT_URL=
QDRANT_API_KEY=
COLLECTION_NAME=research_papers
COHERE_API_KEY=
TAVILY_API_KEY=
DATABASE_URL=
```

```bash
uvicorn api.server:app --reload   # backend
streamlit run app_frontend.py     # frontend
```

## API

| Method | Endpoint        | Description             |
| ------ | --------------- | ----------------------- |
| POST   | `/register`     | Create account          |
| POST   | `/login`        | Get token               |
| POST   | `/upload`       | Upload + process PDF    |
| POST   | `/query`        | Ask a question          |
| POST   | `/my-sessions`  | List past sessions      |
| POST   | `/session-data` | Load a session          |
| POST   | `/compare`      | Compare multiple papers |
| GET    | `/health`       | Health check            |

## Limitations

- Groq free tier: 6k tokens/min, 100k/day — large papers or rapid uploads may hit limits
- PDF sweet spot: 20 pages or fewer
- Tavily free tier: 1,000 searches/month
- Guardrail adds one extra LLM call per QA query (summary/gap queries skip it)
- Retrieval is scoped per-session, not per-paper — sessions containing multiple PDFs would search across all of them undifferentiated
