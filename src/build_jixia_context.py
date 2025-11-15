import os
from globals import ANALYSIS_BOOK_DIRECTORY, MAX_DEPTH, COMMENT_PATTERN
from typing import Set, Tuple, List, Dict, Optional
from tqdm import tqdm
import re
from utils import load_json, sort_by_section


def build_lookup_table(decl_data_path: str) -> dict:
    decl_data = load_json(decl_data_path)
    lookup_table = {}
    for decl in decl_data:
        if not decl["ref"]["original"]:
            continue
        lookup_table[tuple(decl["name"])] = decl
        if decl["kind"] == "inductive":
            for constructor in decl["constructors"]:
                lookup_table[tuple(constructor["name"][1:])] = decl
        if decl["kind"] == "structure":
            for constructor in decl["fields"]:
                lookup_table[tuple(constructor["name"])] = decl
    return lookup_table

def load_external_lookup_table(module: tuple, path: str, mapped_lean_analysis_data: dict):
    if module[1] in mapped_lean_analysis_data:
        return mapped_lean_analysis_data[module[1]]["lookup_table"]

    return build_lookup_table(path)

def extract_context(reference: dict):
    # This function can return None if 'pp' is None
    return reference['ref']['pp']

def extract_references(syms: dict):
    return syms["typeReferences"], syms["valueReferences"]
def load_textbook_section(section: str):
    with open(os.path.join(ANALYSIS_BOOK_DIRECTORY, section + ".lean"), "r") as f:
        return f.read()

def combine_context(context_set: set, proposition: str):
    context = f"\-Context Start-\\\n" + "\n".join(context_set) + "\n\-Context End-\\\n"
    proposition = f"\-Proposition-\\\n" + proposition
    return context + proposition

class tree_node:
    def __init__(self, name: str, context: str | None = None):
        self.name = name
        self.context_text = context          # concatenated defs for this namespace
        self.children: dict[str, tree_node] = {}  # name -> child

def _add_path(node: tree_node, ns_path: tuple[str, ...], idx: int, text: str) -> None:
    """Insert path like ('ns1','ns2',...,'nsk'); merge text at terminal."""
    if idx == len(ns_path):  # terminal node: attach/merge text
        if text:
            node.context_text = (node.context_text + "\n" + text) if node.context_text else text
        return
    seg = ns_path[idx]
    child = node.children.get(seg)
    if child is None:
        child = tree_node(name=seg)
        node.children[seg] = child
    _add_path(child, ns_path, idx + 1, text)

def build_context_tree(context_dict: dict[tuple[str, ...], str | list[str]]) -> tree_node:
    """
    context_dict maps namespace tuples to either a single string or a list of strings.
    Example: {('Chapter1','A'): 'structure A ...', ('Chapter1','A','a'): 'def a ...'}
    """
    root = tree_node(name="Root")
    # parents before children
    for ns_tuple, ctx in sorted(context_dict.items(), key=lambda kv: len(kv[0])):
        if not ns_tuple:  # allow attaching directly to root if needed
            payloads = ctx if isinstance(ctx, list) else [ctx]
            for text in payloads:
                _add_path(root, (), 0, text)
            continue

        payloads = ctx if isinstance(ctx, list) else [ctx]
        # optional: dedupe per namespace
        seen = set()
        for text in payloads:
            if text in seen:
                continue
            seen.add(text)
            _add_path(root, ns_tuple, 0, text)
    return root

def render_lean(
    node,
    out: list[str],
    *,
    proposition: str | None = None,
    place_inside_top_level: bool = True,
    target_top_level: str | None = None,   # if None, use the first top-level ns in sort order
    is_root: bool = True,
    _inserted: dict | None = None,
) -> None:
    """
    Renders a namespaced context tree.
    - proposition: the theorem/prop text to insert (or None)
    - place_inside_top_level: if True, insert just before 'end <top_ns>'; else append after all namespaces
    - target_top_level: name of the top-level namespace to host the proposition (if placing inside).
                        If None, the first top-level namespace (sorted) is used.
    """
    if _inserted is None:
        _inserted = {"done": False}

    # Root handling: iterate top-level namespaces
    if is_root:
        top_names = sorted(node.children.keys())
        if place_inside_top_level and proposition and target_top_level is None and top_names:
            target_top_level = top_names[0]

        for top in top_names:
            _render_namespace(
                node.children[top],
                out,
                proposition=proposition,
                target_top_level=target_top_level,
                inserted_flag=_inserted,
            )

        # If we didn't place inside, and we have a proposition, append it outside all namespaces
        if proposition and not place_inside_top_level and not _inserted["done"]:
            out.append(proposition)
            _inserted["done"] = True
        return

    # Non-root: (kept for API symmetry; rendering is handled by _render_namespace)
    raise RuntimeError("render_lean should be called with is_root=True on the synthetic root.")


