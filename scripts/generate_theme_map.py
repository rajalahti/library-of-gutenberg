#!/usr/bin/env python3
"""Generate Project Gutenberg theme map from Gutendex metadata.

Goal: produce a stable mapping bookId -> themeId (and stats), suitable for baking into the app.

This script paginates Gutendex /books and uses only fields needed for classification:
- id
- subjects
- bookshelves
- languages

Outputs:
- data/theme-map/themeByBookId.v1.json  (array index = bookId, value = themeId)
- data/theme-map/stats.v1.json          (counts, unknowns, examples)
- data/theme-map/checkpoint.json        (resume)

Usage:
  python3 scripts/generate_theme_map.py --max-books 70000 --out data/theme-map
  python3 scripts/generate_theme_map.py --max-books 2000 --out data/theme-map --reset

Notes:
- Gutendex has rate limits; we use conservative pacing and retry.
- Classification is heuristic; tune THEME_RULES to taste.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import urllib.request
import urllib.error

GUTENDEX_BASE = "https://gutendex.com/books/"

THEMES = [
    # Keep IDs stable once you start using the map.
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

# Ordered rules: first match wins.
# We match against a combined text of subjects + bookshelves.
THEME_RULES: List[Tuple[str, List[str]]] = [
    ("children", [
        r"\bchildren\b",
        r"juvenile",
        r"\bfairy tales\b",
        r"\bchild(?:ren)?'s\b",
    ]),
    ("horror", [
        r"\bhorror\b",
        r"\bghost\b",
        r"\bvampire\b",
        r"\bwerewolf\b",
        r"\bgothic\b",
        r"\bhaunted\b",
        r"\boccult\b",
        r"\bdevil\b",
        r"\bwitch\b",
    ]),
    ("mystery", [
        r"\bmystery\b",
        r"\bdetective\b",
        r"\bcrime\b",
        r"\bpolice\b",
        r"\bthriller\b",
    ]),
    ("scifi", [
        r"science fiction",
        r"\bsci-?fi\b",
        r"\bspace\b",
        r"\btime travel\b",
        r"\baliens?\b",
        r"\brobots?\b",
    ]),
    ("fantasy", [
        r"\bfantasy\b",
        r"\bmyth\b",
        r"\bmythology\b",
        r"\blegends?\b",
        r"\bfairy\b",
        r"\bdragons?\b",
    ]),
    ("romance", [
        r"\bromance\b",
        r"\blove\b",
        r"\bcourtship\b",
    ]),
    ("adventure", [
        r"\badventure\b",
        r"\bsea stories\b",
        r"\bpirates?\b",
        r"\bwestern\b",
    ]),
    ("poetry", [
        r"\bpoetry\b",
        r"\bpoems\b",
        r"\bsonnets\b",
    ]),
    ("drama", [
        r"\bdrama\b",
        r"\bplays?\b",
        r"\btheatre\b",
    ]),
    ("history", [
        r"\bhistory\b",
        r"\bwar\b",
        r"\bmilitary\b",
        r"\brevolution\b",
    ]),
    ("religion", [
        r"\breligion\b",
        r"\bchristian\b",
        r"\bbible\b",
        r"\btheology\b",
        r"\bsermons\b",
    ]),
    ("philosophy", [
        r"\bphilosophy\b",
        r"\bethics\b",
        r"\blogic\b",
        r"\bmetaphysics\b",
    ]),
    ("science", [
        r"\bscience\b",
        r"\bphysics\b",
        r"\bchemistry\b",
        r"\bbiology\b",
        r"\bmathematics\b",
        r"\bengineering\b",
        r"\btechnology\b",
    ]),
    ("biography", [
        r"\bbiograph\b",
        r"\bautobiograph\b",
        r"\bdiaries\b",
        r"\bletters\b",
        r"\bcorrespondence\b",
        r"\bmemoirs\b",
    ]),
    ("travel", [
        r"\btravel\b",
        r"\bvoyage\b",
        r"\bgeography\b",
        r"\bexploration\b",
    ]),
]

# Precompile regex for speed
_COMPILED_RULES: List[Tuple[str, List[re.Pattern[str]]]] = [
    (tid, [re.compile(pat, flags=re.IGNORECASE) for pat in pats])
    for tid, pats in THEME_RULES
]


def http_get_json(url: str, timeout: int = 30) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "library-of-gutenberg-theme-map/0.1 (local dev)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        return json.loads(data.decode("utf-8"))


def safe_lower_join(items: Any) -> str:
    if not items:
        return ""
    if isinstance(items, list):
        return "\n".join(str(x) for x in items).lower()
    return str(items).lower()


def classify_theme(subjects: List[str], bookshelves: List[str], languages: List[str]) -> str:
    text = (safe_lower_join(subjects) + "\n" + safe_lower_join(bookshelves)).strip()

    # Quick language-based bucketing could go here later; for now we ignore.

    for theme_id, patterns in _COMPILED_RULES:
        for pat in patterns:
            if pat.search(text):
                return theme_id

    # Fallback
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
    ap.add_argument("--out", default="data/theme-map", help="Output directory")
    ap.add_argument("--max-books", type=int, default=70000, help="Max Gutenberg IDs to map")
    ap.add_argument("--reset", action="store_true", help="Reset checkpoint and outputs")
    ap.add_argument("--sleep", type=float, default=0.35, help="Sleep between requests")
    ap.add_argument("--max-pages", type=int, default=0, help="Stop after N pages (0=all)")
    args = ap.parse_args()

    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)

    checkpoint_path = os.path.join(out_dir, "checkpoint.json")
    map_path = os.path.join(out_dir, "themeByBookId.v1.json")
    stats_path = os.path.join(out_dir, "stats.v1.json")

    if args.reset:
        for p in [checkpoint_path, map_path, stats_path]:
            if os.path.exists(p):
                os.remove(p)

    # themeByBookId[bookId] = themeId. Keep index 0 unused for direct indexing.
    if os.path.exists(map_path):
        with open(map_path, "r", encoding="utf-8") as f:
            theme_by_id: List[Optional[str]] = json.load(f)
    else:
        theme_by_id = [None] * (args.max_books + 1)

    ck = load_checkpoint(checkpoint_path)
    next_url = ck.get("next") or GUTENDEX_BASE
    done = int(ck.get("done") or 0)

    counts: Dict[str, int] = {t["id"]: 0 for t in THEMES}
    unknowns: int = 0
    examples: Dict[str, List[int]] = {t["id"]: [] for t in THEMES}

    # Seed counts from existing map (if resuming)
    for bid in range(1, min(len(theme_by_id), args.max_books + 1)):
        tid = theme_by_id[bid]
        if tid in counts:
            counts[tid] += 1
        elif tid is not None:
            unknowns += 1

    page = 0
    retries = 0

    print(f"Starting: max_books={args.max_books} next={next_url} done={done}")

    while next_url:
        page += 1
        if args.max_pages and page > args.max_pages:
            print(f"Stopping at max_pages={args.max_pages}")
            break

        try:
            data = http_get_json(next_url)
            retries = 0
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            retries += 1
            wait = min(30.0, 1.5 ** retries)
            print(f"WARN fetch failed ({type(e).__name__}): {e}. retry {retries} in {wait:.1f}s")
            time.sleep(wait)
            if retries > 10:
                raise
            continue

        results = data.get("results") or []
        for book in results:
            bid = int(book.get("id") or 0)
            if bid <= 0 or bid > args.max_books:
                continue
            if theme_by_id[bid] is not None:
                continue

            subjects = book.get("subjects") or []
            bookshelves = book.get("bookshelves") or []
            languages = book.get("languages") or []

            tid = classify_theme(subjects, bookshelves, languages)
            if tid not in THEME_ID_SET:
                tid = "general"

            theme_by_id[bid] = tid
            counts[tid] = counts.get(tid, 0) + 1
            if len(examples[tid]) < 8:
                examples[tid].append(bid)
            done += 1

        # Progress + checkpoint
        next_url = data.get("next")
        ck = {"next": next_url, "done": done, "page": page, "updatedAt": int(time.time())}
        save_json(checkpoint_path, ck)

        # Persist map frequently (safe for long runs; cheap insurance against SIGKILL)
        save_json(map_path, theme_by_id)
        save_json(stats_path, {"counts": counts, "examples": examples, "done": done, "max_books": args.max_books, "page": page})
        print(f"page {page} done {done} next={next_url}", flush=True)

        # Exit if fully filled
        if all(theme_by_id[bid] is not None for bid in range(1, args.max_books + 1)):
            print("All mapped")
            next_url = None
            break

        time.sleep(args.sleep)

    save_json(map_path, theme_by_id)
    save_json(stats_path, {"counts": counts, "examples": examples, "done": done, "max_books": args.max_books, "page": page})
    print(f"Wrote: {map_path}")
    print(f"Wrote: {stats_path}")

    # report missing
    missing = [i for i in range(1, args.max_books + 1) if theme_by_id[i] is None]
    print(f"Missing: {len(missing)}")
    if missing[:20]:
        print(f"Missing sample: {missing[:20]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
