import os
import subprocess
from tqdm import tqdm
from globals import JIXIA_WORKING_DIR, JIXIA_EXECUTABLE, CACHE_DIR, ANALYSIS_BOOK_DIRECTORY
from utils import load_json, sort_by_section
import pickle

def build_dependency_set(src_module: str, imports: list, g: dict) -> set:
    deps = {src_module}  # keep self
    for mod in imports:
        if mod[0] in ("Init", "Mathlib"):
            continue
        if mod[0] != "Analysis":
            continue
        
        parts = mod[1:]
        if not parts:
            continue
        if mod[1] == "Tools":
            fqn = mod[1] + "/" + ".".join(mod[2:])
        else:
            fqn = ".".join(parts)

        # seed unseen/empty modules with themselves
        if fqn not in g or not g[fqn]:
            g[fqn] = {fqn}

        # include the immediate import and whatever we know so far
        deps.add(fqn)
        deps |= g[fqn]

    g[src_module] = deps
    
    dep_file_paths = [os.path.join(ANALYSIS_BOOK_DIRECTORY, f"{dep}.lean") for dep in deps]
    return dep_file_paths

def process_snippet(question_string: str, section: str, idx: int):
    section_workspace = os.path.join(JIXIA_WORKING_DIR, section)
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
        cwd=JIXIA_WORKING_DIR,
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

def preprocess_lean_analysis(jixia_table, force_reprocess=False):
    cache_path_map = os.path.join(CACHE_DIR, "jixia_name_map_cache.pkl")
    cache_path_table = os.path.join(CACHE_DIR, "global_symbol_table_cache.pkl")
    cache_path_dependency = os.path.join(CACHE_DIR, "global_dependency_table_cache.pkl")
    if force_reprocess:
        print("Force reprocessing lean analysis data...")
        if os.path.exists(cache_path_map):
            os.remove(cache_path_map)
            print("Removed cached lean analysis data (map).")
        if os.path.exists(cache_path_table):
            os.remove(cache_path_table)
            print("Removed cached lean analysis data (table).")

    jixia_name_map = {}
    # This is the new unified table.
    # It will map: Tuple[str, ...] -> {"decl": decl_obj, "sym": sym_obj}
    global_symbol_table = {}
    global_dependency_table = {}
    
    print("Preprocessing jixia analysis data...")
    if not os.path.exists(cache_path_map) or not os.path.exists(cache_path_table) or force_reprocess:
        print("No cache found. Preprocessing data...")
        
        # --- Pass 1: Build the full global_symbol_table ---
        all_sections_data = {}
        for section in tqdm(sort_by_section(jixia_table.keys()), desc="Pass 1: Reading data"):
            contents = jixia_table[section]
            decl_list = load_json(contents["decl"])
            sym_list = load_json(contents["sym"])
            imports = load_json(contents["mod"])["imports"]
            dependency_set = build_dependency_set(section, imports, global_dependency_table)
            
            all_sections_data[section] = {
                "decl_list": decl_list,
                "sym_list": sym_list,
                "imports": imports,
                "dependency_set": dependency_set
            }
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
                "imports": data["imports"],
                "dependency_set": data["dependency_set"]
            }

        print(f"Caching lean analysis data at {cache_path_map}...")
        with open(cache_path_map, "wb") as f:
            pickle.dump(jixia_name_map, f)
        print(f"Caching global symbol table at {cache_path_table}...")
        with open(cache_path_table, "wb") as f:
            pickle.dump(global_symbol_table, f)
        print(f"Caching global dependency table at {cache_path_dependency}...")
        with open(cache_path_dependency, "wb") as f:
            pickle.dump(global_dependency_table, f)
    else:
        print("Loading cached lean analysis data...")
        with open(cache_path_map, "rb") as f:
            jixia_name_map = pickle.load(f)
        with open(cache_path_table, "rb") as f:
            global_symbol_table = pickle.load(f)
        with open(cache_path_dependency, "rb") as f:
            global_dependency_table = pickle.load(f)
    # Return both the section-map and the new global table
    return jixia_name_map, global_symbol_table, global_dependency_table