def _render_namespace(
    node,
    out: list[str],
    *,
    proposition: str | None,
    target_top_level: str | None,
    inserted_flag: dict,
    _is_top_level: bool = True,
) -> None:
    """Render a namespace node and its subtree; insert proposition inside the chosen top-level ns if requested."""
    out.append(f"namespace {node.name}")
    if getattr(node, "context_text", None):
        out.append(node.context_text)

    # Render children (sorted for determinism)
    child_names = sorted(node.children.keys())
    for cname in child_names:
        _render_namespace(
            node.children[cname],
            out,
            proposition=proposition,
            target_top_level=target_top_level,
            inserted_flag=inserted_flag,
            _is_top_level=False,   # children are not top-level
        )

    # If this is the intended top-level namespace, and we haven't inserted yet, drop the proposition here
    if (
        proposition
        and not inserted_flag["done"]
        and target_top_level is not None
        and _is_top_level
        and node.name == target_top_level
    ):
        out.append(proposition)
        inserted_flag["done"] = True

    out.append(f"end {node.name}")

def render_dependency_set(dependency_set: set[str]) -> str:
    dependency_context = []
    for dep in dependency_set:
        with open(dep, "r") as f:
            dependency_context.append(f.read())
    return "\n".join(dependency_context)

def build_jixia_context(aggregated_baseline_data: dict, mapped_lean_analysis_data: dict, global_symbol_table: dict, global_dependency_table: dict) -> list[dict]:
    def check_imports(ref: list):
        if ref[0] not in ["Analysis", "Init"]:
            return True
        return False

    test_examples_with_context = []
    missed_references = {}

    for section in tqdm(sort_by_section(aggregated_baseline_data.keys())):
        contents = aggregated_baseline_data[section]

        for idx, content in enumerate(contents):
  
            # --- Context Collection Setup (per-query) ---
            processed_symbols: Set[Tuple[str, ...]] = set()
            
            query_name = tuple(content["name"])
            query_text = content["content"]

            # --- Start: Nested Helper Functions ---

            def is_local_chapter_ref(symbol_tuple: Tuple[str, ...]) -> bool:
                """
                Checks if a symbol is from a local namespace and exists in our 
                global table *with a decl object*.
                """
                if not symbol_tuple:
                        return False

                is_chapter = symbol_tuple[0].startswith("Chapter")
                is_finset = symbol_tuple[0].startswith("Finset")

                if not (is_chapter or is_finset): # If it's not in either namespace
                    return False
                
                # Explicitly check for key and then for "decl" sub-key
                if symbol_tuple not in global_symbol_table:
                    if symbol_tuple not in missed_references:
                        missed_references[tuple(symbol_tuple)] = set()
                    missed_references[tuple(symbol_tuple)].add(section)
                    return False
                
                if "decl" not in global_symbol_table[symbol_tuple]:
                    # This can happen if a symbol is in .sym but not .decl
                    if symbol_tuple not in missed_references:
                        missed_references[tuple(symbol_tuple)] = set()
                    missed_references[tuple(symbol_tuple)].add(section)
                    return False
                    
                return True

            
            def find_sym_data(symbol_tuple: Tuple[str, ...]) -> Optional[Dict]:
                """
                Finds the .sym.json data for any symbol from the unified
                global_symbol_table. NO DEFAULTS.
                """
                if symbol_tuple not in global_symbol_table:
                    return None
                
                # Explicit check for the "sym" key
                if "sym" in global_symbol_table[symbol_tuple]:
                    return global_symbol_table[symbol_tuple]["sym"]
                
                return None
          

            def collect_refs_recursive(symbol_tuple: Tuple[str, ...], current_depth: int):
                """
                PHASE 1: Collect all symbols. NO DEFAULTS.
                """
                # 1. Base Cases: Stop if not local or already seen
                if not is_local_chapter_ref(symbol_tuple) or symbol_tuple in processed_symbols:
                    return
                
                # 2. Process this symbol
                processed_symbols.add(symbol_tuple)
                sym_data = find_sym_data(symbol_tuple)
                if sym_data is None:
                    return

                # 3. Recurse on *all* type dependencies.
                # Explicit key and None check.
                if "typeReferences" in sym_data:
                    type_refs_list = sym_data["typeReferences"]
                    if type_refs_list is not None:
                        for t_ref in type_refs_list:
                            collect_refs_recursive(tuple(t_ref), current_depth)

                # 4. Recurse on value dependencies, *if* depth allows
                if current_depth < MAX_DEPTH or MAX_DEPTH == -1:
                    # Explicit key and None check.
                    if "valueReferences" in sym_data:
                        value_refs_list = sym_data["valueReferences"]
                        if value_refs_list is not None:
                            for v_ref in value_refs_list:
                                collect_refs_recursive(tuple(v_ref), current_depth + 1)

            def topological_sort(symbols_to_sort: Set[Tuple]) -> List[Tuple]:
                """
                PHASE 2: Sort all collected symbols. NO DEFAULTS.
                """
                graph = {sym: set() for sym in symbols_to_sort}
                in_degree = {sym: 0 for sym in symbols_to_sort}

                for sym in symbols_to_sort:
                    sym_data = find_sym_data(sym)
                    if sym_data is None:
                        continue
                    
                    # Explicit key and None check
                    if "valueReferences" in sym_data:
                        val_refs_list = sym_data["valueReferences"]
                        if val_refs_list is not None:
                            for v_ref_list in val_refs_list:
                                v_ref = tuple(v_ref_list)
                                if v_ref in symbols_to_sort:
                                    if sym not in graph[v_ref]:
                                        graph[v_ref].add(sym)
                                        in_degree[sym] += 1
                
                # Kahn's algorithm
                queue = [sym for sym in symbols_to_sort if in_degree[sym] == 0]
                sorted_list = []
                
                while queue:
                    queue.sort(key=lambda x: str(x))
                    u = queue.pop(0)
                    sorted_list.append(u)
                    
                    # Sort for deterministic output
                    sorted_neighbors = sorted(list(graph[u]), key=lambda x: str(x))
                    for v in sorted_neighbors:
                        in_degree[v] -= 1
                        if in_degree[v] == 0:
                            queue.append(v)
                            
                if len(sorted_list) != len(symbols_to_sort):
                    print(f"Warning: Cycle detected in dependencies for {query_name}.")
                    remaining = [s for s in symbols_to_sort if s not in sorted_list]
                    return sorted_list + remaining
                    
                return sorted_list
            
            # --- End: Nested Helper Functions ---

            
            # --- Main Collection Logic ---
            
            # Get the query's initial references from the section-specific map
            if query_name not in mapped_lean_analysis_data[section]["sym"]:
                print(f"Warning: Could not find symbol data for query {query_name} in {section}")
                continue
                
            syms = mapped_lean_analysis_data[section]["sym"][query_name]
            imports = mapped_lean_analysis_data[section]["imports"]
            
            filtered_imports = ["import " + '.'.join(imp) for imp in imports if check_imports(imp)]
            if "import Mathlib.Tactic" not in filtered_imports:
                 filtered_imports.insert(0, "import Mathlib.Tactic")

            # Explicitly build initial reference lists
            initial_type_refs = []
            if "typeReferences" in syms and syms["typeReferences"] is not None:
                initial_type_refs = [tuple(r) for r in syms["typeReferences"]]

            initial_value_refs = []
            if "valueReferences" in syms and syms["valueReferences"] is not None:
                initial_value_refs = [tuple(r) for r in syms["valueReferences"]]
            
            all_initial_refs = set(initial_type_refs + initial_value_refs)
            
            for ref_tuple in all_initial_refs:
                collect_refs_recursive(ref_tuple, current_depth=0)

            sorted_symbols = topological_sort(processed_symbols)

            context_set: Set[str] = set()
            context_dict: Dict[Tuple[str, ...], List[str]] = {}

            for symbol_tuple in sorted_symbols:
                # We know "decl" exists because is_local_chapter_ref checked it
                decl = global_symbol_table[symbol_tuple]["decl"]
                
                # --- [THIS IS THE FIX] ---
                def_text = extract_context(decl) # This can return None

                # Explicitly check if extract_context returned None
                if def_text is None:
                    continue # Skip this symbol, it has no printable context
                
                def_text = re.sub(COMMENT_PATTERN, "", def_text, flags=re.DOTALL).strip()
                # --- [END FIX] ---

                if not def_text: # Skip empty definitions (e.g., only comments)
                    continue

                if def_text in context_set: # Dedupe
                    continue
                context_set.add(def_text)
                
                namespace_tuple = tuple(decl["name"][:-1])
                if namespace_tuple not in context_dict:
                    context_dict[namespace_tuple] = []
                context_dict[namespace_tuple].append(def_text)


            # --- Rendering Logic ---
            
            context_tree = build_context_tree(context_dict)
            lines = []
            
            target_ns = None
            if query_name: 
                if query_name[0].startswith("Chapter"):
                    target_ns = query_name[0]
                elif query_name[0].startswith("Finset"):
                    target_ns = query_name[0]
            
            render_lean(
                context_tree, 
                lines, 
                proposition=query_text, 
                place_inside_top_level=False,
                target_top_level=target_ns
            )
            
            lean_context = "\n".join(filtered_imports + [""] + lines)
            
            
            test_examples_with_context.append(
                {
                    "chapter_name": section,
                    "FQN": ".".join(query_name),
                    "content": lean_context, # Use the sorted, namespaced context
                    "dependency_set": render_dependency_set(mapped_lean_analysis_data[section]["dependency_set"]),
                }
            )
    return test_examples_with_context