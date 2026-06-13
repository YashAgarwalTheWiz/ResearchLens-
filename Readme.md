# ResearchLens

A multi-capability RAG (Retrieval-Augmented Generation) system that helps researchers analyze academic papers — summarizing content, identifying research gaps, and answering questions grounded in the paper (with web search fallback for queries the paper doesn't cover).

## Features

- **PDF Ingestion** — Upload a research paper and have it parsed, chunked, and embedded for retrieval.
- **Summarization** — Get a concise summary of the uploaded paper.
- **Research Gap Analysis** — Automatically identify limitations, untested domains, open questions, and suggested future work mentioned in the paper.
- **Question Answering (RAG)** — Ask questions about the paper; answers are grounded in retrieved chunks, with citations.
- **Web Search Fallback** — If the paper doesn't contain enough information to answer a query, the system falls back to live web search (Tavily) before generating a response.
- **User Authentication** — Register/login with token-based auth; each user's sessions and chat history are saved.
- **Session History** — Revisit past uploads and conversations from a dashboard.

## Tech Stack

| Component           | Technology                                                    |
| ------------------- | ------------------------------------------------------------- |
| LLM                 | Groq (`llama-3.3-70b-versatile`)                              |
| Embeddings          | Cohere (`embed-english-light-v3.0`, 384-dim, cosine distance) |
| Vector Database     | Qdrant Cloud                                                  |
| Orchestration       | LangGraph                                                     |
| Backend API         | FastAPI                                                       |
| Frontend            | Streamlit                                                     |
| Relational Database | Supabase (PostgreSQL via psycopg2)                            |
| Web Search Fallback | Tavily                                                        |
| PDF Parsing         | PyMuPDF                                                       |

## Architecture / Workflow

ResearchLens is built around two LangGraph graphs: an **ingestion graph** (runs once per uploaded PDF) and a **query graph** (runs per user query).

### 1. Ingestion Graph

```
                ┌─────────────┐        ┌───────────┐
   PDF Upload → │  pdf_parser │ ─────→ │  embedder │ → Qdrant (vector store)
                └─────────────┘        └───────────┘
```

- **pdf_parser** — Extracts text from the uploaded PDF (PyMuPDF) and splits it into chunks.
- **embedder** — Generates embeddings for each chunk (Cohere) and stores them in Qdrant under the paper's session/collection.

### 2. Query Graph

```
                ┌──────────────┐     ┌───────────────┐
  User Query →  │ chunk_loader  │ →  │  query_router │
                └──────────────┘     └───────┬───────┘
                                              │
                  ┌───────────────────────────┼───────────────────────────┐
                  │                           │                           │
                  ▼                           ▼                           ▼
           ┌─────────────┐            ┌─────────────┐            ┌──────────────┐
           │ summarizer  │            │ gap_finder  │            │  retriever   │
           └─────────────┘            └─────────────┘            └──────┬───────┘
                  │                           │                          ▼
                  │                           │                   ┌──────────────┐
                  │                           │                   │    grader    │
                  │                           │                   └──────┬───────┘
                  │                           │                          │
                  │                           │              ┌───────────┴───────────┐
                  │                           │              │ (insufficient context)│
                  │                           │              ▼                       │
                  │                           │       ┌──────────────┐               │
                  │                           │       │  web_search   │              │
                  │                           │       └──────┬───────┘               │
                  │                           │              │                       │
                  │                           │              ▼                       ▼
                  │                           │       ┌────────────────────────────────┐
                  │                           │       │           generator            │
                  │                           │       └───────────────┬────────────────┘
                  │                           │                        ▼
                  │                           │              ┌──────────────────┐
                  │                           │              │ citation_builder │
                  │                           │              └──────────────────┘
                  ▼                           ▼                        ▼
              [Response]                  [Response]               [Response]
```

- **chunk_loader** — Loads the relevant chunks/embeddings for the current session from Qdrant.
- **query_router** — Classifies the user's intent: summary request, gap-analysis request, or a general question.
- **summarizer** — Produces a summary of the paper directly from loaded chunks.
- **gap_finder** — Analyzes chunks for explicit limitations, untested areas, open questions, suggested future work, and unvalidated assumptions; returns a structured list of research gaps.
- **retriever** — Performs similarity search in Qdrant to retrieve chunks relevant to the query.
- **grader** — Evaluates whether retrieved chunks are sufficient to answer the query.
- **web_search** — Triggered only if the grader determines the paper's content is insufficient; queries Tavily for supplementary information.
- **generator** — Produces the final answer using retrieved (and optionally web-searched) context.
- **citation_builder** — Attaches source citations (paper chunks and/or web sources) to the generated answer.

## Project Structure

```
config.py                      ← loads all API keys/config from environment variables
app_frontend.py                ← Streamlit frontend (login/register → dashboard → chat)
api/
  server.py                    ← FastAPI app, all endpoints
  auth_router.py                ← /register and /login endpoints
services/
  auth_service.py               ← password hashing, token generation/validation
  embedding_service.py          ← Cohere embeddings
  pdf_service.py                ← PyMuPDF + text splitter
  qdrant_service.py              ← Qdrant CRUD, scroll, search
graph/
  state.py                       ← ResearchState TypedDict
  builder.py                     ← ingestion graph + query graph definitions
nodes/
  pdf_parser.py
  chunk_loader.py
  embedder.py
  retriever.py
  grader.py
  query_router.py
  web_search.py
  summarizer.py
  gap_finder.py
  generator.py
  citation_builder.py
```

## Database Schema (Supabase / PostgreSQL)

| Table             | Columns                                                           |
| ----------------- | ----------------------------------------------------------------- |
| `rpa_users`       | `user_id`, `email`, `password_hash`, `created_at`                 |
| `rpa_user_tokens` | `token`, `user_id`, `created_at`                                  |
| `rpa_sessions`    | `session_id`, `chat_history`, `user_id`, `pdf_name`, `created_at` |

All tables use the `rpa_` prefix to avoid collisions with other projects sharing the same database.

## Authentication

- Simple UUID-based bearer tokens (stored in `rpa_user_tokens`), not JWT.
- `/register` and `/login` endpoints handled in `auth_router.py`.
- All protected endpoints (`/upload`, `/query`, `/my-sessions`) require a valid token.
- Passwords are hashed with `passlib` (bcrypt backend).

## Setup

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd ResearchLens
```

### 2. Create a virtual environment and install dependencies

```bash
python -m venv venv
source venv/bin/activate      # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in the project root with the following keys:

```
GROQ_API_KEY=your_groq_api_key
QDRANT_URL=your_qdrant_cluster_url
QDRANT_API_KEY=your_qdrant_api_key
COLLECTION_NAME=research_papers
COHERE_API_KEY=your_cohere_api_key
TAVILY_API_KEY=your_tavily_api_key
DATABASE_URL=your_supabase_postgres_connection_string
```

| Variable          | Description                                            | Where to get it                                      |
| ----------------- | ------------------------------------------------------ | ---------------------------------------------------- |
| `GROQ_API_KEY`    | API key for the Groq LLM (`llama-3.3-70b-versatile`)   | [console.groq.com](https://console.groq.com)         |
| `QDRANT_URL`      | URL of your Qdrant Cloud cluster                       | [cloud.qdrant.io](https://cloud.qdrant.io)           |
| `QDRANT_API_KEY`  | API key for your Qdrant cluster                        | Qdrant Cloud dashboard                               |
| `COLLECTION_NAME` | Name of the Qdrant collection used to store embeddings | Your choice (default: `research_papers`)             |
| `COHERE_API_KEY`  | API key for Cohere embeddings                          | [dashboard.cohere.com](https://dashboard.cohere.com) |
| `TAVILY_API_KEY`  | API key for Tavily web search fallback                 | [tavily.com](https://tavily.com)                     |
| `DATABASE_URL`    | PostgreSQL connection string for Supabase              | Supabase project settings → Database                 |

> **Note:** `.env` is excluded from version control via `.gitignore`. Never commit API keys or database credentials.

### 4. Run the backend (FastAPI)

```bash
uvicorn api.server:app --reload
```

### 5. Run the frontend (Streamlit)

```bash
streamlit run app_frontend.py
```

## Usage

1. Register a new account or log in via the Streamlit frontend.
2. From the dashboard, upload a research paper (PDF, **20 pages or fewer recommended** — larger documents may exceed daily LLM token limits on the free tier).
3. Once processed, choose to:
   - Generate a **summary** of the paper.
   - Run **gap analysis** to identify research gaps.
   - **Ask questions** about the paper via the chat interface.
4. Revisit past sessions from the dashboard at any time.

## Known Limitations

- The Groq free tier has a 100,000-token-per-day limit. Summarization and gap analysis are token-intensive operations; processing several large papers per day may exhaust this quota.
- Recommended PDF size: **20 pages or fewer** for reliable processing within rate limits.

## Roadmap

- [ ] Add LangSmith tracing for observability
- [ ] Enforce PDF page-count limits at upload time
- [ ] Token usage tracking and budget warnings
- [ ] Deploy backend to Render and frontend to Streamlit Cloud

## License

Specify your license here (e.g., MIT).
