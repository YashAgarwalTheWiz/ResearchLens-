"""Upload a folder of PDFs and run the analyses on each, so the eval has data to measure.

Start the backend first (uvicorn api.server:app), then from the project root:
    python -m eval.run_batch papers/ --email you@example.com --password yourpassword
    python -m eval.run_batch papers/ --email ... --password ... --refs     # also run the reference check

Safe to re-run: papers already uploaded or analysed are reused, so no API calls are wasted.
Free Groq limits allow only a few papers per day, so it stops cleanly when the daily limit is hit.
"""
import argparse
import pathlib
import sys
import time

import requests

API = "http://127.0.0.1:8000"


def fail(msg):
    print(f"\n{msg}")
    sys.exit(1)


def detail(res):
    try:
        return res.json().get("detail", res.text)
    except Exception:
        return res.text[:300]


def call(path, token, timeout=600, **payload):
    res = requests.post(f"{API}{path}", json={"token": token, **payload}, timeout=timeout)
    if res.status_code == 429 or "Daily AI usage limit" in res.text:
        fail(f"Rate limit reached: {detail(res)}\nRun the same command again later; finished papers are kept.")
    return res


def wait_until_ready(token, session_id):
    while True:
        s = call("/status", token, session_id=session_id).json()
        if s["status"] in ("ready", "failed"):
            return s
        print(f"   ...{s['progress']}")
        time.sleep(3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--refs", action="store_true", help="also run the reference check")
    args = ap.parse_args()

    pdfs = sorted(pathlib.Path(args.folder).glob("*.pdf"))
    if not pdfs:
        fail(f"No PDFs found in {args.folder}")

    login = requests.post(f"{API}/login", json={"email": args.email, "password": args.password}, timeout=30)
    if login.status_code != 200:
        fail(f"Login failed: {detail(login)} (register in the app first)")
    token = login.json()["token"]

    for i, pdf in enumerate(pdfs, start=1):
        print(f"[{i}/{len(pdfs)}] {pdf.name}")
        with open(pdf, "rb") as f:
            up = requests.post(f"{API}/upload", files={"file": (pdf.name, f, "application/pdf")},
                               data={"token": token}, timeout=120)
        if up.status_code != 200:
            print(f"   upload failed: {detail(up)}")
            continue
        session_id = up.json()["session_id"]

        s = wait_until_ready(token, session_id)
        if s["status"] == "failed":
            if "Daily AI usage limit" in (s["error"] or ""):
                fail(f"Rate limit reached: {s['error']}\nRun again later; finished papers are kept.")
            print(f"   processing failed: {s['error']}")
            continue
        print("   ✓ extracted")

        pos = call("/positioning", token, session_id=session_id)
        print("   ✓ where it stands" if pos.status_code == 200 else f"   ✗ where it stands: {detail(pos)}")

        if args.refs:
            ref = call("/references", token, session_id=session_id)
            if ref.status_code == 200:
                c = ref.json()["counts"]
                print(f"   ✓ references: {c['verified']} verified, {c['check']} to check, {c['not_found']} not found")
            else:
                print(f"   ✗ references: {detail(ref)}")

    print("\nDone. Now run:  python -m eval.grounding_eval")


if __name__ == "__main__":
    main()