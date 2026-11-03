import os
from dotenv import load_dotenv

load_dotenv()

# --- online services we still need (an LLM and a paper database can't run on 8 GB RAM / offline) ---
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
OPENALEX_API_KEY = os.environ.get("OPENALEX_API_KEY")   # free key = 10x bigger daily budget

# --- local storage + local embeddings ---
DB_PATH = os.environ.get("DB_PATH", "data/researchlens.db")     # one SQLite file, created automatically
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"     # 384-dim, ~90 MB, runs on CPU

# --- LLM ---
LLM_MODEL = "openai/gpt-oss-120b"
LLM_MODEL_FAST = "openai/gpt-oss-20b"

# --- extraction ---
EXTRACT_MAX_CHARS = 9000     # max text sent to the LLM per field group
IDENTITY_MAX_CHARS = 3000    # title/authors/year only need the first page

# --- question answering ---
QA_TOP_K = 5                 # chunks retrieved per question
QA_HISTORY_MESSAGES = 6      # how many previous chat messages the LLM sees

# --- related work / positioning ---
RELATED_TOP_K = 10            # how many related papers we compare against
RELATED_ABSTRACT_CHARS = 900  # abstract length sent to the LLM per related paper
MAX_CANDIDATES = 300          # max candidates we fetch abstracts for before ranking