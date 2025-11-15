import os
import json
from typing import List, Dict, Any
from openai import OpenAI
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from dotenv import load_dotenv
import argparse
from utils import load_jsonl, load_json
load_dotenv()
    
def load_data(file_path: str) -> List[Dict[str, Any]]:
    if file_path.endswith(".jsonl"):
        return load_jsonl(file_path)
    elif file_path.endswith(".json"):
        return load_json(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_path}")
    
def extract_code_block(content: str) -> str:
    try:
        if "```lean" in content:
            return content.split("```lean", 1)[1].split("```", 1)[0].strip()
        if "```" in content:
            return content.split("```", 1)[1].split("```", 1)[0].strip()
        return content.strip()
    except Exception:
        return content.strip()
    
def run_api_call(api_call: str, client: Any) -> str:
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

def process_single_query(index: int, query: Dict[str, Any], client: Any) -> Dict[str, Any]:
    result = run_api_call(query["query"], client)
    cleaned_result = extract_code_block(result)
    updated_entry = {
        "chapter_name": query["chapter_name"],
        "FQN": query["FQN"],
        "content": cleaned_result,
    }
    log_entry = {
        "query": {**query, "content": cleaned_result},
        "result": result,
    }
    return {"index": index, "updated_entry": updated_entry, "log_entry": log_entry}

def main(data: List[Dict[str, Any]], output_dir: str, name: str):
    max_workers = 75
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=1000)
    results_by_index: Dict[int, Dict[str, Any]] = {}
    updated_by_index: Dict[int, Dict[str, Any]] = {}

    stream_log_path = os.path.join(output_dir, f"{name}_api_call_stream.jsonl")
    stream_cleaned_path = os.path.join(output_dir, f"{name}_cleaned_stream.jsonl")

    with ThreadPoolExecutor(max_workers=max_workers) as executor, \
         open(stream_log_path, "a") as stream_log_f, \
         open(stream_cleaned_path, "a") as stream_cleaned_f:
        futures = {
            executor.submit(process_single_query, i, q, client): i
            for i, q in enumerate(data)
        }
        for future in tqdm(as_completed(futures), total=len(futures)):
            idx = futures[future]
            try:
                res = future.result()
                updated_by_index[idx] = res["updated_entry"]
                results_by_index[idx] = res["log_entry"]
                # Stream full log line
                stream_log_f.write(json.dumps({
                    "timestamp": time.time(),
                    "index": idx,
                    "status": "updated",
                    "FQN": res["updated_entry"]["FQN"],
                    "chapter_name": res["updated_entry"]["chapter_name"],
                    "result": res["log_entry"]["result"],
                }) + "\n")
                stream_log_f.flush()
                # Stream cleaned content line
                stream_cleaned_f.write(json.dumps({
                    "timestamp": time.time(),
                    "index": idx,
                    **res["updated_entry"],
                }) + "\n")
                stream_cleaned_f.flush()
            except Exception as e:
                results_by_index[idx] = {"error": f"PROCESSING_ERROR: {e}"}
                stream_log_f.write(json.dumps({
                    "timestamp": time.time(),
                    "index": idx,
                    "status": "error",
                    "error": str(e),
                }) + "\n")
                stream_log_f.flush()

    # Preserve input order in outputs
    ordered_indices = sorted(updated_by_index.keys())
    updated_data = [updated_by_index[i] for i in ordered_indices]
    results = [results_by_index[i] for i in sorted(results_by_index.keys())]

    with open(os.path.join(output_dir, f"{name}_api_call_logging.json"), "w") as f:
        json.dump(results, f, indent=4)
    
    with open(os.path.join(output_dir, f"{name}.json"), "w") as f:
        json.dump(updated_data, f, indent=4)
        
    with open(os.path.join(output_dir, f"human_readable_{name}.txt"), "w") as f:
        for example in updated_data:
            f.write(example["chapter_name"] + ": " + example["FQN"] + "\n\n" + example["content"] + "\n\n")
            f.write("-----------------------------------\n\n")
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("data_path", type=str)
    parser.add_argument("output_dir", type=str)
    parser.add_argument("name", type=str)
    args = parser.parse_args()
    data_path = args.data_path
    output_dir = args.output_dir
    name = args.name
    os.makedirs(output_dir, exist_ok=True)
    data = load_data(data_path)
    main(data, output_dir, name)
