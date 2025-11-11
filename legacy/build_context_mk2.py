import json
from pathlib import Path
import subprocess
import os
from tqdm import tqdm
import dill as pickle
from typing import Set, Tuple, Optional, Dict, List
import re

JIXIA_EXECUTABLE = "/Users/alextaylor/dev/jixia/.lake/build/bin/jixia"
BASELINE_PATH = "/Users/alextaylor/Desktop/lean_prover/tao_analysis_baseline.jsonl"

WORKING_DIR = Path(os.getcwd()) / "processed_test_data"
OUTPUT_DIR = Path(os.getcwd())

DATA_DIR = "/Users/alextaylor/Desktop/lean_prover/processed_analysis"

CACHE_DIR = "/Users/alextaylor/Desktop/lean_prover/.cache"
os.makedirs(CACHE_DIR, exist_ok=True)

ANALYSIS_BOOK_DIRECTORY = "/Users/alextaylor/Desktop/lean_prover/analysis/analysis/Analysis"


# Configurable recursion depth
MAX_DEPTH = 3 
COMMENT_PATTERN = r"/\-[\-]?.*?\-\/"


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
            entry = {
                "mod": os.path.join(section_path, f"{section}.mod.json"),
                "decl": os.path.join(section_path, f"{section}.decl.json"),
                "sym": os.path.join(section_path, f"{section}.sym.json"),
            }
            # Optional elab/ast if present
            elab_path = os.path.join(section_path, f"{section}.elab.json")
            ast_path = os.path.join(section_path, f"{section}.ast.json")
            if os.path.exists(elab_path):
                entry["elab"] = elab_path
            if os.path.exists(ast_path):
                entry["ast"] = ast_path
            jixia_table[section] = entry

    # Optional: mount a preprocessed Init dataset if present under DATA_DIR/Init
    init_dir = os.path.join(DATA_DIR, "Init")
    if os.path.isdir(init_dir):
        init_entry = {}
        for ext in ["mod", "decl", "sym", "elab", "ast"]:
            p = os.path.join(init_dir, f"Init.{ext}.json")
            if os.path.exists(p):
                init_entry[ext] = p
        if init_entry:
            jixia_table["Init"] = init_entry

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
    # This function is now only used as a helper inside preprocess_lean_analysis
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

