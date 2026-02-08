#!/usr/bin/env python3
"""Generate a 7-floor library layout + shelf section tags from raw Gutendex JSONL.

Inputs:
  data/book-meta/bookMetaById.v1.jsonl   (one JSON object per book)

Outputs (default out dir: data/layout):
  floors7.v1.json
    - floors (7) with roomStart/roomCount/capacity/bookCount
    - subcategories per floor (top N + Other + RELATED buckets)

  slots7.v1.json
    - for each floor: arrays length=capacity:
        bookIdBySlot[] (ints; may include repeats to fill slack)
        subIdBySlot[]  (small strings)

  primaryLocationByBookId.v1.json
    - bookId -> { room, wall, shelf, vol, floorId, subId }
      (first occurrence in slots7)

  tags/room-<NNN>.v1.json
    - shelf section tags per room for fast frontend loading
      { room, tags:[{wall,shelf,volStart,label,subId}] }

Notes:
- Because total capacity (rooms*640) exceeds total books, we must fill slack.
  We do this by repeating books from related floors (fillFrom chain),
  and marking those slots as RELATED:<floor> subcategories.
- Books may therefore appear multiple times in the world; teleport/search uses
  the primary (first) location.
- Update-friendly: regenerate anytime from raw JSONL; books can move.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

BOOKS_PER_ROOM = 640
BOOKS_PER_SHELF = 32
SHELVES_PER_WALL = 5
WALLS_PER_ROOM = 4

assert BOOKS_PER_ROOM == BOOKS_PER_SHELF * SHELVES_PER_WALL * WALLS_PER_ROOM


def norm_bookshelf(bs: str) -> str:
    bs = bs.strip()
    bs = re.sub(r"^Category:\s*", "", bs, flags=re.IGNORECASE)
    bs = re.sub(r"\s+", " ", bs)
    return bs


def any_match(patterns: Iterable[re.Pattern[str]], text: str) -> bool:
    return any(p.search(text) for p in patterns)


def join_text(book: Dict[str, Any]) -> str:
    parts: List[str] = []
    parts.extend(book.get("bookshelves") or [])
    parts.extend(book.get("subjects") or [])
    return "\n".join(str(x) for x in parts).lower()


# Floors (7) with library-like names
FLOORS = [
    {"id": "history_war", "label": "History & War"},
    {"id": "literature_fiction", "label": "Literature & Fiction"},
    {"id": "crime_mystery_gothic", "label": "Crime, Mystery & Gothic"},
    {"id": "scifi_fantasy", "label": "Sci‑Fi & Fantasy"},
    {"id": "children_ya", "label": "Children & YA"},
    {"id": "poetry_drama", "label": "Poetry & Drama"},
    {"id": "nonfiction_thought", "label": "Non‑fiction & Thought"},
]
FLOOR_BY_ID = {f["id"]: f for f in FLOORS}

# Related fill chain, used only to fill slack slots.
FILL_CHAIN = {
    "history_war": ["literature_fiction"],
    "literature_fiction": ["history_war"],
    "crime_mystery_gothic": ["literature_fiction", "scifi_fantasy"],
    "scifi_fantasy": ["literature_fiction"],
    "children_ya": ["literature_fiction"],
    "poetry_drama": ["literature_fiction"],
    "nonfiction_thought": ["history_war", "literature_fiction"],
}

# Floor classification patterns (coarse)
P = lambda *xs: [re.compile(x, re.IGNORECASE) for x in xs]

FLOOR_RULES: List[Tuple[str, List[re.Pattern[str]]]] = [
    ("children_ya", P(r"children", r"juvenile")),
    ("poetry_drama", P(r"\bpoetry\b", r"\bpoems\b", r"plays/films/dramas", r"\bdrama\b", r"\btheatre\b")),
    ("scifi_fantasy", P(r"science-?fiction", r"sci-?fi", r"fantasy", r"mythology", r"legends?", r"folklore", r"fairy tales")),
    ("crime_mystery_gothic", P(r"crime", r"thrillers?", r"mystery", r"detective", r"horror", r"gothic", r"ghost", r"vampire", r"occult", r"haunted")),
    ("history_war", P(r"\bhistory\b", r"\bwar\b", r"military", r"revolution", r"history -")),
    ("nonfiction_thought", P(r"philosophy", r"ethics", r"religion", r"spiritual", r"theology", r"science", r"physics", r"chemistry", r"biology", r"mathematics", r"engineering", r"technology", r"how to", r"travel", r"voyage", r"geography", r"biograph", r"autobiograph", r"memoirs")),
    # default literature_fiction
]


def classify_floor(book: Dict[str, Any]) -> str:
    txt = join_text(book)
    for floor_id, pats in FLOOR_RULES:
        if any_match(pats, txt):
            return floor_id
    return "literature_fiction"


def choose_subcategory(book: Dict[str, Any], floor_id: str) -> str:
    # Use the first (normalized) bookshelf as default subcategory
    shelves = [norm_bookshelf(x) for x in (book.get("bookshelves") or []) if str(x).strip()]
    subjects = [str(x) for x in (book.get("subjects") or []) if str(x).strip()]

    # Heuristic: pick the most specific shelf-like label
    for bs in shelves:
        # Ignore extremely broad labels
        if bs.lower() in {"novels", "short stories"} and floor_id != "literature_fiction":
            continue
        return bs

    # Fallback: subject keyword buckets
    subj_text = "\n".join(subjects).lower()
    if floor_id == "history_war":
        if "american" in subj_text:
            return "History - American"
        if "europe" in subj_text:
            return "History - European"
        if "brit" in subj_text:
            return "History - British"
        if "war" in subj_text or "military" in subj_text:
            return "History - Warfare"
        return "History - Other"

    if floor_id == "crime_mystery_gothic":
        if "detective" in subj_text:
            return "Detective Fiction"
        if "gothic" in subj_text or "horror" in subj_text:
            return "Gothic & Horror"
        return "Crime & Mystery"

    if floor_id == "scifi_fantasy":
        if "science fiction" in subj_text or "space" in subj_text or "time travel" in subj_text:
            return "Science Fiction"
        if "myth" in subj_text or "legend" in subj_text or "folklore" in subj_text:
            return "Mythology & Folklore"
        return "Fantasy"

    if floor_id == "children_ya":
        if "fairy" in subj_text:
            return "Fairy Tales"
        if "animals" in subj_text or "birds" in subj_text:
            return "Animals & Nature"
        return "Children"

    if floor_id == "poetry_drama":
        if "plays" in subj_text or "drama" in subj_text or "theatre" in subj_text:
            return "Drama"
        return "Poetry"

    if floor_id == "nonfiction_thought":
        if "philosophy" in subj_text or "ethics" in subj_text:
            return "Philosophy"
        if "religion" in subj_text or "theology" in subj_text:
            return "Religion"
        if "travel" in subj_text or "geography" in subj_text:
            return "Travel"
        if "biograph" in subj_text or "memoir" in subj_text:
            return "Biography"
        return "Science & Reference"

    # literature_fiction
    if shelves:
        return shelves[0]
    return "Other"


def stable_shuffle(ids: List[int], seed: str) -> List[int]:
    # Deterministic sort by hash-like key without heavy crypto
    def key(x: int) -> int:
        h = 2166136261
        s = f"{seed}:{x}"
        for ch in s:
            h ^= ord(ch)
            h = (h * 16777619) & 0xFFFFFFFF
        return h

    return sorted(ids, key=key)


def slot_to_location(slot: int) -> Tuple[int, int, int, int]:
    # Returns (roomOffset, wall, shelf, vol)
    room_offset = slot // BOOKS_PER_ROOM
    in_room = slot % BOOKS_PER_ROOM
    wall = in_room // (BOOKS_PER_SHELF * SHELVES_PER_WALL)
    in_wall = in_room % (BOOKS_PER_SHELF * SHELVES_PER_WALL)
    shelf = in_wall // BOOKS_PER_SHELF
    vol = in_wall % BOOKS_PER_SHELF
    return room_offset, wall, shelf, vol


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/book-meta/bookMetaById.v1.jsonl")
    ap.add_argument("--out", dest="out", default="data/layout")
    ap.add_argument("--top-subs", type=int, default=8)
    ap.add_argument("--min-sub-books", type=int, default=200, help="Merge subcategories smaller than this into Other")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)

    # 1) Load + classify
    floor_books: Dict[str, List[int]] = {f["id"]: [] for f in FLOORS}
    sub_by_book: Dict[int, str] = {}
    floor_by_book: Dict[int, str] = {}
    sub_counts_by_floor: Dict[str, Counter[str]] = {f["id"]: Counter() for f in FLOORS}

    with open(args.inp, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            book = json.loads(line)
            bid = int(book.get("id") or 0)
            if bid <= 0:
                continue
            floor_id = classify_floor(book)
            sub = choose_subcategory(book, floor_id)
            floor_books[floor_id].append(bid)
            floor_by_book[bid] = floor_id
            sub_by_book[bid] = sub
            sub_counts_by_floor[floor_id][sub] += 1

    # 2) Decide official subcategories per floor (top N + Other)
    official_subs: Dict[str, List[str]] = {}
    for floor_id in floor_books:
        items = list(sub_counts_by_floor[floor_id].items())
        items.sort(key=lambda kv: (-kv[1], kv[0]))
        subs: List[str] = []
        for sub, cnt in items:
            if cnt < args.min_sub_books:
                continue
            subs.append(sub)
            if len(subs) >= args.top_subs:
                break
        official_subs[floor_id] = subs

    # 3) Compute rooms per floor and ranges
    floors_out = []
    room_start = 0
    rooms_total = 0

    floor_stats: Dict[str, Dict[str, Any]] = {}
    for fl in FLOORS:
        fid = fl["id"]
        count = len(floor_books[fid])
        rooms = max(1, math.ceil(count / BOOKS_PER_ROOM))
        cap = rooms * BOOKS_PER_ROOM
        floors_out.append({
            "id": fid,
            "label": fl["label"],
            "roomStart": room_start,
            "roomCount": rooms,
            "bookCount": count,
            "capacity": cap,
            "fillFrom": FILL_CHAIN.get(fid, []),
            "subcategories": [{"id": s, "label": s, "count": sub_counts_by_floor[fid][s]} for s in official_subs[fid]] + [{"id": "Other", "label": "Other", "count": count - sum(sub_counts_by_floor[fid][s] for s in official_subs[fid])}],
        })
        floor_stats[fid] = {"roomStart": room_start, "roomCount": rooms, "capacity": cap}
        room_start += rooms
        rooms_total += rooms

    # 4) Build slots per floor: block by subcategory, shuffle within blocks, fill slack via related floors by repeating
    slots_out: Dict[str, Dict[str, Any]] = {}
    primary_loc: Dict[str, Any] = {}

    # Precompute donor pools per floor (deterministic order)
    donor_pool: Dict[str, List[int]] = {}
    for fid in floor_books:
        donor_pool[fid] = stable_shuffle(floor_books[fid].copy(), seed=f"donor:{fid}")

    for fl in FLOORS:
        fid = fl["id"]
        cap = floor_stats[fid]["capacity"]
        subs = official_subs[fid]

        # bucket book ids
        buckets: Dict[str, List[int]] = defaultdict(list)
        for bid in floor_books[fid]:
            sub = sub_by_book[bid]
            if sub not in subs:
                sub = "Other"
            buckets[sub].append(bid)

        # Build ordered list of sub blocks: use chosen subs in order, then Other
        ordered_subs = subs + ["Other"]
        bookIdBySlot: List[int] = []
        subIdBySlot: List[str] = []

        for sub in ordered_subs:
            ids = buckets.get(sub, [])
            ids = stable_shuffle(ids, seed=f"{fid}:{sub}")
            for bid in ids:
                bookIdBySlot.append(bid)
                subIdBySlot.append(sub)

        # Fill slack if needed by repeating books from related floors
        if len(bookIdBySlot) < cap:
            need = cap - len(bookIdBySlot)
            chain = FILL_CHAIN.get(fid, [])
            if not chain:
                chain = ["literature_fiction"] if fid != "literature_fiction" else ["history_war"]
            fill_ids: List[int] = []
            fill_subs: List[str] = []

            cursor = 0
            donor_cursor: Dict[str, int] = defaultdict(int)
            # Round-robin donors
            while need > 0:
                donor = chain[cursor % len(chain)]
                cursor += 1
                pool = donor_pool.get(donor) or []
                if not pool:
                    continue
                # take deterministically by cycling through each donor pool
                idx = donor_cursor[donor] % len(pool)
                donor_cursor[donor] += 1
                take_bid = pool[idx]
                fill_ids.append(take_bid)
                fill_subs.append(f"RELATED:{donor}")
                need -= 1

            bookIdBySlot.extend(fill_ids)
            subIdBySlot.extend(fill_subs)

        # Truncate if somehow over
        bookIdBySlot = bookIdBySlot[:cap]
        subIdBySlot = subIdBySlot[:cap]

        slots_out[fid] = {
            "floorId": fid,
            "capacity": cap,
            "bookIdBySlot": bookIdBySlot,
            "subIdBySlot": subIdBySlot,
        }

        # Build primary location mapping (first occurrence wins)
        room_start = floor_stats[fid]["roomStart"]
        for slot, bid in enumerate(bookIdBySlot):
            if str(bid) in primary_loc:
                continue
            room_off, wall, shelf, vol = slot_to_location(slot)
            primary_loc[str(bid)] = {
                "room": room_start + room_off,
                "wall": wall,
                "shelf": shelf,
                "volume": vol,
                "floorId": fid,
                "subId": subIdBySlot[slot],
            }

    

    # 5) Generate per-room shelf section tags for frontend (small files)
    tags_dir = os.path.join(args.out, "tags")
    os.makedirs(tags_dir, exist_ok=True)

    # Build tags: for each room (global room index), for each (wall,shelf), place tags at volStart where subId changes.
    # We only create tags for walls 0..3 and shelves 0..4 that exist in room mapping.
    room_tags: Dict[int, List[Dict[str, Any]]] = defaultdict(list)

    for fl in FLOORS:
        fid = fl["id"]
        floor_room_start = floor_stats[fid]["roomStart"]
        rooms = floor_stats[fid]["roomCount"]
        sub_ids = slots_out[fid]["subIdBySlot"]

        for room_off in range(rooms):
            global_room = floor_room_start + room_off
            room_base_slot = room_off * BOOKS_PER_ROOM

            # For each wall and shelf, scan vols 0..31
            for wall in range(WALLS_PER_ROOM):
                for shelf in range(SHELVES_PER_WALL):
                    prev_sub: Optional[str] = None
                    for vol in range(BOOKS_PER_SHELF):
                        slot = room_base_slot + wall * (BOOKS_PER_SHELF * SHELVES_PER_WALL) + shelf * BOOKS_PER_SHELF + vol
                        sub = sub_ids[slot]
                        if vol == 0 or sub != prev_sub:
                            room_tags[global_room].append({
                                "wall": wall,
                                "shelf": shelf,
                                "volStart": vol,
                                "subId": sub,
                                "label": sub,
                            })
                        prev_sub = sub

    # Write tags per room
    for room_idx, tags in room_tags.items():
        out_path = os.path.join(tags_dir, f"room-{room_idx:03d}.v1.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"room": room_idx, "tags": tags}, f, ensure_ascii=False)

    floors_path = os.path.join(args.out, "floors7.v1.json")
    slots_path = os.path.join(args.out, "slots7.v1.json")
    primary_path = os.path.join(args.out, "primaryLocationByBookId.v1.json")

    with open(floors_path, "w", encoding="utf-8") as f:
        json.dump({"booksPerRoom": BOOKS_PER_ROOM, "roomsTotal": rooms_total, "floors": floors_out}, f, ensure_ascii=False, indent=2)

    with open(slots_path, "w", encoding="utf-8") as f:
        json.dump(slots_out, f, ensure_ascii=False)

    with open(primary_path, "w", encoding="utf-8") as f:
        json.dump(primary_loc, f, ensure_ascii=False)

    print("Wrote:", floors_path)
    print("Wrote:", slots_path)
    print("Wrote:", primary_path)
    print("roomsTotal:", rooms_total)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
