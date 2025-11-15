import argparse
import os
from globals import JIXIA_DATA_DIR, BASELINE_DATA_PATH, CACHE_DIR, JIXIA_WORKING_DIR, OUTPUT_DIR
from tqdm import tqdm
import json
from utils import load_json, load_jsonl, filter_baseline, make_dir
from jixia_lean_utils import process_snippet, preprocess_lean_analysis
from build_jixia_context import build_jixia_context
from build_gpt_context import build_gpt_context
from construct_queries import construct_query_jixia_gpt, construct_query_gpt

def preprocess_baseline_data(force_reprocess: bool = False):
    if force_reprocess:
        print("Force reprocessing baseline data...")
        if os.path.exists(os.path.join(CACHE_DIR, "aggregated_baseline_data_cache.json")):
            os.remove(os.path.join(CACHE_DIR, "aggregated_baseline_data_cache.json"))
            print("Removed cached baseline data.")
        else:
            print("No cached baseline data found.")
    os.makedirs(JIXIA_WORKING_DIR, exist_ok=True)
    baseline_data = load_jsonl(BASELINE_DATA_PATH)
    aggregated_baseline_data = filter_baseline(baseline_data)
    print("Preprocessing baseline data...")
    if not os.path.exists(os.path.join(CACHE_DIR, "aggregated_baseline_data_cache.json")) or force_reprocess:
        print("No cache found. Preprocessing data, this may take a while...")
        for section, contents in tqdm(aggregated_baseline_data.items()):
            for content in contents:
                decl_json = process_snippet(content["content"], section, int(content["idx"]))
                name = load_json(decl_json)[0]["name"]
                content["name"] = tuple(name)
        print(f"Caching baseline data at {os.path.join(CACHE_DIR, 'aggregated_baseline_data_cache.json')}...")
        with open(os.path.join(CACHE_DIR, "aggregated_baseline_data_cache.json"), "w") as f:
            json.dump(aggregated_baseline_data, f)
            
    else:
        print("Loading cached baseline data...")
        with open(os.path.join(CACHE_DIR, "aggregated_baseline_data_cache.json"), "r") as f:
            aggregated_baseline_data = json.load(f)

    return aggregated_baseline_data

def construct_jixia_table():
    jixia_table = {}
    os.listdir(JIXIA_DATA_DIR)
    for section in os.listdir(JIXIA_DATA_DIR):
        if section.startswith("Section_"):
            section_path = os.path.join(JIXIA_DATA_DIR, section)
            jixia_table[section] = {
                "mod": os.path.join(section_path, f"{section}.mod.json"),
                "decl": os.path.join(section_path, f"{section}.decl.json"),
                "sym": os.path.join(section_path, f"{section}.sym.json"),
            }
    return jixia_table

def main(method: str, output_name: str):
    output_path = os.path.join(OUTPUT_DIR, output_name)
    jixia_table = construct_jixia_table()
    mapped_lean_analysis_data, global_symbol_table, global_dependency_table = preprocess_lean_analysis(jixia_table, force_reprocess=False)
    aggregated_baseline_data = preprocess_baseline_data(force_reprocess=False)

    if method == "jixia_gpt":
        print("global_dependency_table", global_dependency_table)
        processed_data = build_jixia_context(aggregated_baseline_data, mapped_lean_analysis_data, global_symbol_table, global_dependency_table)
        for query in processed_data:
            query["query"] = construct_query_jixia_gpt(query)
    elif method == "gpt":
        processed_data = build_gpt_context(aggregated_baseline_data, mapped_lean_analysis_data)
        for query in processed_data:
            query["query"] = construct_query_gpt(query)
    else:
        raise ValueError(f"Invalid method: {method}")
    
    with open(os.path.join(output_path, f"processed_data_{method}.jsonl"), "w") as f:
        for query in processed_data:
            f.write(json.dumps(query) + "\n")
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", type=str, required=True)
    parser.add_argument("--output_name", type=str, required=True)
    args = parser.parse_args()
    method = args.method
    output_name = args.output_name
    main(method, output_name)