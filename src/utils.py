from typing import List, Dict, Any
import json
import os

def make_dir(output_dir: str, dir_path: str) -> str:
    os.makedirs(os.path.join(output_dir, dir_path), exist_ok=True)
    return os.path.join(output_dir, dir_path)
def load_jsonl(file_path: str) -> List[Dict[str, Any]]:
    with open(file_path, "r") as f:
        return [json.loads(line) for line in f]  
    
def load_json(file_path: str) -> Dict[str, Any]:
    with open(file_path, "r") as f:
        return json.load(f)  
    
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

def sort_by_section(sections: list) -> list:
    return sorted(sections, key=lambda x: (int(x.split("_")[1]), x.split("_")[2].split(".")[0]))