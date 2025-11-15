import argparse
import json
import re

pattern = r'(?s)(theorem\b(?:(?!\btheorem\b).)*?:=\s*by(?:(?!\btheorem\b).)*?\bsorry\b)'
fqn_pattern = r"(?m)^(\s*theorem\s+)(?:[A-Za-z0-9_]+\.)+([A-Za-z0-9_']+)"

replacement = r'\1\2'

BASELINE_PATH = "../baseline_data/tao_analysis_baseline.jsonl"

def remove_whitespace(text: str) -> str:
    return text.strip().replace(" ", "").replace("\n", "")

def extract_last_theorem_block(text: str) -> str | None:
    matches = list(re.finditer(pattern, text))
    return matches[-1].group(1) if matches else None

def strip_fqn_in_theorem_name(text: str) -> str:
    try:
        return re.sub(fqn_pattern, replacement, text)
    except Exception as e:
        return ""

def load_jsonl(jsonl_path: str) -> list[dict]:
    with open(jsonl_path, "r") as f:
        data = [json.loads(line) for line in f]
    if "index" in data[0]:
        data.sort(key=lambda x: x["index"])
    else:
        data.sort(key=lambda x: (int(x["chapter_name"].split("_")[1]), x["chapter_name"].split("_")[2].split(".")[0]))
    return data

def verify_theorem_presence(jsonl_path: str, baseline_data: list[dict]):
    data = load_jsonl(jsonl_path)
    missing = []
    for idx, item in enumerate(baseline_data):
        content = item["content"].strip()
        ground_truth = strip_fqn_in_theorem_name(extract_last_theorem_block(content))
        extracted_theorem = strip_fqn_in_theorem_name(extract_last_theorem_block(data[idx]["content"]))
        
        removed_whitespace_extracted_theorem = remove_whitespace(extracted_theorem)
        removed_whitespace_content = remove_whitespace(ground_truth)
        if removed_whitespace_extracted_theorem != removed_whitespace_content:
            print(idx)
            missing.append(item)
            print("-" * 80)
            print(extracted_theorem)
            print("-" * 40)
            print(item["content"])
            print("-" * 80)
         
            
    return missing

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl_path", type=str)
    args = parser.parse_args()
    baseline_data = load_jsonl(BASELINE_PATH)
    missing = verify_theorem_presence(args.jsonl_path, baseline_data)
    print(f"Missing {len(missing)} theorems")
    for item in missing:
        print(item["content"])
        print("-" * 80)

if __name__ == "__main__":
    main()