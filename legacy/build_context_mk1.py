import json
from pathlib import Path
import subprocess
import os
from tqdm import tqdm
import dill as pickle
from dataclasses import dataclass, field
from typing import Dict, Tuple, Iterable, Optional

JIXIA_EXECUTABLE = "/Users/alextaylor/dev/jixia/.lake/build/bin/jixia"
BASELINE_PATH = "/Users/alextaylor/Desktop/lean_prover/tao_analysis_baseline.jsonl"

WORKING_DIR = Path(os.getcwd()) / "processed_test_data"
OUTPUT_DIR = Path(os.getcwd())

DATA_DIR = "/Users/alextaylor/Desktop/lean_prover/processed_analysis"

CACHE_DIR = "/Users/alextaylor/Desktop/lean_prover/.cache"
os.makedirs(CACHE_DIR, exist_ok=True)

ANALYSIS_BOOK_DIRECTORY = "/Users/alextaylor/Desktop/lean_prover/analysis/analysis/Analysis"


def load_jsonl(file):
    with open(file, "r") as f:
        return [json.loads(line) for line in f]

def parse_json(file):
    with open(file, "r") as f:
        return json.load(f)

def sort_by_chapter(sections: list) -> list:
    return sorted(sections, key=lambda x: (int(x.split("_")[1]), x.split("_")[2].split(".")[0]))

def construct_jixia_table():
    jixia_table = {}
    os.listdir(DATA_DIR)
    for section in os.listdir(DATA_DIR):
        if section.startswith("Section_"):
            section_path = os.path.join(DATA_DIR, section)
            jixia_table[section] = {
                "mod": os.path.join(section_path, f"{section}.mod.json"),
                "decl": os.path.join(section_path, f"{section}.decl.json"),
                "sym": os.path.join(section_path, f"{section}.sym.json"),
            }
    return jixia_table

