import json
from pathlib import Path
import os
from tqdm import tqdm
import dill as pickle
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

BASELINE_PATH = "/Users/alextaylor/Desktop/lean_prover/baseline_data/tao_analysis_baseline.jsonl"

DATA_DIR = "/Users/alextaylor/Desktop/lean_prover/processed_analysis"

OUTPUT_DIR = Path(os.getcwd()) / "baseline_results"
os.makedirs(OUTPUT_DIR, exist_ok=True)
CACHE_DIR = "/Users/alextaylor/Desktop/lean_prover/baseline_approach/.cache"
os.makedirs(CACHE_DIR, exist_ok=True)

ANALYSIS_BOOK_DIRECTORY = "/Users/alextaylor/Desktop/lean_prover/analysis/analysis/Analysis"

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
            }
    return jixia_table

def preprocess_baseline_data():
    baseline_data = load_jsonl(BASELINE_PATH)
    aggregated_data = {}
    for idx, item in enumerate(baseline_data):
        if item["chapter_name"] not in aggregated_data:
            aggregated_data[item["chapter_name"]] = []
        aggregated_data[item["chapter_name"]].append({
            "idx": idx,
            "content": item["content"].strip()
        })

    return aggregated_data


def resolve_external_lookup_pathing(module: list, lookup_tables: dict) -> str:
    if module[0] == "Analysis":
        return lookup_tables[module[1]]
    
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

def render_dependency_set(dependency_set: set[str]) -> str:
    dependency_context = []
    for dep in dependency_set:
        with open(dep, "r") as f:
            dependency_context.append(f.read())
    return "\n".join(dependency_context)

def preprocess_lean_analysis(jixia_table, force_reprocess=False):

    cache_path_dependency = os.path.join(CACHE_DIR, "global_dependency_table_cache.pkl")
    if force_reprocess:
        print("Force reprocessing lean analysis data...")
        if os.path.exists(cache_path_dependency):
            os.remove(cache_path_dependency)
            print("Removed cached lean analysis data (dependency).")

    global_dependency_table = {}
    
    print("Preprocessing jixia analysis data...")
    if not os.path.exists(cache_path_dependency) or force_reprocess:
        print("No cache found. Preprocessing data...")
        
        # --- Pass 1: Build the full global_symbol_table ---
        all_sections_data = {}
        for section in tqdm(sort_by_chapter(jixia_table.keys()), desc="Pass 1: Reading data"):
            contents = jixia_table[section]
            imports = parse_json(contents["mod"])["imports"]
            dependency_set = build_dependency_set(section, imports, global_dependency_table)
          
            all_sections_data[section] = {
                "imports": imports,
                "dependency_set": dependency_set
            }

        print(f"Caching global dependency table at {cache_path_dependency}...")
        with open(cache_path_dependency, "wb") as f:
            pickle.dump(all_sections_data, f)
    else:
        print("Loading cached lean analysis data...")
        with open(cache_path_dependency, "rb") as f:
            all_sections_data = pickle.load(f)
       
    # Return both the section-map and the new global table
    return all_sections_data

def build_query(section, query_base, query_context):
    query = (f"We would like to construct a compilable version of a theorem from {section}. The theorem is as follows:\n{query_base}\n"
    "Please use the following relevant lean files to aggregate the minimum number of statements required to compile the theorem. Please include all necessary imports and properly construct the namespace(s) required for compilation."
    "Do not change the theorem name and do not solve the theorem. You may include necessary external imports, but do not import sections provided below or others in the textbook.\n"
    "The relevant lean files are as follows:\n" + query_context + "\n"
    "Please return the compiled theorem in a valid lean code block wrapped in ```lean tags."
    )
    return query

def build_queries(aggregated_baseline_data, all_sections_data):
    test_examples_with_context = []
    global_idx = 0  # Track global position in queries list to preserve JSONL order

    for section in tqdm(sort_by_chapter(aggregated_baseline_data.keys())):
        contents = aggregated_baseline_data[section]

        for idx, content in enumerate(contents):
                     
            query_base = content["content"]
            query_context = render_dependency_set(all_sections_data[section]["dependency_set"])
            
            query = build_query(section, query_base, query_context)
            
            test_examples_with_context.append(
                {
                    "index": global_idx,
                    "source_idx": content["idx"],
                    "chapter_name": section,
                    "query": query,
                    "content": query_base,
                    "dependency_set": query_context,
                }
            )
            global_idx += 1
  
    return test_examples_with_context

def extract_code_block(content: str) -> str:
    try:
        if "```lean" in content:
            return content.split("```lean", 1)[1].split("```", 1)[0].strip()
        if "```" in content:
            return content.split("```", 1)[1].split("```", 1)[0].strip()
        return content.strip()
    except Exception:
        return content.strip()

def call_api(api_call: str, client: Any) -> str:
    try:
        
        completion = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {"role": "system", "content": "Please format your final response as a valid lean code block wrapped in ```lean tags."},
                {"role": "user", "content": api_call},
            ],
            reasoning_effort="high",
        )
        if completion.choices and completion.choices[0].message:
            content = completion.choices[0].message.content or ""
            return content.strip()
        return ""
    except Exception as e:
        print("ERROR: " + str(e))
        return f"API_ERROR: {e}"

def run_single_api_call(query: dict, client: Any) -> dict:
    api_call = query["query"]
    result = call_api(api_call, client)
    cleaned = extract_code_block(result)
    return {
        "index": query["index"],
        "source_idx": query["source_idx"],
        "chapter_name": query["chapter_name"],
        "content": cleaned,
    }

def run_api_calls(queries: List[dict]) -> List[dict]:
    client = OpenAI(api_key=OPENAI_API_KEY, timeout=1000)
    max_workers = 50
    results_by_index: Dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(run_single_api_call, query, client)
            for query in queries
        ]
        for future in tqdm(as_completed(futures), total=len(futures)):
            res = future.result()
            results_by_index[res["index"]] = res
    ordered_indices = sorted(results_by_index.keys())
    return [results_by_index[idx] for idx in ordered_indices]


def main():
    jixia_table = construct_jixia_table()
    # Note the variable name changes here
    all_sections_data = preprocess_lean_analysis(jixia_table, force_reprocess=True)
    aggregated_baseline_data = preprocess_baseline_data()
    # Pass the new global_symbol_table
    queries = build_queries(aggregated_baseline_data, all_sections_data)
    
    test_examples_with_context = run_api_calls(queries)
    
    output_path = os.path.join(OUTPUT_DIR, "tao_analysis_baseline_gpt_context.jsonl")
    print(f"Saving {len(test_examples_with_context)} test examples with context to {output_path}")
    with open(output_path, "w") as f:
        for example in test_examples_with_context:
            f.write(json.dumps(example) + "\n")
    
    output_path = os.path.join(OUTPUT_DIR, "human_readable_tao_analysis_baseline_gpt_context.txt")
    print(f"Saving {len(test_examples_with_context)} test examples with context to {output_path}")
    with open(output_path, "w") as f:
        for idx, example in enumerate(test_examples_with_context):
            f.write(example["chapter_name"] + ": Example " + str(idx + 1) + "\n\n" + example["content"] + "\n\n")
            f.write("-----------------------------------\n\n")

if __name__ == "__main__":
    main()
