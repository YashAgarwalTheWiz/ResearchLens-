# ResearchLens

Upload a research paper and see **what it really says**, **where it stands against related work**, and **whether its citations are real** — or describe a research idea and find out if it's already been done. Every claim is linked to its source.

A plain chatbot can summarise a PDF. ResearchLens checks the paper against the field: it finds the 10 most similar published papers, compares them, and tells you what's new, what was done before, and what the paper is missing. Every claim is verified **in code** to point at a real, retrieved paper — invented citations are removed before you ever see them.

## Features

| Feature                | What it does                                                                                                                                                                                             | How it stays grounded                                                                                                                                            |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 📄 **Paper**           | Problem, core idea, method, a results table (metric, dataset, score, best baseline), datasets, metrics, author-stated limitations and future work                                                        | Every fact carries its page number and exact quote; facts whose quote isn't in the paper are dropped; each score must appear in its quoted sentence or table row |
| 🧭 **Where It Stands** | Finds the 10 closest papers on OpenAlex, rates each contribution (mostly new / partly done / largely done before), lists gaps vs. the field, and shows what datasets and metrics the field commonly uses | Coverage is counted in code; every claim must cite a retrieved paper; invented citations are removed; links are built from real IDs                              |
| 🔗 **References**      | Looks up every reference in the paper on OpenAlex and flags ones that can't be found or whose title, year or first author don't match                                                                    | Parsed titles must appear in the reference text; matching (title similarity, year, author) is done in code                                                       |
| 💬 **Ask**             | Q&A about the paper                                                                                                                                                                                      | Answers cite excerpts inline (`[S1]`); only cited excerpts are shown; invented references are removed                                                            |
| 💡 **Idea Check**      | Describe a research idea and see the closest published work, which parts look new, and what's already been done                                                                                          | Same verified pipeline as Where It Stands                                                                                                                        |
| 🔬 **Compare**         | Side-by-side comparison of your own uploaded papers                                                                                                                                                      | The table comes straight from the extracted facts                                                                                                                |

Uploads run in the background with a live progress bar (_Reading the PDF → Indexing the text → Finding tables → Extracting facts_), and every result is cached, so reopening a paper or re-checking the same idea costs no API calls.

## Architecture

Three small LangGraph pipelines (Idea Check reuses the third):

```
Upload:           pdf_parser → embedder → table_extractor → extractor        (background task, live progress)
Ask:              retriever → generator → citation_builder
Where It Stands:  related_finder → related_extractor → positioning_analyst → citation_verifier
Idea Check:       the same graph as Where It Stands, started from a text idea instead of a PDF
```

- **extractor** — pulls grounded facts from the paper; every value must come with a quote that is found in the text
- **related_finder** — gathers candidates from OpenAlex (references, citing papers, related works, keyword search), then ranks them by embedding similarity
- **related_extractor** — one batched LLM call reads all 10 abstracts
- **positioning_analyst** — code counts dataset/metric coverage; the LLM writes the contribution checks and gaps
- **citation_verifier** — drops any claim that doesn't cite a real retrieved paper

**Reference checker** (`services/reference_checker.py`): extracts the reference list from the PDF → a small LLM splits it into title / first author / year → code keeps only titles found in the text → each title is looked up on OpenAlex and compared in code.

## Tech stack

| Layer                             | Tech                                              |
| --------------------------------- | ------------------------------------------------- |
| LLM                               | Groq (`gpt-oss-120b`, `gpt-oss-20b`)              |
| Related papers + reference lookup | OpenAlex API                                      |
| Embeddings                        | `all-MiniLM-L6-v2` (local, sentence-transformers) |
| Storage + vector search           | SQLite + numpy cosine similarity (local)          |
| Orchestration                     | LangGraph                                         |
| Backend / Frontend                | FastAPI / Streamlit                               |
| PDF parsing                       | PyMuPDF                                           |

## Evaluation