# --- [MODIFIED FUNCTION] ---
def preprocess_lean_analysis(jixia_table, force_reprocess=False):
    cache_path_map = os.path.join(CACHE_DIR, "jixia_name_map_cache.pkl")
    cache_path_table = os.path.join(CACHE_DIR, "global_symbol_table_cache.pkl")
    cache_path_modmap = os.path.join(CACHE_DIR, "module_imports_cache.pkl")
    cache_path_sym2mod = os.path.join(CACHE_DIR, "symbol_to_module_cache.pkl")

    if force_reprocess:
        print("Force reprocessing lean analysis data...")
        if os.path.exists(cache_path_map):
            os.remove(cache_path_map)
            print("Removed cached lean analysis data (map).")
        if os.path.exists(cache_path_table):
            os.remove(cache_path_table)
            print("Removed cached lean analysis data (table).")
        if os.path.exists(cache_path_modmap):
            os.remove(cache_path_modmap)
            print("Removed cached module imports map.")
        if os.path.exists(cache_path_sym2mod):
            os.remove(cache_path_sym2mod)
            print("Removed cached symbol-to-module map.")

    jixia_name_map = {}
    # This is the new unified table.
    # It will map: Tuple[str, ...] -> {"decl": decl_obj, "sym": sym_obj}
    global_symbol_table = {}
    module_imports: Dict[str, List[List[str]]] = {}
    symbol_to_module: Dict[Tuple[str, ...], str] = {}

    print("Preprocessing jixia analysis data...")
    if not os.path.exists(cache_path_map) or not os.path.exists(cache_path_table) or not os.path.exists(cache_path_modmap) or not os.path.exists(cache_path_sym2mod) or force_reprocess:
        print("No cache found. Preprocessing data...")
        
        # --- Pass 1: Build the full global_symbol_table ---
        all_sections_data = {}
        for section in tqdm(sort_by_chapter(jixia_table.keys()), desc="Pass 1: Reading data"):
            contents = jixia_table[section]
            decl_list = parse_json(contents["decl"]) if "decl" in contents else []
            sym_list = parse_json(contents["sym"]) if "sym" in contents else []
            imports = parse_json(contents["mod"]) ["imports"] if "mod" in contents else []
            elab_list = parse_json(contents["elab"]) if "elab" in contents else []
            ast_list = parse_json(contents["ast"]) if "ast" in contents else []
            
            all_sections_data[section] = {
                "decl_list": decl_list,
                "sym_list": sym_list,
                "imports": imports,
                "elab_list": elab_list,
                "ast_list": ast_list,
            }
            # Derive module name for the section (or Init)
            module_name = "Init" if section == "Init" else f"Analysis.{section}"
            module_imports[module_name] = imports
            
            # Add all declarations to the global table
            for decl in decl_list:
                if not decl["ref"]["original"]:
                    continue
                
                key = tuple(decl["name"])
                if key not in global_symbol_table:
                    global_symbol_table[key] = {}
                global_symbol_table[key]["decl"] = decl
                # map symbol to its defining module
                symbol_to_module[key] = module_name
                
                # Also map constructors/fields to the *parent* decl
                if decl["kind"] == "inductive":
                    for constructor in decl["constructors"]:
                        c_key = tuple(constructor["name"][1:])
                        if c_key not in global_symbol_table:
                             global_symbol_table[c_key] = {}
                        global_symbol_table[c_key]["decl"] = decl
                        symbol_to_module[c_key] = module_name
                if decl["kind"] == "structure":
                    for field in decl["fields"]:
                        f_key = tuple(field["name"])
                        if f_key not in global_symbol_table:
                            global_symbol_table[f_key] = {}
                        global_symbol_table[f_key]["decl"] = decl
                        symbol_to_module[f_key] = module_name

            # Add all symbol data to the global table
            for sym in sym_list:
                key = tuple(sym["name"])
                if key not in global_symbol_table:
                    global_symbol_table[key] = {}
                global_symbol_table[key]["sym"] = sym
                if key not in symbol_to_module:
                    symbol_to_module[key] = module_name
            # We retain elab/ast per-module in the section map (next pass)

        # --- Pass 2: Build the per-section jixia_name_map ---
        print("Pass 2: Building section maps...")
        for section, data in all_sections_data.items():
            jixia_name_map[section] = {
                "decl": {tuple(d["name"]): d for d in data["decl_list"] if "name" in d},
                "sym": {tuple(s["name"]): s for s in data["sym_list"] if "name" in s},
                "imports": data["imports"],
                "elab": data["elab_list"],
                "ast": data["ast_list"],
                "module_name": ("Init" if section == "Init" else f"Analysis.{section}"),
            }

        print(f"Caching lean analysis data at {cache_path_map}...")
        with open(cache_path_map, "wb") as f:
            pickle.dump(jixia_name_map, f)
        print(f"Caching global symbol table at {cache_path_table}...")
        with open(cache_path_table, "wb") as f:
            pickle.dump(global_symbol_table, f)
        with open(cache_path_modmap, "wb") as f:
            pickle.dump(module_imports, f)
        with open(cache_path_sym2mod, "wb") as f:
            pickle.dump(symbol_to_module, f)
    else:
        print("Loading cached lean analysis data...")
        with open(cache_path_map, "rb") as f:
            jixia_name_map = pickle.load(f)
        with open(cache_path_table, "rb") as f:
            global_symbol_table = pickle.load(f)
        with open(cache_path_modmap, "rb") as f:
            module_imports = pickle.load(f)
        with open(cache_path_sym2mod, "rb") as f:
            symbol_to_module = pickle.load(f)

    # Return section-map, symbol table, module imports and symbol→module
    return jixia_name_map, global_symbol_table, module_imports, symbol_to_module
# --- [END MODIFIED FUNCTION] ---


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

# --- [REMOVED unused recurse_references function] ---

def _iter_term_const_refs(elab_node: dict, acc: Set[Tuple[str, ...]]):
    """Walks an elab tree node (as dict) and collects any termConstRefs/typeConstRefs."""
    if not isinstance(elab_node, dict):
        return
    info = elab_node.get("info")
    if isinstance(info, dict):
        # Term nodes (by our encoder) carry term/type const refs
        term = info.get("term")
        if isinstance(term, dict):
            for key in ("termConstRefs", "typeConstRefs"):
                refs = term.get(key)
                if isinstance(refs, list):
                    for r in refs:
                        try:
                            acc.add(tuple(r) if isinstance(r, list) else tuple(r))
                        except Exception:
                            pass
    # Recurse children
    for child in elab_node.get("children", []):
        _iter_term_const_refs(child, acc)


