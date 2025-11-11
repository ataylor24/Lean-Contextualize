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
    cache_path_instances = os.path.join(CACHE_DIR, "instance_index.pkl")

    if force_reprocess:
        print("Force reprocessing lean analysis data...")
        if os.path.exists(cache_path_map):
            os.remove(cache_path_map)
            print("Removed cached lean analysis data (map).")
        if os.path.exists(cache_path_table):
            os.remove(cache_path_table)
            print("Removed cached lean analysis data (table).")
        if os.path.exists(cache_path_instances):
            os.remove(cache_path_instances)
            print("Removed cached instance index.")

    jixia_name_map = {}
    # This is the new unified table.
    # It will map: Tuple[str, ...] -> {"decl": decl_obj, "sym": sym_obj}
    global_symbol_table = {}
    # Instance index maps (class_head: str, type_head: tuple[str,...]) -> instance name tuple
    instance_index: Dict[Tuple[str, Tuple[str, ...]], Tuple[str, ...]] = {}

    print("Preprocessing jixia analysis data...")
    if (
        not os.path.exists(cache_path_map)
        or not os.path.exists(cache_path_table)
        or not os.path.exists(cache_path_instances)
        or force_reprocess
    ):
        print("No cache found. Preprocessing data...")
        
        # --- Pass 1: Build the full global_symbol_table ---
        all_sections_data = {}
        sym_by_name: Dict[Tuple[str, ...], Dict] = {}
        for section in tqdm(sort_by_chapter(jixia_table.keys()), desc="Pass 1: Reading data"):
            contents = jixia_table[section]
            decl_list = parse_json(contents["decl"])
            sym_list = parse_json(contents["sym"])
            imports = parse_json(contents["mod"])["imports"]
            
            all_sections_data[section] = {
                "decl_list": decl_list,
                "sym_list": sym_list,
                "imports": imports
            }
            
            # Index sym rows by their fully qualified name for this section
            for sym in sym_list:
                if "name" not in sym:
                    raise KeyError(f"sym row missing name in section {section}")
                key = tuple(sym["name"])
                if key in sym_by_name:
                    raise ValueError(f"Duplicate sym name encountered: {key}")
                sym_by_name[key] = sym

            # Add all declarations to the global table
            for decl in decl_list:
                if not decl["ref"]["original"]:
                    continue
                
                key = tuple(decl["name"])
                if key not in global_symbol_table:
                    global_symbol_table[key] = {}
                global_symbol_table[key]["decl"] = decl
                
                # Also map constructors/fields to the *parent* decl
                if decl["kind"] == "inductive":
                    for constructor in decl["constructors"]:
                        c_key = tuple(constructor["name"][1:])
                        if c_key not in global_symbol_table:
                             global_symbol_table[c_key] = {}
                        global_symbol_table[c_key]["decl"] = decl
                if decl["kind"] == "structure":
                    for field in decl["fields"]:
                        f_key = tuple(field["name"])
                        if f_key not in global_symbol_table:
                            global_symbol_table[f_key] = {}
                        global_symbol_table[f_key]["decl"] = decl

                # Exact instance discovery via decl.kind == "instance" and matching sym row
                if decl["kind"] == "instance":
                    if "name" not in decl:
                        raise KeyError("instance decl missing name")
                    inst_name = tuple(decl["name"])
                    ns_prefix = tuple(decl["name"][:-1])
                    if inst_name not in sym_by_name:
                        raise KeyError(f"sym row not found for instance {inst_name}")
                    srow = sym_by_name[inst_name]
                    if "typeReferences" not in srow:
                        raise KeyError(f"sym row for {inst_name} missing typeReferences")
                    refs = srow["typeReferences"]
                    if not isinstance(refs, list) or len(refs) == 0:
                        raise ValueError(f"typeReferences malformed for instance {inst_name}")
                    # Find concrete type equal to ns_prefix
                    concrete: Optional[Tuple[str, ...]] = None
                    for r in refs:
                        if not (isinstance(r, list) and len(r) > 0):
                            raise ValueError(f"Bad reference for instance {inst_name}: {r}")
                        if tuple(r) == ns_prefix:
                            concrete = tuple(r)
                            break
                    if concrete is None:
                        # Instance defined outside the concrete type's namespace; log and skip.
                        print(f"Skipping non-local instance without ns-matching concrete type: {inst_name}")
                        continue
                    # Class heads are the non-concrete, non-local type heads
                    class_heads: List[Tuple[str, ...]] = []
                    for r in refs:
                        rt = tuple(r)
                        if rt == concrete:
                            continue
                        # ignore local types like Chapter*/Finset*
                        if len(rt) >= 1 and (rt[0].startswith("Chapter") or rt[0].startswith("Finset")):
                            continue
                        class_heads.append(rt[:1])
                    for cls in class_heads:
                        key_ci = (cls, concrete)
                        if key_ci not in instance_index:
                            instance_index[key_ci] = inst_name

            # Add all symbol data to the global table
            for sym in sym_list:
                key = tuple(sym["name"])
                if key not in global_symbol_table:
                    global_symbol_table[key] = {}
                global_symbol_table[key]["sym"] = sym

        # --- Pass 2: Build the per-section jixia_name_map ---
        print("Pass 2: Building section maps...")
        for section, data in all_sections_data.items():
            jixia_name_map[section] = {
                "decl": {tuple(d["name"]): d for d in data["decl_list"] if "name" in d},
                "sym": {tuple(s["name"]): s for s in data["sym_list"] if "name" in s},
                "imports": data["imports"]
            }

        print(f"Caching lean analysis data at {cache_path_map}...")
        with open(cache_path_map, "wb") as f:
            pickle.dump(jixia_name_map, f)
        print(f"Caching global symbol table at {cache_path_table}...")
        with open(cache_path_table, "wb") as f:
            pickle.dump(global_symbol_table, f)
        print(f"Caching instance index at {cache_path_instances}...")
        with open(cache_path_instances, "wb") as f:
            pickle.dump(instance_index, f)
    else:
        print("Loading cached lean analysis data...")
        with open(cache_path_map, "rb") as f:
            jixia_name_map = pickle.load(f)
        with open(cache_path_table, "rb") as f:
            global_symbol_table = pickle.load(f)
        with open(cache_path_instances, "rb") as f:
            instance_index = pickle.load(f)

    # Return section-map, new global table, and the instance index
    return jixia_name_map, global_symbol_table, instance_index
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

