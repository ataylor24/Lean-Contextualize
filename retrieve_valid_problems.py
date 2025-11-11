import json

def main():
    verification_path = "results.json"
    data_path = "second_pass_api_check/cleaned_stream.jsonl"
    
    verified_results = []
    with open(verification_path, "r") as f:
        verification_results = json.load(f)
    with open(data_path, "r") as f:
        data = [json.loads(line) for line in f]
    for verification_result in verification_results:
        if verification_result["status"] == "ok":
            
            verified_results.append({key:value for key, value in data[verification_result["index"]].items() if key in ["chapter_name", "FQN", "content"]})
    
    with open("verified_results.jsonl", "w") as f:
        for verified_result in verified_results:
            f.write(json.dumps(verified_result) + "\n")
    
    print(f"Saved {len(verified_results)} verified results to verified_results.jsonl")

if __name__ == "__main__":
    main()