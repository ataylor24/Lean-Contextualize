from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

from agentic_jixia.toolbox import (
    DeclarationLookupTool,
    FileLookupTool,
    ReferenceLookupTool,
    ReferenceResult,
    SymbolLookupTool,
)
from jixia_lean_utils import preprocess_lean_analysis, process_snippet
from utils import load_json, sort_by_section

# Ensure the src root (where ``main.py`` lives) is importable when this module
# is executed directly via ``python src/agentic_jixia/workflow.py``.
SRC_ROOT = Path(__file__).resolve().parents[1]
if str(SRC_ROOT) not in sys.path:
    sys.path.append(str(SRC_ROOT))

from main import preprocess_baseline_data, construct_jixia_table  # type: ignore


NameTuple = Tuple[str, ...]


@dataclass
class AgenticToolset:
    file_lookup: FileLookupTool
    decl_lookup: DeclarationLookupTool
    sym_lookup: SymbolLookupTool
    reference_lookup: ReferenceLookupTool


@dataclass
class AgenticTask:
    section: str
    index: int
    fqn: NameTuple
    content: str
    toolset: AgenticToolset
    reference_summary: ReferenceResult

    def as_prompt_seed(self, max_file_chars: int = 20_000) -> Dict[str, object]:
        """
        Produce a serializable view of the task that can seed an LLM dialogue.
        File content is truncated via ``max_file_chars`` to keep prompts bounded.
        """
        return {
            "section": self.section,
            "index": self.index,
            "fqn": ".".join(self.fqn),
            "content": self.content,
            "dependency_files": self.toolset.file_lookup.list_files(),
            "dependency_snippet": self.toolset.file_lookup.snapshot(max_chars=max_file_chars),
            "reference_seeds": [".".join(name) for name in self.reference_summary.seeds],
        }


class AgenticJixiaWorkflow:
    """
    Orchestrates the exact preprocessing pipeline from ``src/main.py`` but exposes every
    per-theorem task as a bundle of lookup tools that can be consumed by an agent loop.
    """

    def __init__(
        self,
        *,
        force_reprocess: bool = False,
        reference_depth: int = 2,
        reference_budget: int = 24,
    ):
        self.reference_depth = reference_depth
        self.reference_budget = reference_budget

        jixia_table = construct_jixia_table()
        (
            self.mapped_lean_analysis_data,
            global_symbol_table,
            self.global_dependency_table,
        ) = preprocess_lean_analysis(jixia_table, force_reprocess=force_reprocess)
        self.aggregated_baseline_data = preprocess_baseline_data(force_reprocess=force_reprocess)

        self._decl_lookup = DeclarationLookupTool(global_symbol_table)
        self._sym_lookup = SymbolLookupTool(global_symbol_table)
        self._reference_lookup = ReferenceLookupTool(self._sym_lookup)

    def iter_tasks(
        self,
        *,
        sections: Optional[Sequence[str]] = None,
        limit: Optional[int] = None,
    ) -> Iterator[AgenticTask]:
        selected_sections = set(sections) if sections else None
        produced = 0

        for section in sort_by_section(self.aggregated_baseline_data.keys()):
            if selected_sections and section not in selected_sections:
                continue

            section_payload = self.aggregated_baseline_data[section]
            if section not in self.mapped_lean_analysis_data:
                continue

            dependency_paths = self.mapped_lean_analysis_data[section]["dependency_set"]
            file_lookup = FileLookupTool(dependency_paths)

            toolset = AgenticToolset(
                file_lookup=file_lookup,
                decl_lookup=self._decl_lookup,
                sym_lookup=self._sym_lookup,
                reference_lookup=self._reference_lookup,
            )

            for content in section_payload:
                idx = int(content["idx"])
                fqn = self._ensure_name(section, idx, content)
                reference_result = toolset.reference_lookup.collect(
                    fqn, max_depth=self.reference_depth, budget=self.reference_budget
                )

                yield AgenticTask(
                    section=section,
                    index=idx,
                    fqn=fqn,
                    content=content["content"],
                    toolset=toolset,
                    reference_summary=reference_result,
                )

                produced += 1
                if limit and produced >= limit:
                    return

    def collect_tasks(
        self,
        *,
        sections: Optional[Sequence[str]] = None,
        limit: Optional[int] = None,
    ) -> List[AgenticTask]:
        return list(self.iter_tasks(sections=sections, limit=limit))

    def _ensure_name(self, section: str, idx: int, content: Dict[str, object]) -> NameTuple:
        """
        Guarantee that each baseline entry has a ground-truth FQN. If missing,
        rerun ``process_snippet`` to regenerate the declaration JSON.
        """
        name = content.get("name")
        if name:
            return tuple(name)

        decl_path = process_snippet(content["content"], section, idx)
        decl_json = load_json(decl_path)
        resolved_name = tuple(decl_json[0]["name"])
        content["name"] = list(resolved_name)
        return resolved_name


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview the agent-ready tasks built from the Jixia workflow."
    )
    parser.add_argument("--limit", type=int, default=5, help="Maximum tasks to preview.")
    parser.add_argument(
        "--section",
        action="append",
        help="Restrict to specific Section_* identifiers (can be repeated).",
    )
    parser.add_argument("--force-reprocess", action="store_true", help="Bypass caches.")
    parser.add_argument("--reference-depth", type=int, default=2)
    parser.add_argument("--reference-budget", type=int, default=24)
    parser.add_argument(
        "--max-file-chars",
        type=int,
        default=10_000,
        help="How many characters of dependency text to include in the preview.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = _build_cli()
    args = parser.parse_args(argv)

    workflow = AgenticJixiaWorkflow(
        force_reprocess=bool(args.force_reprocess),
        reference_depth=args.reference_depth,
        reference_budget=args.reference_budget,
    )
    tasks = workflow.collect_tasks(sections=args.section, limit=args.limit)

    for task in tasks:
        seed = task.as_prompt_seed(max_file_chars=args.max_file_chars)
        print("=" * 40)
        print(f"Section: {seed['section']}  Index: {seed['index']}  FQN: {seed['fqn']}")
        print("- Dependency files:", len(seed["dependency_files"]))
        print("- Snippet preview:")
        print(seed["dependency_snippet"][: args.max_file_chars])
        print("- Theorem:")
        print(task.content.strip())


if __name__ == "__main__":
    main()
