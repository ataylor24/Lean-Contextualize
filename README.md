# Lean-Contextualize
Lean-Contextualize builds dependency-aware Lean contexts from Jixia symbol/decl graphs. It resolves constructors, instances, and wrappers to produce the minimal context required for compiling individual problems. This is designed to enhance dataset generation from custom Lean4 codebases.

Usage:
1) Make sure Jixia and custom Lean project (ex. analysis) lean versions match
2) Run orchestrate_jixia.py to construct the processed 