# --- [MODIFIED FUNCTION: No default values, explicit None checks] ---
def build_context(
    aggregated_baseline_data,
    mapped_lean_analysis_data,
    global_symbol_table,
    instance_index: Dict[Tuple[str, Tuple[str, ...]], Tuple[str, ...]],
    jixia_table,
):
    def check_imports(ref: list):
        if ref[0] not in ["Analysis", "Init"]:
            return True
        return False

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

            def detect_heads_in_closure(symbols: Set[Tuple[str, ...]]) -> Set[str]:
                heads: Set[str] = set()
                for sym in symbols:
                    sd = find_sym_data(sym)
                    if sd is None:
                        continue
                    # Add all reference heads observed in this symbol
                    for key in ("typeReferences", "valueReferences"):
                        if key in sd and sd[key] is not None:
                            for ref in sd[key]:
                                if isinstance(ref, list) and len(ref) > 0:
                                    heads.add(ref[0])
                return heads


            def choose_concrete_type_candidate(symbols: Set[Tuple[str, ...]], syms_for_query: Dict) -> Optional[Tuple[str, ...]]:
                # Prefer a Chapter*/Finset* head if present in type refs of the query symbol
                candidates: List[Tuple[str, ...]] = []
                for key in ("typeReferences",):
                    if key in syms_for_query and syms_for_query[key] is not None:
                        for ref in syms_for_query[key]:
                            if isinstance(ref, list) and len(ref) > 0:
                                t = tuple(ref)
                                if t and (t[0].startswith("Chapter") or t[0].startswith("Finset")):
                                    candidates.append(t)
                if candidates:
                    return candidates[0]
                # Fall back to scanning closure type refs
                seen: Dict[Tuple[str, ...], int] = {}
                for sym in symbols:
                    sd = find_sym_data(sym)
                    if sd is None:
                        continue
                    if "typeReferences" in sd and sd["typeReferences"] is not None:
                        for ref in sd["typeReferences"]:
                            if isinstance(ref, list) and len(ref) > 0:
                                t = tuple(ref)
                                if t and (t[0].startswith("Chapter") or t[0].startswith("Finset")):
                                    if t in seen:
                                        seen[t] = seen[t] + 1
                                    else:
                                        seen[t] = 1
                if seen:
                    # pick the most frequent
                    return sorted(seen.items(), key=lambda kv: (-kv[1], str(kv[0])))[0][0]
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

            # Compute required plumbing (instances and section-declared postfix) before adding defs
            heads_in_closure = detect_heads_in_closure(processed_symbols)

            # Decide concrete type candidate for instance lookups
            concrete_type = choose_concrete_type_candidate(processed_symbols, syms)

            # 1) Include any postfix notations declared in this section by default (raw decl scan)
            def _collect_postfix_from_raw(section_name: str):
                import re as _re
                results: List[Tuple[Tuple[str, ...], str]] = []
                decl_path = jixia_table[section_name]["decl"]
                with open(decl_path, "r") as f:
                    raw = f.read()
                for m in _re.finditer(r"postfix\s*:\s*\d+\s*\\?\"([^\\\"]+)\\?\"\s*=>\s*([A-Za-z0-9_\.]+)", raw):
                    symbol = m.group(1)
                    fqn = m.group(2)
                    if not fqn:
                        continue
                    parts = tuple(fqn.split("."))
                    if not parts:
                        continue
                    ns_tuple = (parts[0],)
                    snippet = f'postfix:100 "{symbol}" => {fqn}'
                    results.append((ns_tuple, snippet))
                return results
            postfix_decls = _collect_postfix_from_raw(section)
            for ns_tuple, snippet in postfix_decls:
                if ns_tuple not in context_dict:
                    context_dict[ns_tuple] = []
                if snippet not in context_dict[ns_tuple]:
                    context_dict[ns_tuple].append(snippet)

            # Inject local instances minimally based on heads observed in closure
            if concrete_type is not None:
                required_heads: Set[str] = set()
                for cls_tuple, t in instance_index.keys():
                    if t == concrete_type and isinstance(cls_tuple, tuple) and len(cls_tuple) >= 1:
                        if cls_tuple[0] in heads_in_closure:
                            required_heads.add(cls_tuple)
                # Add instances if not already in closure (avoid duplicates)
                for h in sorted(required_heads, key=lambda x: str(x)):
                    key = (h, concrete_type)
                    if key not in instance_index:
                        continue
                    inst_name = instance_index[key]
                    if inst_name in processed_symbols:
                        continue
                    # pull pretty text for the instance and add to the appropriate namespace
                    if inst_name not in global_symbol_table or "decl" not in global_symbol_table[inst_name]:
                        continue
                    inst_decl = global_symbol_table[inst_name]["decl"]
                    inst_text = extract_context(inst_decl)
                    if inst_text is None:
                        continue
                    inst_text = re.sub(COMMENT_PATTERN, "", inst_text, flags=re.DOTALL).strip()
                    if not inst_text:
                        continue
                    ns_tuple = tuple(inst_decl["name"][:-1])
                    if ns_tuple not in context_dict:
                        context_dict[ns_tuple] = []
                    if inst_text not in context_dict[ns_tuple]:
                        context_dict[ns_tuple].append(inst_text)

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
                    "content": lean_context, # Use the sorted, namespaced context
                }
            )
       

  
    return test_examples_with_context
# --- [END MODIFIED FUNCTION] ---


# --- [MODIFIED FUNCTION] ---
def main():
    jixia_table = construct_jixia_table()
    # Note the variable name changes here
    mapped_lean_analysis_data, global_symbol_table, instance_index = preprocess_lean_analysis(jixia_table, force_reprocess=True)
    aggregated_baseline_data = preprocess_baseline_data(force_reprocess=True)
    # Pass the new global_symbol_table
    test_examples_with_context = build_context(
        aggregated_baseline_data,
        mapped_lean_analysis_data,
        global_symbol_table,
        instance_index,
        jixia_table,
    )
    
    output_path = os.path.join(OUTPUT_DIR, "tao_analysis_baseline_unwrapped_context.jsonl")
    with open(output_path, "w") as f:
        for example in test_examples_with_context:
            f.write(json.dumps(example) + "\n")
    print(f"Saved {len(test_examples_with_context)} test examples with context to {output_path}")

if __name__ == "__main__":
    main()