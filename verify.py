#!/usr/bin/env python3
"""
compile_jsonl_lean.py

Read a JSONL of Lean snippets and compile each one with the `lean` binary.
Assumes each JSONL line is either:
  - a dict with a "content" field containing Lean code, or
  - a dict with a "code" field containing Lean code, or
  - a raw JSON string containing Lean code.

By default this uses `lean --make` on a temp Main.lean per snippet.
You can force specific imports to appear at the VERY TOP of the file with --force-imports,
e.g., --force-imports "Init,Mathlib.Tactic".
"""

import argparse
import json
import sys
import tempfile
import shutil
from pathlib import Path
import subprocess
from typing import List, Dict, Any
import time
import math

LAKE_PROJECT = Path("/Users/alextaylor/Desktop/lean_prover/analysis/analysis")

def load_jsonl(path: str) -> List[Any]:
    rows: List[Any] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows

def extract_code(entry: Any) -> str:
    if isinstance(entry, dict):
        if "content" in entry and isinstance(entry["content"], str):
            return entry["content"]
        if "code" in entry and isinstance(entry["code"], str):
            return entry["code"]
        # fallthrough: stringify?
        raise ValueError("JSON object missing 'content' or 'code' string field.")
    if isinstance(entry, str):
        return entry
    raise ValueError("Unsupported JSONL line: must be dict or string.")

def build_source(body: str, imports: List[str]) -> str:
    header = ""
    if imports:
        header = "\n".join(f"import {imp.strip()}" for imp in imports if imp.strip()) + "\n\n"
    # Do NOT try to keep existing imports above header; we want ours at file start if requested.
    return header + body

def compile_with_lean(lean_exe: str, src_path: Path, timeout: int) -> subprocess.CompletedProcess:
    # Prefer `lean --make` so transitive imports (on LEAN_PATH) get built/checked.
    # Run from the snippet directory to improve relative import resolution.
    # Use Lake environment so Mathlib and other deps resolve.
    cmd_make = ["lake", "env", lean_exe, "--make", str(src_path)]
    cmd_plain = ["lake", "env", lean_exe, str(src_path)]
    run_cwd = str(LAKE_PROJECT)
    try:
        proc = subprocess.run(
            cmd_make,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=run_cwd,
            timeout=timeout if timeout > 0 else None,
        )
        if proc.returncode == 0:
            return proc
        # Fallback: try plain `lean` (no --make) which can be more permissive for standalone files
        proc2 = subprocess.run(
            cmd_plain,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=run_cwd,
            timeout=timeout if timeout > 0 else None,
        )
        return proc2
    except subprocess.TimeoutExpired as e:
        # Synthesize a CompletedProcess-like object
        cp = subprocess.CompletedProcess(cmd_make, returncode=124, stdout=e.stdout or "", stderr=e.stderr or "timeout")
        return cp

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", required=True, help="Path to input JSONL file.")
    ap.add_argument("--lean", default="lean", help="Path to the Lean executable (default: 'lean').")
    ap.add_argument("--timeout", type=int, default=120, help="Per-snippet compile timeout (seconds).")
    ap.add_argument(
        "--force-imports",
        default="Init",
        help="Comma-separated imports to force at file top, e.g. 'Init,Mathlib.Tactic'."
    )
    ap.add_argument("--out-json", default="", help="Optional path to write a JSON results report.")
    ap.add_argument("--keep-tmp", action="store_true", help="Keep temporary directories on disk for inspection.")
    args = ap.parse_args()

    rows = load_jsonl(args.jsonl)
    imports = [s.strip() for s in args.force_imports.split(",")] if args.force_imports else []

    # Prepare output structure
    results: List[Dict[str, Any]] = []

    # We can reuse one temp dir for speed unless --keep-tmp
    time_prefix = math.floor(time.time())
    base_tmp = tempfile.mkdtemp(prefix=f"lean_compile_{time_prefix}_", dir=str(LAKE_PROJECT))
    base_tmp_path = Path(base_tmp)

    try:
        total = len(rows)
        ok = 0

        for i, entry in enumerate(rows):
            try:
                code = extract_code(entry)
                index = entry["index"]
            except Exception as e:
                results.append({
                    "index": index,
                    "status": "extract_failed",
                    "error": str(e),
                })
                continue

            # Create a per-snippet directory with a Main.lean
            snip_dir = base_tmp_path / f"snippet_{index}"
            snip_dir.mkdir(parents=True, exist_ok=True)
            main_lean = snip_dir / "Main.lean"

            src_text = build_source(code, imports)
            main_lean.write_text(src_text, encoding="utf-8")

            proc = compile_with_lean(args.lean, main_lean, args.timeout)

            status = "ok" if proc.returncode == 0 else "error"
            if status == "ok":
                ok += 1

            results.append({
                "index": index,
                "src_text": src_text,
                "status": status,
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "tmp_dir": str(snip_dir) if args.keep_tmp else None,
            })

            # Print a compact line to console
            tag = "PASS" if status == "ok" else f"FAIL({proc.returncode})"
            print(f"[{i:04d}] {tag}")

        # Summary
        print("\n--- Summary ---")
        print(f"Total: {total}")
        print(f"Pass : {ok}")
        print(f"Fail : {total - ok}")

        if args.out_json:
            # Redact gigantic outputs a bit
            out = []
            for r in results:
                ro = dict(r)
                if isinstance(ro.get("stdout"), str) and len(ro["stdout"]) > 5000:
                    ro["stdout"] = ro["stdout"][:5000] + "\n...[truncated]..."
                if isinstance(ro.get("stderr"), str) and len(ro["stderr"]) > 5000:
                    ro["stderr"] = ro["stderr"][:5000] + "\n...[truncated]..."
                out.append(ro)
            Path(args.out_json).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    finally:
        if not args.keep_tmp:
            try:
                shutil.rmtree(base_tmp_path, ignore_errors=True)
            except Exception:
                pass

if __name__ == "__main__":
    main()
