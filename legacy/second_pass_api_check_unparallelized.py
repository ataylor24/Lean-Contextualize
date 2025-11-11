import os
import json
from typing import List, Dict, Any
from openai import OpenAI
from tqdm import tqdm

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
    return content.split("```lean")[1].split("```")[0].strip()
    
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

def main(data: List[Dict[str, Any]]):
    client = OpenAI(api_key=OPENAI_API_KEY, timeout=1000)
    results = []
    updated_data = []
  
    for query in tqdm(data):
     
        api_call = construct_api_call(query)
       
        # run the api call
        result = run_api_call(api_call, client)
        
        query["content"] = extract_code_block(result)
        updated_data.append({
            "chapter_name": query["chapter_name"],
            "FQN": query["FQN"],
            "content": extract_code_block(result),
        })
        results.append({
            "query": query,
            "api_call": api_call,
            "result": result,
        })
        
    
    with open(os.path.join(OUTPUT_DIR, "api_call_logging.json"), "w") as f:
        json.dump(results, f, indent=4)
    
    with open(os.path.join(OUTPUT_DIR, "cleaned_tao_analysis_baseline_wrapped_context.json"), "w") as f:
        json.dump(updated_data, f, indent=4)
    

if __name__ == "__main__":
    data_path = os.path.join(os.path.dirname(__file__), "tao_analysis_baseline_wrapped_context.jsonl")
    data = read_jsonl(data_path)
    data = temp_combine_files(data)
    main(data)