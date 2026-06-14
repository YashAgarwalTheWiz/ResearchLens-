import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
QDRANT_URL = os.environ["QDRANT_URL"]
QDRANT_API_KEY = os.environ["QDRANT_API_KEY"]
COLLECTION_NAME = os.environ.get("COLLECTION_NAME", "research_papers")
COHERE_API_KEY = os.environ["COHERE_API_KEY"]
TAVILY_API_KEY = os.environ["TAVILY_API_KEY"]
DATABASE_URL = os.environ["DATABASE_URL"]
HEAD_CHARS=8000
TAIL_CHARS=5000
GAP_MAX_CHARS=15000