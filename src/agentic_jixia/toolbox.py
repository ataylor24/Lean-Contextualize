from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


NameTuple = Tuple[str, ...]


def _to_name_tuple(name: Sequence[str]) -> NameTuple:
    return tuple(name)


class FileLookupTool:
    """
    Lightweight helper that exposes both the dependency list and file bodies
    for the Analysis textbook modules relevant to a section.
    """

    def __init__(self, dependency_paths: Iterable[str]):
        unique_paths = {str(Path(p)) for p in dependency_paths}
        self._paths: List[str] = sorted(unique_paths)

    def list_files(self) -> List[str]:
        """Return the deterministic list of dependency files backing this task."""
        return list(self._paths)

    def read_file(self, path: str) -> str:
        """Read a specific dependency file on demand."""
        norm = str(Path(path))
        if norm not in self._paths:
            raise FileNotFoundError(f"{norm} is not registered for this task")
        return Path(norm).read_text(encoding="utf-8")

    def snapshot(self, max_chars: int = -1) -> str:
        """
        Concatenate the dependency files up to ``max_chars`` characters.
        Handy when the agent needs a quick, flattened context blob.
        """
        chunks: List[str] = []
        remaining = max_chars if max_chars != -1 else float("inf")
        for dep_path in self._paths:
            text = Path(dep_path).read_text(encoding="utf-8")
            if len(text) > remaining:
                chunks.append(text[:remaining])
                break
            chunks.append(text)
            remaining -= len(text)
            if remaining <= 0:
                break
        return "\n".join(chunks)


class DeclarationLookupTool:
    """Wrapper around the global declaration table returned by ``preprocess_lean_analysis``."""

    def __init__(self, global_symbol_table: Mapping[NameTuple, Mapping[str, object]]):
        self._decls: Dict[NameTuple, Mapping[str, object]] = {
            name: entry["decl"]
            for name, entry in global_symbol_table.items()
            if "decl" in entry
        }

    def get(self, name: Sequence[str]) -> Optional[Mapping[str, object]]:
        return self._decls.get(_to_name_tuple(name))

    def contains(self, name: Sequence[str]) -> bool:
        return _to_name_tuple(name) in self._decls


class SymbolLookupTool:
    """Convenience accessor for the symbol (``sym``) entries."""

    def __init__(self, global_symbol_table: Mapping[NameTuple, Mapping[str, object]]):
        self._symbols: Dict[NameTuple, Mapping[str, object]] = {
            name: entry["sym"]
            for name, entry in global_symbol_table.items()
            if "sym" in entry
        }

    def get(self, name: Sequence[str]) -> Optional[Mapping[str, object]]:
        return self._symbols.get(_to_name_tuple(name))

    def contains(self, name: Sequence[str]) -> bool:
        return _to_name_tuple(name) in self._symbols


@dataclass
class ReferenceResult:
    """Minimal bundle describing recursively collected references."""

    seeds: List[NameTuple]
    resolved: Dict[NameTuple, Mapping[str, object]]


class ReferenceLookupTool:
    """
    Provides a controllable traversal over the ``typeReferences`` and
    ``valueReferences`` graph exposed by the symbol table. This lets the
    agent request only the minimal supporting items it needs.
    """

    def __init__(self, symbol_lookup: SymbolLookupTool):
        self._sym_lookup = symbol_lookup

    def collect(
        self,
        root: Sequence[str],
        *,
        max_depth: int = 2,
        budget: int = 24,
    ) -> ReferenceResult:
        """
        Perform a BFS over the type/value reference graph starting at ``root``.
        ``budget`` caps the total number of unique names returned.
        """
        root_name = _to_name_tuple(root)
        seen = {root_name}
        queue = deque([(root_name, 0)])
        resolved: Dict[NameTuple, Mapping[str, object]] = {}

        while queue and len(seen) < budget:
            current, depth = queue.popleft()
            sym_entry = self._sym_lookup.get(current)
            if not sym_entry:
                continue
            resolved[current] = sym_entry
            if depth >= max_depth:
                continue
            neighbor_lists = sym_entry.get("typeReferences", []) + sym_entry.get(
                "valueReferences", []
            )
            for neighbor in neighbor_lists:
                neighbor_name = _to_name_tuple(neighbor)
                if neighbor_name in seen:
                    continue
                seen.add(neighbor_name)
                queue.append((neighbor_name, depth + 1))
                if len(seen) >= budget:
                    break

        return ReferenceResult(seeds=list(seen), resolved=resolved)
