# ResearchLens

> A multi-capability RAG system for academic research — upload a paper, get a structured summary, identify research gaps, ask questions grounded in the document, and compare insights across multiple papers.

---

## Features

- **Intelligent PDF Ingestion** — Upload any research paper. Text is extracted page-by-page (PyMuPDF), chunked, embedded, and stored in Qdrant. SHA-256 hashing prevents duplicate processing — re-uploading the same paper instantly returns the existing session.
- **Structured Summarization** — Automatically generates a three-section summary (Contributions, Methodology, Results) on upload. Cached in the database; served instantly on every subsequent request.
- **Research Gap Analysis** — Identifies untested domains, unvalidated assumptions, open questions from the paper body, and explicit limitations and future work from the authors. All gaps are cached at upload time.
- **Input Guardrail** — Every query is classified by an LLM before entering the pipeline. Off-topic questions (general knowledge, small talk, code requests, etc.) are rejected immediately with a clear message, without touching retrieval or generation.
- **Cited Question Answering (RAG)** — Ask any question about the paper. Answers are grounded in retrieved chunks with page-level citations. A score-based grader skips redundant LLM calls for high-confidence matches.
- **Web Search Fallback** — When the paper's content is insufficient to answer a query, Tavily web search is triggered automatically before generation.
- **Multi-Paper Comparison** — Select two or more past sessions and generate a structured cross-paper analysis. The comparison is split into four parts: an extracted facts table (datasets, key metrics, model type, primary limitation — sourced directly from cached summaries), a dimensional rating across Novelty, Methodological Rigor, Generalization, and Scalability, a core differences section grounded in specific datasets and design choices, and a contextual verdict that states which paper is stronger for what problem rather than making a universal judgment.
- **User Authentication** — Register and log in with token-based auth. Each user's sessions, chat history, summaries, and gap analyses are isolated and persisted.
- **Session Dashboard** — All past uploads are accessible from the dashboard. Load any session to immediately resume with full summary, gaps, and chat history context restored.

---

## Architecture

ResearchLens is built around two LangGraph graphs that run at different points in the application lifecycle.

### Ingestion Graph

Runs **once per PDF upload**. All expensive operations — summarization, gap analysis, metadata extraction — happen here and are persisted to the database. Subsequent requests for the same data are pure database reads.

```
pdf_parser → embedder → metadata_extractor → summarizer → gap_finder
```

| Node                 | Responsibility                                                                                          |
| -------------------- | ------------------------------------------------------------------------------------------------------- |
| `pdf_parser`         | Extracts page-level text from the PDF using PyMuPDF                                                     |
| `embedder`           | Generates 384-dim embeddings and upserts chunks to Qdrant                                               |
| `metadata_extractor` | Extracts title, authors, abstract, limitations, and future work via LLM                                 |
| `summarizer`         | Produces a structured three-section summary from the paper's head and tail zones                        |
| `gap_finder`         | Identifies research gaps from the paper's middle zone; merges with metadata limitations and future work |

### Query Graph

Runs **per user QA query only**. Summary and gap queries are intercepted at the server level and served from cache — the graph is never invoked for them. Off-topic queries are rejected by the guardrail node before any retrieval happens.

```
guardrail → chunk_loader → query_router → retriever → grader → [web_search] → generator → citation_builder
```

| Node               | Responsibility                                                                                        |
| ------------------ | ----------------------------------------------------------------------------------------------------- |
| `guardrail`        | LLM-based classifier — rejects queries unrelated to research papers before any retrieval happens      |
| `chunk_loader`     | Loads all chunks for the session from Qdrant                                                          |
| `query_router`     | Routes the query (all graph-level queries are QA by the time they reach here)                         |
| `retriever`        | Cosine similarity search in Qdrant; returns top-k chunks with relevance scores                        |
| `grader`           | Passes chunks above a score threshold directly; sends borderline chunks to LLM for relevance judgment |
| `web_search`       | Triggered when no relevant chunks are found; queries Tavily for supplementary context                 |
| `generator`        | Generates the final answer using retrieved and/or web context                                         |
| `citation_builder` | Attaches page-level citations to the response                                                         |

### Guardrail Design

The guardrail is the first node in the query graph. It sends the user's question to the LLM with a strict YES/NO classification prompt. If the verdict is NO, `query_type` is set to `blocked` and the graph short-circuits to `END` via a conditional edge — the retrieval pipeline, generator, and citation builder are never invoked. Blocked queries are also not written to chat history.

