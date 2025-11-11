import os
import json
from typing import List, Dict, Any
from openai import OpenAI
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

OPENAI_API_KEY = "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"

OUTPUT_DIR = "second_pass_api_check"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def temp_combine_files(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    error_messages = json.load(open("results.json"))
    for index in error_messages:
        data[int(index)].update(error_messages[index])
    return data

def read_jsonl(file_path: str) -> List[Dict[str, Any]]:
    with open(file_path, "r") as f:
        return [json.loads(line) for line in f]

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
            reasoning_effort="medium",
        )
        if completion.choices and completion.choices[0].message:
            content = completion.choices[0].message.content or ""
            return content.strip()
        return ""
    except Exception as e:
        return f"API_ERROR: {e}"

def construct_api_call(query: Dict[str, Any]) -> str:
    content = query["content"]
    dependency_set = query["dependency_set"]
    fqn = query["FQN"]
    error_message = json.dumps(query["first_error"])
    api_call = "\n".join([
            dependency_set,
            "Please use the above lean files to evaluate the below context.",
            f"We have constructed a context for theorem {fqn} that does not currently compile.",
            "We have included the failing error message in addition to the relevant context.",
            "Please consider the source code and produce a version of the theorem with minimal updates that compiles."
            "Do not change the theorem name or the namespace, or change existing code. Do not solve the theorem.",
            "The failing error message is: " + error_message,
            "Theorem:\n" + content
        ])
    
    return api_call

def process_single_query(index: int, query: Dict[str, Any], client: Any) -> Dict[str, Any]:
    api_call = construct_api_call(query)
    result = run_api_call(api_call, client)
    cleaned = extract_code_block(result)
    updated_entry = {
        "chapter_name": query["chapter_name"],
        "FQN": query["FQN"],
        "content": cleaned,
    }
    log_entry = {
        "query": {**query, "content": cleaned},
        "api_call": api_call,
        "result": result,
    }
    return {"index": index, "updated_entry": updated_entry, "log_entry": log_entry}

def main(data: List[Dict[str, Any]]):
    client = OpenAI(api_key=OPENAI_API_KEY, timeout=1000)
    results_by_index: Dict[int, Dict[str, Any]] = {}
    updated_by_index: Dict[int, Dict[str, Any]] = {}

    stream_log_path = os.path.join(OUTPUT_DIR, "api_call_stream.jsonl")
    stream_cleaned_path = os.path.join(OUTPUT_DIR, "cleaned_stream.jsonl")

    with ThreadPoolExecutor(max_workers=10) as executor, \
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

    with open(os.path.join(OUTPUT_DIR, "api_call_logging.json"), "w") as f:
        json.dump(results, f, indent=4)
    
    with open(os.path.join(OUTPUT_DIR, "cleaned_tao_analysis_baseline_wrapped_context.json"), "w") as f:
        json.dump(updated_data, f, indent=4)
    

if __name__ == "__main__":
    data_path = os.path.join(os.path.dirname(__file__), "tao_analysis_baseline_wrapped_context.jsonl")
    data = read_jsonl(data_path)
    data = temp_combine_files(data)
    main(data)