def process_snippet(question_string: str, section: str, idx: int):
    section_workspace = os.path.join(WORKING_DIR, section)
    os.makedirs(section_workspace, exist_ok=True)
    
    file_path = os.path.join(section_workspace, f"question_{idx}.lean")
    chapter_key = section.split("_")[1]
    namespace_open = f"namespace Chapter{chapter_key}\n" if chapter_key != "4" else f"namespace {section}\n"
    namespace_close = f"end Chapter{chapter_key}\n" if chapter_key != "4" else f"end {section}\n"
    if section == "Section_4_4":
        namespace_open = namespace_close = ""
    elif section == "Section_7_1":
        namespace_open = f"namespace Finset\n"
        namespace_close = f"end Finset\n"
    #implicitly fixed was the wrong name extracted from section 3.6
    wrapper = "".join([namespace_open, "[QUERY_STRING]\n", namespace_close])
    with open(file_path, "w") as f:
        f.write(wrapper.replace("[QUERY_STRING]", question_string))

    # Run jixia
    proc = subprocess.run(
        [
            "lake",
            "env",
            JIXIA_EXECUTABLE,
            "-i",
            "-d",
            os.path.join(section_workspace, f"question_{idx}.decl.json"),
            file_path,
        ],
        cwd=WORKING_DIR,
        capture_output=True,
        text=True,
        check=False,
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"jixia failed for {file_path} (exit {proc.returncode}).\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    return os.path.join(section_workspace, f"question_{idx}.decl.json")

def filter_baseline(baseline_data):
    aggregated_data = {}
    for idx, item in enumerate(baseline_data):
        if item["chapter_name"] not in aggregated_data:
            aggregated_data[item["chapter_name"]] = []
        aggregated_data[item["chapter_name"]].append({
            "idx": idx,
            "content": item["content"].strip()
        })
    return aggregated_data

def preprocess_baseline_data(force_reprocess: bool = False):
    if force_reprocess:
        print("Force reprocessing baseline data...")
        if os.path.exists(os.path.join(CACHE_DIR, "aggregated_baseline_data_cache.json")):
            os.remove(os.path.join(CACHE_DIR, "aggregated_baseline_data_cache.json"))
            print("Removed cached baseline data.")
        else:
            print("No cached baseline data found.")
    os.makedirs(WORKING_DIR, exist_ok=True)
    baseline_data = load_jsonl(BASELINE_PATH)
    aggregated_baseline_data = filter_baseline(baseline_data)
    print("Preprocessing baseline data...")
    if not os.path.exists(os.path.join(CACHE_DIR, "aggregated_baseline_data_cache.json")) or force_reprocess:
        print("No cache found. Preprocessing data, this may take a while...")
        for section, contents in tqdm(aggregated_baseline_data.items()):
            for content in contents:
                decl_json = process_snippet(content["content"], section, int(content["idx"]))
                name = parse_json(decl_json)[0]["name"]
                content["name"] = tuple(name)
        print(f"Caching baseline data at {os.path.join(CACHE_DIR, 'aggregated_baseline_data_cache.json')}...")
        with open(os.path.join(CACHE_DIR, "aggregated_baseline_data_cache.json"), "w") as f:
            json.dump(aggregated_baseline_data, f)
            
    else:
        print("Loading cached baseline data...")
        with open(os.path.join(CACHE_DIR, "aggregated_baseline_data_cache.json"), "r") as f:
            aggregated_baseline_data = json.load(f)

    return aggregated_baseline_data


def resolve_external_lookup_pathing(module: list, lookup_tables: dict) -> str:
    if module[0] == "Analysis":
        return lookup_tables[module[1]]
    
    raise ValueError(f"Module {'.'.join(module)} is not a Supported module")


def recurse_module_pathing(module: list, jixia_table: dict) -> str:
    if module[0] == "Analysis":
        return jixia_table[module[1]]["decl"]
    raise ValueError(f"Module {'.'.join(module)} is not a Supported module")

def process_modules(analysis_json_path: str, lookup_tables: dict) -> dict:
    module_data = parse_json(analysis_json_path)
    module_lookup_table = {}
    for module in module_data["imports"]:
        if module[0] in ["Init", "Mathlib"]:
            # We do not currently support imports from Mathlib or Init
            continue
        # we can probably extend this to support external imports in the future
        module_lookup_table.update(resolve_external_lookup_pathing(module, lookup_tables))
    return module_lookup_table

def filter_lean_analysis(analysis_json_path):
    analysis_data = parse_json(analysis_json_path)
    analysis_name_map = {}
    for item in analysis_data:
        analysis_name_map[tuple(item["name"])] = item
    return analysis_name_map

def build_lookup_table(decl_data_path):
    decl_data = parse_json(decl_data_path)
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

def preprocess_lean_analysis(jixia_table, force_reprocess=False):
    if force_reprocess:
        print("Force reprocessing lean analysis data...")
        if os.path.exists(os.path.join(CACHE_DIR, "jixia_name_map_cache.json")):
            os.remove(os.path.join(CACHE_DIR, "jixia_name_map_cache.json"))
            print("Removed cached lean analysis data.")
        else:
            print("No cached lean analysis data found.")
        if os.path.exists(os.path.join(CACHE_DIR, "global_lookup_table_cache.json")):
            os.remove(os.path.join(CACHE_DIR, "global_lookup_table_cache.json"))
            print("Removed cached lean analysis data.")
        else:
            print("No cached lean analysis data found.")
    jixia_name_map = {}
    global_lookup_table = {}

    print("Preprocessing jixia analysis data...")
    if not os.path.exists(os.path.join(CACHE_DIR, "jixia_name_map_cache.pkl")) or force_reprocess:
        print("No cache found. Preprocessing data...")
        for section in tqdm(sort_by_chapter(jixia_table.keys())):
            contents = jixia_table[section]
            imports = parse_json(contents["mod"])["imports"]
            named_decl_data = filter_lean_analysis(contents["decl"])
            named_sym_data = filter_lean_analysis(contents["sym"])
            lookup_table = build_lookup_table(contents["decl"])
            global_lookup_table.update(lookup_table)
            jixia_name_map[section] = {
                "decl": named_decl_data,
                "sym": named_sym_data,
                "imports": imports,
            }
        print(f"Caching lean analysis data at {os.path.join(CACHE_DIR, 'jixia_name_map_cache.pkl')}...")
        with open(os.path.join(CACHE_DIR, "jixia_name_map_cache.pkl"), "wb") as f:
            pickle.dump(jixia_name_map, f)
        print(f"Caching global lookup table at {os.path.join(CACHE_DIR, 'global_lookup_table_cache.pkl')}...")
        with open(os.path.join(CACHE_DIR, "global_lookup_table_cache.pkl"), "wb") as f:
            pickle.dump(global_lookup_table, f)
    else:
        print("Loading cached lean analysis data...")
        with open(os.path.join(CACHE_DIR, "jixia_name_map_cache.pkl"), "rb") as f:
            jixia_name_map = pickle.load(f)
        with open(os.path.join(CACHE_DIR, "global_lookup_table_cache.pkl"), "rb") as f:
            global_lookup_table = pickle.load(f)

    return jixia_name_map, global_lookup_table

def load_external_lookup_table(module: tuple, path: str, mapped_lean_analysis_data: dict):
    if module[1] in mapped_lean_analysis_data:
        return mapped_lean_analysis_data[module[1]]["lookup_table"]

    return build_lookup_table(path)

def extract_context(reference: dict):
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
    
def recurse_references(references: list, lookup_table: dict):
    syms,vals = extract_references(references)
    additional_context = set()
    for sym in syms:
        if sym in lookup_table:
            additional_context.add(extract_context(lookup_table[sym]))
        
    for val in vals:
        if val in lookup_table:
            additional_context.add(extract_context(lookup_table[val]))
    return additional_context

def build_context(aggregated_baseline_data, mapped_lean_analysis_data, lookup_table):
    def check_ref(ref: list): 
        # filters references that do not originate from the analysis book
        if "Chapter" in ref[0]:
            return True
        else:
            return False
            
    def check_imports(ref: list):
        if ref[0] not in ["Analysis", "Init"]:
            return True
        return False

    test_examples_with_context = []
    missed_references = {}
    
    # Configurable recursion depth
    MAX_DEPTH = 3 

    for section in tqdm(sort_by_chapter(aggregated_baseline_data.keys())):
        contents = aggregated_baseline_data[section]
 
        print(f"---- Examples from {section} ----")

        for idx, content in enumerate(contents):
  
            # --- Context Collection Setup (per-query) ---
            processed_symbols: Set[Tuple[str, ...]] = set()
            context_set: Set[str] = set()
            context_dict: Dict[Tuple[str, ...], List[str]] = {}
            
            query_name = tuple(content["name"])
            query_text = content["content"]

            # --- Start: Nested Helper Functions ---

            def is_local_chapter_ref(symbol_tuple: Tuple[str, ...]) -> bool:
                """
                Checks if a symbol is from 'Chapter*' and exists in our global lookup table.
                Logs misses for debugging.
                """
                if not symbol_tuple or not symbol_tuple[0].startswith("Chapter"):
                    return False
                
                if symbol_tuple not in lookup_table:
                    if symbol_tuple not in missed_references:
                        missed_references[tuple(symbol_tuple)] = set()
                    missed_references[tuple(symbol_tuple)].add(section)
                    return False
                return True

            def add_definition(symbol_tuple: Tuple[str, ...]) -> bool:
                """
                Adds a symbol's definition text to context_set and context_dict.
                Uses the *declaration's name* for namespacing.
                Returns True if a new definition was added.
                """
                if not is_local_chapter_ref(symbol_tuple):
                    return False
                
                decl = lookup_table[symbol_tuple]
                def_text = extract_context(decl)

                # Use text-based deduplication
                if def_text in context_set:
                    return False 
                
                context_set.add(def_text)
                
                # Use the full name from the decl for the namespace path
                namespace_tuple = tuple(decl["name"][:-1]) 
                
                if namespace_tuple not in context_dict:
                    context_dict[namespace_tuple] = []
                
                context_dict[namespace_tuple].append(def_text)
                return True

            def find_sym_data(symbol_tuple: Tuple[str, ...]) -> Optional[Dict]:
                """
                Finds the .sym.json data for any symbol by checking its
                declaration's file path.
                """
                if symbol_tuple not in lookup_table:
                    return None
                    
                sym_data_map = mapped_lean_analysis_data[section].get("sym", {})
                return sym_data_map.get(symbol_tuple)

            def collect_refs_recursive(symbol_tuple: Tuple[str, ...], current_depth: int):
                """
                Recursively collects context.
                - Adds the current symbol's definition.
                - Adds all its *direct type* dependencies.
                - Recurses *only* on its *value* dependencies.
                """
                # 1. Base Cases: Stop if max depth, already seen, or not local
                if (current_depth > MAX_DEPTH or
                    symbol_tuple in processed_symbols or
                    not is_local_chapter_ref(symbol_tuple)):
                    return

                processed_symbols.add(symbol_tuple)

                # 2. Add this symbol's definition
                add_definition(symbol_tuple)
                
                # 3. Find this symbol's own dependencies
                sym_data = find_sym_data(symbol_tuple)
                if not sym_data:
                    return # No further references to follow

                # 4. Add all *direct type dependencies* (e.g., Nat.add needs Nat)
                # We add these but do not recurse from them.
                type_refs = sym_data.get("typeReferences", [])
                for t_ref in type_refs:
                    t_ref_tuple = tuple(t_ref)
                    if t_ref_tuple not in processed_symbols:
                        if add_definition(t_ref_tuple):
                            processed_symbols.add(t_ref_tuple) # Mark as "visited"

                # 5. Recurse *only* on valueReferences, as per prompt
                value_refs = sym_data.get("valueReferences", [])
                for v_ref in value_refs:
                    collect_refs_recursive(tuple(v_ref), current_depth + 1)
            
            # --- End: Nested Helper Functions ---

            
            # --- Main Collection Logic ---
            
            if query_name not in mapped_lean_analysis_data[section]["sym"]:
                print(f"Warning: Could not find symbol data for query {query_name} in {section}")
                continue
                
            syms = mapped_lean_analysis_data[section]["sym"][query_name]
            imports = mapped_lean_analysis_data[section]["imports"]
            
            # Filter imports
            filtered_imports = ["import " + '.'.join(imp) for imp in imports if check_imports(imp)]
            if "import Mathlib.Tactic" not in filtered_imports:
                 filtered_imports.insert(0, "import Mathlib.Tactic")

            # 1. Get *all* direct references from the query
            initial_type_refs = [tuple(r) for r in syms.get("typeReferences", [])]
            initial_value_refs = [tuple(r) for r in syms.get("valueReferences", [])]
            
            # Combine all unique starting points for the recursion
            all_initial_refs = set(initial_type_refs + initial_value_refs)
            
            # 2. Start recursion from all direct dependencies
            for ref_tuple in all_initial_refs:
                collect_refs_recursive(ref_tuple, current_depth=0)

            # --- Rendering Logic ---
            
            context_tree = build_context_tree(context_dict)
            lines = []
            
            # Find the correct top-level namespace (e.g., "Chapter2")
            target_ns = None
            if query_name and query_name[0].startswith("Chapter"):
                target_ns = query_name[0]
            
            render_lean(
                context_tree, 
                lines, 
                proposition=query_text, 
                place_inside_top_level=True,
                target_top_level=target_ns
            )
            
            lean_context = "\n".join(filtered_imports + [""] + lines)
            
            print(f"---- simple-based Context ----")
            print(combine_context(context_set, query_text))
            print(f"---- tree-based Context ----")
            print(lean_context)
            
            test_examples_with_context.append(
                {
                    "chapter_name": section,
                    "content": lean_context, # Using the namespaced version
                }
            )
        exit()

  
    return test_examples_with_context

def main():
    jixia_table = construct_jixia_table()
    aggregated_baseline_data = preprocess_baseline_data(force_reprocess=False)
    mapped_lean_analysis_data, lookup_table = preprocess_lean_analysis(jixia_table, force_reprocess=True)
    test_examples_with_context = build_context(aggregated_baseline_data, mapped_lean_analysis_data, lookup_table)
    with open(os.path.join(OUTPUT_DIR, "tao_analysis_baseline_with_context.jsonl"), "w") as f:
        for example in test_examples_with_context:
            f.write(json.dumps(example) + "\n")
    print(f"Saved {len(test_examples_with_context)} test examples with context to {os.path.join(OUTPUT_DIR, 'tao_analysis_baseline_with_context.jsonl')}")

if __name__ == "__main__":
    main()