```
Incoming QA query
       │
       ▼
   guardrail (LLM classifier)
       │
  ┌────┴────┐
  │         │
 YES        NO
  │         │
  ▼         ▼
chunk_   return blocked
loader   response + EXIT
```

### Zone-Based Text Splitting

Rather than blindly slicing the full paper text, all LLM calls operate on named zones:

| Zone     | Definition                                                    | Used by                            |
| -------- | ------------------------------------------------------------- | ---------------------------------- |
| `head`   | First 8,000 characters                                        | `metadata_extractor`, `summarizer` |
| `tail`   | Last 5,000 characters before the references section           | `metadata_extractor`, `summarizer` |
| `middle` | Everything between head and tail, capped at 15,000 characters | `gap_finder`                       |

This keeps every LLM call well within Groq's token limits while targeting each zone at the content that actually lives there: introductions and abstracts at the head, conclusions and results at the tail, methodology and experiments in the middle.

### Query Classification and Caching

```
Incoming /query request
        │
        ▼
classify_query() — keyword matching, no LLM
        │
   ┌────┴────┐
   │         │
summary    gap        qa
   │         │          │
   ▼         ▼          ▼
DB read   DB read   query_graph.invoke()
                         │
                         ▼
                     guardrail (LLM)
                         │
                  blocked? → return early
                         │
                    retrieval pipeline
```

Summary and gap queries never touch the LLM or the graph. They are keyword-classified at the server level and returned directly from the cached database columns populated during ingestion.

---

## Tech Stack

| Component           | Technology                                                   |
| ------------------- | ------------------------------------------------------------ |
| LLM                 | Groq — `llama-3.3-70b-versatile`                             |
| Embeddings          | HuggingFace sentence-transformers (384-dim, cosine distance) |
| Vector Database     | Qdrant Cloud                                                 |
| Graph Orchestration | LangGraph                                                    |
| Backend API         | FastAPI                                                      |
| Frontend            | Streamlit                                                    |
| Relational Database | Supabase (PostgreSQL via psycopg2)                           |
| Web Search Fallback | Tavily                                                       |
| PDF Parsing         | PyMuPDF                                                      |
| Tracing             | LangSmith                                                    |

---

## Project Structure

```
ResearchLens/
├── config.py                   # All environment variables and constants (HEAD_CHARS, TAIL_CHARS, GAP_MAX_CHARS)
├── app_frontend.py             # Streamlit frontend — auth, dashboard, session view, comparison UI
├── requirements.txt
│
├── api/
│   ├── server.py               # FastAPI app — all endpoints, query classification, caching logic
│   └── auth_router.py          # /register and /login
│
├── services/
│   ├── auth_service.py         # Token generation and validation, bcrypt password hashing
│   ├── embedding_service.py    # HuggingFace embedding wrapper
│   ├── pdf_service.py          # PyMuPDF extraction + text chunking (chunk_size=1200, overlap=150)
│   ├── qdrant_service.py       # Qdrant upsert, search, scroll
│   └── text_sections.py        # Zone-based text splitter — head / middle / tail
│
├── graph/
│   ├── state.py                # ResearchState TypedDict, CitationObject, RetrievedDoc
│   └── builder.py              # Ingestion graph and query graph definitions
│
└── nodes/
    ├── pdf_parser.py
    ├── embedder.py
    ├── metadata_extractor.py
    ├── summarizer.py
    ├── gap_finder.py
    ├── chunk_loader.py
    ├── query_router.py
    ├── retriever.py
    ├── grader.py
    ├── web_search.py
    ├── generator.py
    ├── citation_builder.py
    └── guardrail.py            # LLM-based input classifier — blocks off-topic queries
```

---

## Database Schema

All tables use the `rpa_` prefix to avoid collisions in a shared database.

### `rpa_users`

| Column          | Type      | Notes       |
| --------------- | --------- | ----------- |
| `user_id`       | UUID      | Primary key |
| `email`         | TEXT      | Unique      |
| `password_hash` | TEXT      | bcrypt      |
| `created_at`    | TIMESTAMP |             |

### `rpa_user_tokens`

| Column       | Type      | Notes                     |
| ------------ | --------- | ------------------------- |
| `token`      | TEXT      | Primary key               |
| `user_id`    | UUID      | Foreign key → `rpa_users` |
| `created_at` | TIMESTAMP |                           |

### `rpa_sessions`

