# ResearchLens

> Upload a research paper. Get a summary, research gaps, and cited answers to your questions — instantly.

---

## What it does

- **Upload a PDF** → extracts text, generates embeddings, caches summary + research gaps
- **Ask questions** → RAG pipeline retrieves relevant chunks, generates cited answers
- **Off-topic guardrail** → LLM classifier blocks non-paper questions before they hit the pipeline
- **Web search fallback** → triggers Tavily if the paper can't answer the query
- **Compare papers** → structured cross-paper analysis across multiple sessions
- **Auth + sessions** → every user's papers, chats, and summaries are persisted and reloadable

---

## Tech Stack

| Layer | Tech |
|---|---|
| LLM | Groq `llama-3.3-70b-versatile` |
| Embeddings | HuggingFace sentence-transformers (384-dim) |
| Vector DB | Qdrant Cloud |
| Graph | LangGraph |
| Backend | FastAPI |
| Frontend | Streamlit |
| Database | Supabase (PostgreSQL) |
| Web Search | Tavily |
| PDF Parsing | PyMuPDF |

---

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
      chunk_loader → retriever → grader
        │
        ├── low confidence? → web_search
        │
      generator → citation_builder → return
```

---

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
│   ├── retriever.py
│   ├── grader.py
│   ├── generator.py
│   ├── citation_builder.py
│   ├── web_search.py
│   ├── pdf_parser.py
│   ├── embedder.py
│   ├── summarizer.py
│   ├── gap_finder.py
│   └── metadata_extractor.py
├── services/
├── config.py
└── app_frontend.py
```

---

## Setup

```bash
git clone https://github.com/YashAgarwalTheWiz/ResearchLens-
cd ResearchLens
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file:

```env
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

---

## API

| Method | Endpoint | Description |
|---|---|---|
| POST | `/register` | Create account |
| POST | `/login` | Get token |
| POST | `/upload` | Upload + process PDF |
| POST | `/query` | Ask a question |
| POST | `/my-sessions` | List past sessions |
| POST | `/session-data` | Load a session |
| POST | `/compare` | Compare multiple papers |
| GET | `/health` | Health check |

---

## Limitations

- Groq free tier: 6k tokens/min, 100k/day — large papers or rapid uploads may hit limits
- PDF sweet spot: **20 pages or fewer**
- Tavily free tier: 1,000 searches/month
- Guardrail adds one extra LLM call per QA query (summary/gap queries skip it)
