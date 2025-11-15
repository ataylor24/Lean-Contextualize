# Agentic Jixia Workflow

This module mirrors the preprocessing logic from `src/main.py` but surfaces the
results as tool-like objects that can be consumed by an iterative agent loop.

## Quick start

```bash
python3 src/agentic_jixia/workflow.py --limit 3
```

The command above loads the cached Jixia analysis, prepares up to three tasks,
and prints a compact preview that includes the dependency files and theorem
text for each task.

## Key components

* `FileLookupTool` – lists dependency Lean files for a section and streams their
  contents on demand (or via a truncated snapshot).
* `DeclarationLookupTool` / `SymbolLookupTool` – wrap the global tables created
  by `preprocess_lean_analysis` for instant access to declarations or symbols.
* `ReferenceLookupTool` – performs a bounded BFS over type/value references so
  the agent can pull just the minimum set of supporting items it needs.
* `AgenticJixiaWorkflow` – orchestrates preprocessing, produces `AgenticTask`
  objects, and associates the shared toolset with each theorem.

Each `AgenticTask` exposes the theorem metadata, the structured toolset, and a
`reference_summary` that records the names touched during the bounded reference
traversal. This keeps the agent close to the data layout that already powers
`src/main.py` while enabling iterative compilation/repair loops.