def collect_implicit_instance_refs(local_elab_list: List[dict]) -> Set[Tuple[str, ...]]:
    """Collect implicit constants (instances/notation carriers) from a query-local elab.json array."""
    acc: Set[Tuple[str, ...]] = set()
    if isinstance(local_elab_list, list):
        for node in local_elab_list:
            _iter_term_const_refs(node, acc)
    return acc


def compute_transitive_imports_for_query(root_module: str, module_imports: Dict[str, List[List[str]]], extra_modules: List[str]) -> List[str]:
    """BFS over module imports, keeping a stable order; include extra_modules roots as well."""
    seen = set()
    queue: List[str] = []
    def enqueue(mod: str):
        if mod and mod not in seen:
            seen.add(mod)
            queue.append(mod)

    enqueue(root_module)
    for m in extra_modules:
        enqueue(m)

    ordered: List[str] = []
    idx = 0
    while idx < len(queue):
        mod = queue[idx]
        ordered.append(mod)
        idx += 1
        imports = module_imports.get(mod, [])
        for imp in imports:
            dotted = ".".join(imp)
            enqueue(dotted)
    # Convert to import lines
    return [f"import {m}" for m in ordered]


def aggregate_opens_from_decls(decls: List[dict]) -> List[str]:
    lines: List[str] = []
    seen = set()
    for d in decls:
        si = d.get("scopeInfo", {})
        for od in si.get("openDecl", []) or []:
            if isinstance(od, dict) and "simple" in od:
                ns = od["simple"].get("namespace", [])
                dotted = ".".join(ns)
                if dotted and dotted not in seen:
                    seen.add(dotted)
                    lines.append(f"open {dotted}")
    return lines


