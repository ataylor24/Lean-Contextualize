# Lean-Contextualize
Lean-Contextualize builds dependency-aware Lean contexts from Jixia symbol/decl graphs. It resolves constructors, instances, and wrappers to produce the minimal context required for compiling individual problems. This codebase designed to enhance dataset generation from custom Lean4 codebases.

Usage:
1) Make sure Jixia and custom Lean project (ex. analysis) lean versions match.
2) Run orchestrate_jixia.py to construct the processed analysis files.
3) Run build_context.py to perform type and value resolution and generate the initial version of the generated context JSONL.
4) Verify each row.
5) Run second_pass_api_check.py to query the Open-AI API to correct errors (default: GPT-5-Medium).
