import json
import argparse
import os

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl_path", type=str)
    args = parser.parse_args()
    jsonl_to_hr(args.jsonl_path)

def jsonl_to_hr(jsonl_path: str):
    hr_path = os.path.join(os.path.dirname(jsonl_path), "human_readable_" + os.path.basename(jsonl_path).replace(".jsonl", ".txt"))
    with open(jsonl_path, "r") as f:
        data = [json.loads(line) for line in f]
    with open(hr_path, "w") as f:
        for idx, example in enumerate(data):
            f.write(example["chapter_name"] + ": Example " + str(idx + 1) + "\n\n" + example["content"] + "\n\n")
            f.write("-----------------------------------\n\n")

if __name__ == "__main__":
    main()