| Column          | Type      | Notes                                              |
| --------------- | --------- | -------------------------------------------------- |
| `session_id`    | UUID      | Primary key                                        |
| `user_id`       | UUID      | Foreign key → `rpa_users`                          |
| `pdf_name`      | TEXT      | Original filename                                  |
| `pdf_hash`      | TEXT      | SHA-256; used for deduplication                    |
| `summary`       | TEXT      | Cached at ingestion time                           |
| `research_gaps` | JSONB     | Cached at ingestion time                           |
| `metadata`      | JSONB     | Title, authors, abstract, limitations, future work |
| `chat_history`  | JSONB     | Append-only array of `{role, content}` turns       |
| `created_at`    | TIMESTAMP |                                                    |

---

## API Endpoints

| Method | Endpoint        | Auth  | Description                                                                                    |
| ------ | --------------- | ----- | ---------------------------------------------------------------------------------------------- |
| POST   | `/register`     | No    | Create a new user account                                                                      |
| POST   | `/login`        | No    | Authenticate and receive a token                                                               |
| POST   | `/upload`       | Token | Upload and process a PDF; returns `session_id`                                                 |
| POST   | `/query`        | Token | Ask a question; guardrail blocks off-topic queries; summary/gap served from cache              |
| POST   | `/my-sessions`  | Token | List all past sessions for the current user                                                    |
| POST   | `/session-data` | Token | Fetch cached summary, gaps, and metadata for a single session                                  |
| POST   | `/compare`      | Token | Compare two or more sessions — structured facts table, dimensional ratings, contextual verdict |
| GET    | `/health`       | No    | Health check                                                                                   |

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/YashAgarwalTheWiz/ResearchLens-
cd ResearchLens
```

### 2. Create a virtual environment and install dependencies

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_api_key
QDRANT_URL=your_qdrant_cluster_url
QDRANT_API_KEY=your_qdrant_api_key
COLLECTION_NAME=research_papers
COHERE_API_KEY=your_cohere_api_key
TAVILY_API_KEY=your_tavily_api_key
DATABASE_URL=your_supabase_postgres_connection_string
```

| Variable                        | Where to get it                                                |
| ------------------------------- | -------------------------------------------------------------- |
| `GROQ_API_KEY`                  | [console.groq.com](https://console.groq.com)                   |
| `QDRANT_URL` + `QDRANT_API_KEY` | [cloud.qdrant.io](https://cloud.qdrant.io) — Cluster dashboard |
| `COHERE_API_KEY`                | [dashboard.cohere.com](https://dashboard.cohere.com)           |
| `TAVILY_API_KEY`                | [app.tavily.com](https://app.tavily.com)                       |
| `DATABASE_URL`                  | Supabase project → Settings → Database → Connection string     |

> `.env` is excluded from version control. Never commit API keys or database credentials.

### 4. Run the backend

```bash
uvicorn api.server:app --reload
```

### 5. Run the frontend

```bash
streamlit run app_frontend.py
```

The Streamlit app expects the backend at `http://127.0.0.1:8000` by default. Change the `API_URL` constant in `app_frontend.py` if running on a different host or port.

---

## Usage

1. **Register** a new account or **log in** via the dashboard.
2. **Upload a PDF** (20 pages or fewer recommended). Processing runs the full ingestion pipeline and takes 20–60 seconds depending on paper length.
3. Once processed, the session opens automatically with:
   - **Chat tab** — Ask any question about the paper. Off-topic questions are rejected by the guardrail. Answers come with page-level citations.
   - **Summary tab** — Three-section structured summary, ready instantly.
   - **Research Gaps tab** — Combined list of implicit gaps (from the paper body) and explicit limitations and future work (from the authors).
4. Return to the **dashboard** at any time to reload past sessions or compare multiple papers.
5. To **compare papers**, select two or more from the dashboard multiselect and click **Compare Selected Papers**.

---

## Known Limitations

- **Groq free tier** has a 6,000 tokens-per-minute limit and a 100,000 tokens-per-day limit. Ingestion (metadata extraction + summarization + gap analysis) consumes approximately 3,000–5,000 tokens per paper. Processing several papers in quick succession may trigger temporary rate limit errors.
- **Recommended PDF size is 20 pages or fewer.** Larger documents produce more chunks and longer combined text, increasing the risk of hitting per-request token limits even with zone-based splitting.
- **Web search fallback depends on Tavily's free tier**, which allows 1,000 searches per month. Heavy QA usage on papers with limited content will exhaust this faster.
- **Chat history is session-local.** Loading a past session restores cached summary and gaps instantly, but the visible chat history starts fresh. The full historical chat context is stored in the database and is passed to the LLM for generation, but it is not rendered in the UI on reload.
- **Guardrail adds one LLM call per QA query.** This counts against the Groq token limit. Summary and gap queries bypass the guardrail entirely since they never reach the graph.
