import json
from typing import Dict, Any

def construct_query_jixia_gpt(query: Dict[str, Any]) -> str:
    content = query["content"]
    dependency_set = query["dependency_set"]
    fqn = query["FQN"]
    message = "\n".join([
            dependency_set,
            "Please use the above lean files to evaluate the below context.",
            f"We have constructed a minimal context for theorem {fqn} that does not currently compile.",
            "Please consider the source code and produce a version of the theorem with minimal updates that compiles."
            "Do not change the code of the {fqn} theorem. Do not solve the theorem.",
            "Theorem:\n" + content
        ])
    
    return message

def construct_query_gpt(query: Dict[str, Any]) -> str:
    message = (f"We would like to construct a compilable version of a theorem from {query['chapter_name']}. The theorem is as follows:\n{query['content']}\n"
    "Please use the following relevant lean files to aggregate the minimum number of statements required to compile the theorem. Please include all necessary imports and properly construct the namespace(s) required for compilation."
    "Do not change the theorem name and do not solve the theorem. You may include necessary external imports, but do not import sections provided below or others in the textbook.\n"
    "The relevant lean files are as follows:\n" + query['dependency_set'] + "\n"
    "Please return the compiled theorem in a valid lean code block wrapped in ```lean tags."
    )
    return message