| Metric                                                   | Result    |
| -------------------------------------------------------- | --------- |
| Grounding rate (claims citing a real retrieved paper)    | _fill in_ |
| Related-paper precision (related papers judged relevant) | _fill in_ |
| References verified on OpenAlex                          | _fill in_ |

How to reproduce:

```bash
# 1. with the backend running, upload + analyse a folder of PDFs
#    (safe to re-run: finished papers are reused; stops cleanly at the daily API limit)
python -m eval.run_batch papers/ --email you@example.com --password yourpassword --refs

# 2. compute the numbers; label eval/related_labels.csv with y/n, then run again for precision
python -m eval.grounding_eval
```

## Setup

```bash
git clone https://github.com/YashAgarwalTheWiz/ResearchLens-
cd ResearchLens-
python -m venv venv
venv\Scripts\activate          # Windows  (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
```

Create a `.env` file:

```
GROQ_API_KEY=
OPENALEX_API_KEY=
```

Run (two terminals, from the project root):

```bash
uvicorn api.server:app --reload
streamlit run app_frontend.py
```

The database (`data/researchlens.db`) is created automatically. The embedding model (~90 MB) downloads on first use.

> `--reload` restarts the server whenever a code file changes, which stops any upload in progress (it shows as failed — delete it and upload again). Leave `--reload` off when running the batch eval.

## Project structure

```
├── api/
│   ├── server.py              # FastAPI endpoints, background uploads
│   └── auth_router.py
├── graph/
│   ├── builder.py             # the three LangGraph pipelines
│   ├── state.py
│   └── positioning_state.py
├── nodes/                     # one file per graph node
├── schemas/                   # pydantic models for LLM outputs + stored facts
├── services/
│   ├── llm_service.py         # the one place that calls Groq (retries, caching, rate limits)
│   ├── openalex_service.py    # OpenAlex search, lookups, title matching
│   ├── reference_checker.py
│   ├── vector_store.py        # chunk storage + cosine search in SQLite
│   ├── embedding_service.py   # local MiniLM embeddings
│   ├── pdf_service.py         # PDF → sections → chunks; reference-list extraction
│   ├── section_detector.py
│   ├── table_service.py
│   ├── db.py
│   └── auth_service.py
├── eval/
│   ├── run_batch.py           # upload + analyse a folder of PDFs
│   ├── grounding_eval.py      # grounding rate, related-paper precision, reference stats
│   └── dump_chunks.py
├── app_frontend.py            # Streamlit UI
├── check_db.py                # inspect / delete sessions from the command line
└── config.py
```

## API

| Method | Endpoint              | Description                                           |
| ------ | --------------------- | ----------------------------------------------------- |
| POST   | `/register`, `/login` | Create an account / get a token                       |
| POST   | `/upload`             | Upload a PDF (processing continues in the background) |
| POST   | `/status`             | Upload progress: step, label, error                   |
| POST   | `/my-sessions`        | List your papers with their status                    |
| POST   | `/session-data`       | Extracted facts + saved chat for a paper              |
| POST   | `/delete-session`     | Delete a paper and everything saved for it            |
| POST   | `/positioning`        | Where It Stands (cached)                              |
| POST   | `/references`         | Reference check (cached)                              |
| POST   | `/query`              | Ask a question about a paper                          |
| POST   | `/idea-check`         | Check a research idea (cached per idea)               |
| POST   | `/my-ideas`           | Your recent ideas                                     |
| POST   | `/compare`            | Compare 2+ of your papers                             |
| GET    | `/health`             | Health check                                          |

## Limitations

- Groq's free tier has per-minute and daily token limits; papers of 20 pages or fewer work best, and only a few papers can be processed per day
- Some publishers don't share abstracts with OpenAlex; those papers are skipped, so you may see fewer than 10 related papers
- Very new papers may not be indexed on OpenAlex yet; related work is then found through keyword search only
- "Not found" in the reference check doesn't mean a citation is fake: books, theses, websites and very new preprints are often missing from OpenAlex
- Reference lists are found by their "References" heading; unusual layouts may not be detected
