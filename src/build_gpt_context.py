from typing import List, Dict, Any
from tqdm import tqdm
from utils import sort_by_section

def render_dependency_set(dependency_set: set[str]) -> str:
    dependency_context = []
    for dep in dependency_set:
        with open(dep, "r") as f:
            dependency_context.append(f.read())
    return "\n".join(dependency_context)

def build_gpt_context(aggregated_baseline_data: dict, mapped_lean_analysis_data: dict) -> List[Dict[str, Any]]:
    test_examples_with_context = []


    for section in tqdm(sort_by_section(aggregated_baseline_data.keys())):
        contents = aggregated_baseline_data[section]

        for idx, content in enumerate(contents):
            # --- Context Collection Setup (per-query) ---
            query_name = tuple(content["name"])
            query_text = content["content"]
            
            query_context = render_dependency_set(mapped_lean_analysis_data[section]["dependency_set"])
            
            test_examples_with_context.append(
                {
                    "chapter_name": section,
                    "FQN": ".".join(query_name),
                    "content": query_text, # Use the sorted, namespaced context
                    "dependency_set": query_context,
                }
            )
    return test_examples_with_context