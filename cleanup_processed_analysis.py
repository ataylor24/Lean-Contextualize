#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple


NUMBERED_JSON_PATTERN = re.compile(r"^(?P<stem>.+) (?P<num>\d+)\.json$", re.IGNORECASE)


@dataclass
class DuplicateCandidate:
    directory: str
    base_filename: str
    numbered_filename: str
    number: int
    base_path: str
    numbered_path: str
    is_exact_duplicate: bool | None  # None until compared
    reason: str = ""


def compute_sha256(file_path: str) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def find_numbered_jsons(root: str) -> List[Tuple[str, str]]:
    matches: List[Tuple[str, str]] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            if not filename.lower().endswith(".json"):
                continue
            if NUMBERED_JSON_PATTERN.match(filename):
                matches.append((dirpath, filename))
    return matches


def build_candidates(root: str) -> List[DuplicateCandidate]:
    candidates: List[DuplicateCandidate] = []
    for directory, numbered_filename in find_numbered_jsons(root):
        m = NUMBERED_JSON_PATTERN.match(numbered_filename)
        if not m:
            continue
        stem = m.group("stem")
        num = int(m.group("num"))
        base_filename = f"{stem}.json"
        base_path = os.path.join(directory, base_filename)
        numbered_path = os.path.join(directory, numbered_filename)
        candidates.append(
            DuplicateCandidate(
                directory=directory,
                base_filename=base_filename,
                numbered_filename=numbered_filename,
                number=num,
                base_path=base_path,
                numbered_path=numbered_path,
                is_exact_duplicate=None,
            )
        )
    return candidates


def compare_and_mark(candidates: List[DuplicateCandidate]) -> None:
    for cand in candidates:
        if not os.path.exists(cand.base_path):
            cand.is_exact_duplicate = None
            cand.reason = "base_missing"
            continue
        try:
            if os.path.getsize(cand.base_path) != os.path.getsize(cand.numbered_path):
                cand.is_exact_duplicate = False
                cand.reason = "size_mismatch"
                continue
            h_base = compute_sha256(cand.base_path)
            h_num = compute_sha256(cand.numbered_path)
            cand.is_exact_duplicate = h_base == h_num
            cand.reason = "hash_equal" if cand.is_exact_duplicate else "hash_diff"
        except Exception as e:
            cand.is_exact_duplicate = None
            cand.reason = f"compare_error: {e}"


def main() -> None:
    ap = argparse.ArgumentParser(description="Remove numbered JSON duplicates like 'name 2.json' under processed_analysis.")
    ap.add_argument(
        "--root",
        default="/Users/alextaylor/Desktop/lean_prover/processed_analysis",
        help="Root directory to scan (default: processed_analysis in repo).",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete duplicates. Without this flag, the script only prints what it would do.",
    )
    ap.add_argument(
        "--delete-any-number",
        action="store_true",
        help="Delete numbered files (>=2) even if base is missing or content differs. Use with caution.",
    )
    ap.add_argument(
        "--json-report",
        default="",
        help="Optional path to write a JSON report of candidates and actions.",
    )
    args = ap.parse_args()

    candidates = build_candidates(args.root)
    compare_and_mark(candidates)

    planned_deletes: List[DuplicateCandidate] = []
    skipped: List[DuplicateCandidate] = []

    for cand in candidates:
        # Prefer only removing exact duplicates when base exists
        if cand.is_exact_duplicate is True:
            planned_deletes.append(cand)
        elif args.delete_any_number and cand.number >= 2:
            planned_deletes.append(cand)
        else:
            skipped.append(cand)

    print(f"Found {len(candidates)} numbered JSON files under {args.root}")
    print(f"Would delete {len(planned_deletes)} files; would skip {len(skipped)} files.")

    for cand in planned_deletes:
        print(f"[DEL] {cand.numbered_path} (base: {cand.base_filename}, reason: {cand.reason})")
    for cand in skipped:
        print(f"[SKIP] {cand.numbered_path} (base: {cand.base_filename}, reason: {cand.reason})")

    if args.json_report:
        report = {
            "root": args.root,
            "planned_deletes": [cand.__dict__ for cand in planned_deletes],
            "skipped": [cand.__dict__ for cand in skipped],
        }
        with open(args.json_report, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    if not args.apply:
        print("\nDry run only. Re-run with --apply to delete the planned files.")
        return

    # Perform deletions
    delete_count = 0
    for cand in planned_deletes:
        try:
            os.remove(cand.numbered_path)
            delete_count += 1
        except Exception as e:
            print(f"[ERR] Failed to delete {cand.numbered_path}: {e}")
    print(f"\nDeleted {delete_count} files.")


if __name__ == "__main__":
    main()


