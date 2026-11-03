# ResearchLens

Upload a research paper and see **what it really says**, **where it stands against related work**, and **ask questions about it** — with every claim linked to its source.

A plain chatbot can summarise a PDF. ResearchLens checks the paper against the field: it finds the 10 most similar published papers, compares them, and tells you what's new, what was done before, and what the paper is missing — and every claim is verified in code to point at a real, retrieved paper.

## Features

| Tab | What it does | How it stays grounded |
|---|---|---|
| 📄 **Paper** | Problem, core idea, method, datasets, metrics, key results, author-stated limitations and future work | Every fact carries its page number and the exact quote; facts whose quote can't be found in the paper are dropped |
| 🧭 **Where It Stands** | Finds the 10 closest papers on OpenAlex, builds a comparison table, rates each contribution (mostly new / partly done / largely done before) and lists gaps vs. the field | Dataset/metric coverage is counted in code; every claim must cite a retrieved paper, invented citations are removed; links are built from real IDs |
| 💬 **Ask** | Q&A about the paper | Answers cite excerpts inline (`[S1]`); only cited excerpts are shown; invented references are removed |
| 🔬 **Compare** | Side-by-side comparison of your own uploaded papers | The table comes straight from the extracted facts |

## Architecture

Three small LangGraph pipelines:

```
Upload:           pdf_parser → embedder → table_extractor → extractor
Ask:              retriever → generator → citation_builder
Where It Stands:  related_finder → related_extractor → positioning_analyst → citation_verifier
```

- **related_finder** — finds candidates on OpenAlex (references, citing papers, related works, keyword search), then ranks them by embedding similarity
- **related_extractor** — one batched LLM call reads all 10 abstracts
- **positioning_analyst** — code counts dataset/metric coverage, the LLM writes the contribution checks and gaps
- **citation_verifier** — drops any claim that doesn't cite a real retrieved paper

## Tech stack

| Layer | Tech |
|---|---|
| LLM | Groq (`gpt-oss-120b`, `gpt-oss-20b`) |
| Related papers | OpenAlex API |
| Embeddings | `all-MiniLM-L6-v2` (local, sentence-transformers) |
| Storage + vector search | SQLite + numpy cosine similarity (local) |
| Orchestration | LangGraph |
| Backend / Frontend | FastAPI / Streamlit |
| PDF parsing | PyMuPDF |

## Evaluation

```bash
python -m eval.grounding_eval
```
- **Grounding rate:** share of generated claims that cite a real retrieved paper
- **Related-paper precision:** share of the 10 related papers judged relevant (you label them in `eval/related_labels.csv`)

## Setup

```bash
git clone https://github.com/YashAgarwalTheWiz/ResearchLens-
cd ResearchLens
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

## Limitations

- Groq free tier has per-minute and daily token limits; papers of 20 pages or fewer work best
- Some publishers don't share abstracts with OpenAlex; those papers are skipped, so you may see fewer than 10 related papers
- Very new papers may not be indexed on OpenAlex yet; related work is then found through keyword search only