import argparse
import json
import sys
from pathlib import Path

base_dir = "/Users/alextaylor/Desktop/lean_prover/processed_analysis/Section_10_2"
decl_file = Path(base_dir) / "Section_10_2.decl.json"
elab_file = Path(base_dir) / "Section_10_2.elab.json"
sym_file = Path(base_dir) / "Section_10_2.sym.json"

def parse_json(file):
    with open(file, "r") as f:
        return json.load(f)

def child_depth(child_node):
    
    if "children" not in child_node or len(child_node["children"]) == 0:
        return 0
    else:
        children = 0
        for child in child_node["children"]:
            children += child_depth(child)
          
        return 1 + children

def mine_child_type(child_node):

    if len(child_node["children"]) == 0:
        if "term" in child_node["info"] and "termConstRefs" in child_node["info"]["term"]:

            return set(child_node["info"]["term"]["typeConstRefs"]), set(child_node["info"]["term"]["termConstRefs"])
        else:
            return set(), set()
    else:
        child_types = (set(), set())
        for child in child_node["children"]:
            type_refs, term_refs = mine_child_type(child)
            child_types[0].update(type_refs)
            child_types[1].update(term_refs)
        return child_types

def print_json(name, data):
    for item in data:
        printable = False
        # print(item["kind"], item["name"])
        # if "ref" in item and "str" in item["ref"] and "(2:Nat) + 3 = 5 := by" in item["ref"]["str"]:
        necessary_types = set()
        if "children" in item:
            # print("num_children", len(item["children"]))
            for child in item["children"]:

                if "term" in child["info"] and "type" in child["info"]["term"] and child["info"]["term"]["type"] == "Prop":
                    printable = True
                    
                    type_refs, term_refs = mine_child_type(child)
                    necessary_types.update(type_refs)
                    necessary_types.update(term_refs)
                        # print(child["ref"]["str"])
                        
                        # print("------------------------------------------")
        if printable:
            print(item["ref"]["str"])
            print(necessary_types, f"({len(necessary_types)})")
            print("--------------------------------")


def main():
    elab_data = parse_json(elab_file)

    print_json("elab", elab_data)


if __name__ == "__main__":
    main()