def build_context(aggregated_baseline_data, mapped_lean_analysis_data, global_symbol_table, module_imports, symbol_to_module):

    test_examples_with_context = []
    missed_references = {}

    for section in tqdm(sort_by_chapter(aggregated_baseline_data.keys())):
        contents = aggregated_baseline_data[section]

        for idx, content in enumerate(contents):
  
            # --- Context Collection Setup (per-query) ---
            processed_symbols: Set[Tuple[str, ...]] = set()
            
            query_name = tuple(content["name"])
            query_text = content["content"]

            # --- Start: Nested Helper Functions ---

            def is_local_chapter_ref(symbol_tuple: Tuple[str, ...]) -> bool:
                """
                Accept any symbol present in the global table with a decl entry.
                """
                if not symbol_tuple:
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
                    
                    # Add edges from type references
                    if "typeReferences" in sym_data:
                        t_refs_list = sym_data["typeReferences"]
                        if t_refs_list is not None:
                            for t_ref_list in t_refs_list:
                                t_ref = tuple(t_ref_list)
                                if t_ref in symbols_to_sort:
                                    if sym not in graph[t_ref]:
                                        graph[t_ref].add(sym)
                                        in_degree[sym] += 1

                    # Add edges from value references
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
            # base module
            root_module = mapped_lean_analysis_data[section].get("module_name", f"Analysis.{section}")

            # Explicitly build initial reference lists
            initial_type_refs = []
            if "typeReferences" in syms and syms["typeReferences"] is not None:
                initial_type_refs = [tuple(r) for r in syms["typeReferences"]]

            initial_value_refs = []
            if "valueReferences" in syms and syms["valueReferences"] is not None:
                initial_value_refs = [tuple(r) for r in syms["valueReferences"]]
            
            all_initial_refs = set(initial_type_refs + initial_value_refs)

            # Seed with query-local sym/elab if present (implicit deps)
            local_elab = content.get("local_elab", [])
            local_implicit_refs = collect_implicit_instance_refs(local_elab)
            all_initial_refs |= local_implicit_refs
            
            for ref_tuple in all_initial_refs:
                collect_refs_recursive(ref_tuple, current_depth=0)

            sorted_symbols = topological_sort(processed_symbols)

            context_set: Set[str] = set()
            context_dict: Dict[Tuple[str, ...], List[str]] = {}
            selected_decls: List[dict] = []

            for symbol_tuple in sorted_symbols:
                # We know "decl" exists because is_local_chapter_ref checked it
                decl = global_symbol_table[symbol_tuple]["decl"]
                
                def_text = extract_context(decl) # This can return None
                if def_text is None:
                    continue
                def_text = def_text.strip()

                if not def_text: # Skip empty definitions (e.g., only comments)
                    continue

                if def_text in context_set: # Dedupe
                    continue
                context_set.add(def_text)
                
                namespace_tuple = tuple(decl["name"][:-1])
                if namespace_tuple not in context_dict:
                    context_dict[namespace_tuple] = []
                context_dict[namespace_tuple].append(def_text)
                selected_decls.append(decl)


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
            # Build minimal imports via transitive closure, including modules of non-local symbols
            extra_modules = []
            for sym in processed_symbols:
                mod = symbol_to_module.get(sym)
                if mod and mod not in extra_modules:
                    extra_modules.append(mod)
            import_lines = compute_transitive_imports_for_query(root_module, module_imports, extra_modules)

            # Aggregate opens and binders
            open_lines = aggregate_opens_from_decls(selected_decls)
            binder_lines: List[str] = []
            # collect section-level variable/universe binders
            level_names = set()
            var_decl_lines = []
            for d in selected_decls:
                si = d.get("scopeInfo", {})
                for u in si.get("levelNames", []) or []:
                    try:
                        # levelNames encoded as Name arrays like ["u"]
                        level_names.add(".".join(u) if isinstance(u, list) else str(u))
                    except Exception:
                        pass
                for vline in si.get("varDecls", []) or []:
                    if vline not in var_decl_lines:
                        var_decl_lines.append(vline)
            if level_names:
                binder_lines.append("universe " + " ".join(sorted(level_names)))
            binder_lines.extend(var_decl_lines)

            # Inject opens and binders at the top of the emitted file
            prelude = []
            if import_lines:
                prelude.extend(import_lines)
            # Select and emit notations/macros from AST for involved modules
            involved_modules = set([root_module] + extra_modules)
            notation_lines: List[str] = []
            for sect, data in mapped_lean_analysis_data.items():
                modn = data.get("module_name")
                if modn in involved_modules:
                    for node in data.get("ast", []) or []:
                        try:
                            k = node.get("kind")
                            if isinstance(k, list):
                                # Expect something like ["Lean","Parser","Command","notation"]
                                if len(k) >= 4 and k[-1] in ("notation", "macro_rules"):
                                    s = node.get("str")
                                    if isinstance(s, str) and s.strip():
                                        notation_lines.append(s.strip())
                        except Exception:
                            continue
            if notation_lines:
                prelude.append("")
                prelude.extend(list(dict.fromkeys(notation_lines)))  # dedupe, preserve order
            if open_lines:
                prelude.append("")
                prelude.extend(open_lines)
            if binder_lines:
                prelude.append("")
                prelude.extend(binder_lines)

            lean_context = "\n".join(prelude + [""] + lines)
            
            
            test_examples_with_context.append(
                {
                    "chapter_name": section,
                    "content": lean_context, # Use the sorted, namespaced context
                }
            )
       

  
    return test_examples_with_context
# --- [END MODIFIED FUNCTION] ---


# --- [MODIFIED FUNCTION] ---
def main():
    jixia_table = construct_jixia_table()
    mapped_lean_analysis_data, global_symbol_table, module_imports, symbol_to_module = preprocess_lean_analysis(jixia_table, force_reprocess=True)
    aggregated_baseline_data = preprocess_baseline_data(force_reprocess=True)
    test_examples_with_context = build_context(aggregated_baseline_data, mapped_lean_analysis_data, global_symbol_table, module_imports, symbol_to_module)
    
    output_path = os.path.join(OUTPUT_DIR, "tao_analysis_baseline_unwrapped_context.jsonl")
    with open(output_path, "w") as f:
        for example in test_examples_with_context:
            f.write(json.dumps(example) + "\n")
    print(f"Saved {len(test_examples_with_context)} test examples with context to {output_path}")

if __name__ == "__main__":
    main()