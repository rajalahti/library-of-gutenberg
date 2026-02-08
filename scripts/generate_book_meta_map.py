#!/usr/bin/env python3
"""Generate a richer Project Gutenberg metadata snapshot from Gutendex.

Outputs a mapping bookId -> minimal metadata needed for experiments:
- id
- title
- authors (names)
- languages
- subjects
- bookshelves
- inferredTheme (using same classify rules as theme map)

This is meant for LOCAL development only (file will be large).

Outputs:
- data/book-meta/bookMetaById.v1.jsonl   (one JSON object per book)
- data/book-meta/index.v1.json           (id -> byte offset index for quick lookup; optional)
- data/book-meta/checkpoint.json         (resume)
- data/book-meta/stats.v1.json

Usage:
  python3 scripts/generate_book_meta_map.py --max-books 70000 --out data/book-meta

Notes:
- JSONL keeps writes append-only and crash-safe.
- We keep a simple checkpoint with the next URL + seen ids.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import urllib.request
import urllib.error

GUTENDEX_BASE = "https://gutendex.com/books/"

THEMES = [
    {"id": "horror", "label": "HORROR & GOTHIC"},
    {"id": "mystery", "label": "MYSTERY & CRIME"},
    {"id": "scifi", "label": "SCIENCE FICTION"},
    {"id": "fantasy", "label": "FANTASY & MYTH"},
    {"id": "romance", "label": "ROMANCE"},
    {"id": "adventure", "label": "ADVENTURE & SEA"},
    {"id": "poetry", "label": "POETRY"},
    {"id": "drama", "label": "DRAMA & THEATRE"},
    {"id": "children", "label": "CHILDREN"},
    {"id": "history", "label": "HISTORY"},
    {"id": "religion", "label": "RELIGION"},
    {"id": "philosophy", "label": "PHILOSOPHY"},
    {"id": "science", "label": "SCIENCE & TECH"},
    {"id": "biography", "label": "BIOGRAPHY"},
    {"id": "travel", "label": "TRAVEL & GEOGRAPHY"},
    {"id": "general", "label": "GENERAL / OTHER"},
]
THEME_ID_SET = {t["id"] for t in THEMES}

THEME_RULES: List[Tuple[str, List[str]]] = [
    ("children", [r"\bchildren\b", r"juvenile", r"\bfairy tales\b", r"\bchild(?:ren)?'s\b"]),
    ("horror", [r"\bhorror\b", r"\bghost\b", r"\bvampire\b", r"\bwerewolf\b", r"\bgothic\b", r"\bhaunted\b", r"\boccult\b", r"\bdevil\b", r"\bwitch\b"]),
    ("mystery", [r"\bmystery\b", r"\bdetective\b", r"\bcrime\b", r"\bpolice\b", r"\bthriller\b"]),
    ("scifi", [r"science fiction", r"\bsci-?fi\b", r"\bspace\b", r"\btime travel\b", r"\baliens?\b", r"\brobots?\b"]),
    ("fantasy", [r"\bfantasy\b", r"\bmyth\b", r"\bmythology\b", r"\blegends?\b", r"\bfairy\b", r"\bdragons?\b"]),
    ("romance", [r"\bromance\b", r"\blove\b", r"\bcourtship\b"]),
    ("adventure", [r"\badventure\b", r"\bsea stories\b", r"\bpirates?\b", r"\bwestern\b"]),
    ("poetry", [r"\bpoetry\b", r"\bpoems\b", r"\bsonnets\b"]),
    ("drama", [r"\bdrama\b", r"\bplays?\b", r"\btheatre\b"]),
    ("history", [r"\bhistory\b", r"\bwar\b", r"\bmilitary\b", r"\brevolution\b"]),
    ("religion", [r"\breligion\b", r"\bchristian\b", r"\bbible\b", r"\btheology\b", r"\bsermons\b"]),
    ("philosophy", [r"\bphilosophy\b", r"\bethics\b", r"\blogic\b", r"\bmetaphysics\b"]),
    ("science", [r"\bscience\b", r"\bphysics\b", r"\bchemistry\b", r"\bbiology\b", r"\bmathematics\b", r"\bengineering\b", r"\btechnology\b"]),
    ("biography", [r"\bbiograph\b", r"\bautobiograph\b", r"\bdiaries\b", r"\bletters\b", r"\bcorrespondence\b", r"\bmemoirs\b"]),
    ("travel", [r"\btravel\b", r"\bvoyage\b", r"\bgeography\b", r"\bexploration\b"]),
]
_COMPILED_RULES: List[Tuple[str, List[re.Pattern[str]]]] = [
    (tid, [re.compile(pat, flags=re.IGNORECASE) for pat in pats])
    for tid, pats in THEME_RULES
]


def http_get_json(url: str, timeout: int = 30) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "library-of-gutenberg-book-meta/0.1 (local dev)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def safe_lower_join(items: Any) -> str:
    if not items:
        return ""
    if isinstance(items, list):
        return "\n".join(str(x) for x in items).lower()
    return str(items).lower()


def classify_theme(subjects: List[str], bookshelves: List[str], languages: List[str]) -> str:
    text = (safe_lower_join(subjects) + "\n" + safe_lower_join(bookshelves)).strip()
    for theme_id, patterns in _COMPILED_RULES:
        for pat in patterns:
            if pat.search(text):
                return theme_id
    return "general"


def load_checkpoint(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"next": GUTENDEX_BASE, "done": 0}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, obj: Any) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/book-meta")
    ap.add_argument("--max-books", type=int, default=70000)
    ap.add_argument("--sleep", type=float, default=0.25)
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()

    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)

    checkpoint_path = os.path.join(out_dir, "checkpoint.json")
    stats_path = os.path.join(out_dir, "stats.v1.json")
    jsonl_path = os.path.join(out_dir, "bookMetaById.v1.jsonl")
    seen_path = os.path.join(out_dir, "seen_ids.json")

    if args.reset:
        for p in [checkpoint_path, stats_path, jsonl_path, seen_path]:
            if os.path.exists(p):
                os.remove(p)

    ck = load_checkpoint(checkpoint_path)
    next_url = ck.get("next") or GUTENDEX_BASE

    # Track seen IDs so we can resume safely even if we append duplicates
    if os.path.exists(seen_path):
        seen = set(json.load(open(seen_path, "r", encoding="utf-8")))
    else:
        seen = set()

    counts = {t["id"]: 0 for t in THEMES}
    done = int(ck.get("done") or 0)
    page = int(ck.get("page") or 0)

    # Rebuild counts quickly from stats if exists
    if os.path.exists(stats_path):
        try:
            s = json.load(open(stats_path, "r", encoding="utf-8"))
            if isinstance(s.get("counts"), dict):
                counts.update(s["counts"])
            done = int(s.get("done") or done)
        except Exception:
            pass

    print(f"Starting: max_books={args.max_books} next={next_url} done={done}")

    with open(jsonl_path, "a", encoding="utf-8") as out:
        retries = 0
        while next_url:
            page += 1
            try:
                data = http_get_json(next_url)
                retries = 0
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
                retries += 1
                wait = min(30.0, 1.6 ** retries)
                print(f"WARN fetch failed ({type(e).__name__}): {e}. retry {retries} in {wait:.1f}s", flush=True)
                time.sleep(wait)
                continue

            results = data.get("results") or []
            for book in results:
                bid = int(book.get("id") or 0)
                if bid <= 0 or bid > args.max_books:
                    continue
                if bid in seen:
                    continue

                title = book.get("title") or ""
                authors = [a.get("name") for a in (book.get("authors") or []) if a.get("name")]
                languages = book.get("languages") or []
                subjects = book.get("subjects") or []
                bookshelves = book.get("bookshelves") or []

                theme = classify_theme(subjects, bookshelves, languages)
                if theme not in THEME_ID_SET:
                    theme = "general"

                rec = {
                    "id": bid,
                    "title": title,
                    "authors": authors,
                    "languages": languages,
                    "subjects": subjects,
                    "bookshelves": bookshelves,
                    "theme": theme,
                }
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                seen.add(bid)
                counts[theme] = counts.get(theme, 0) + 1
                done += 1

            next_url = data.get("next")
            ck = {"next": next_url, "done": done, "page": page, "updatedAt": int(time.time())}
            save_json(checkpoint_path, ck)
            save_json(stats_path, {"counts": counts, "done": done, "page": page, "max_books": args.max_books})
            # Persist seen list occasionally (every page for crash safety, but it's small enough)
            save_json(seen_path, sorted(seen))

            print(f"page {page} done {done} next={next_url}", flush=True)
            time.sleep(args.sleep)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
