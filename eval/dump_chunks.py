# Dump one paper's stored chunks to a JSON file (useful for building retrieval test sets).
# Run from the project root:  python -m eval.dump_chunks <session_id>
import json
import sys

from services.vector_store import get_all_chunks

session_id = sys.argv[1]
chunks = get_all_chunks(session_id)

out_path = f"eval/chunks_{session_id[:8]}.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(chunks, f, indent=2, ensure_ascii=False)

print(f"Saved {len(chunks)} chunks to {out_path}")
for c in chunks:
    print(f"[{c['chunk_index']}] (page {c['page_number']}, {c['section']}): {c['chunk_text'][:80]}...")