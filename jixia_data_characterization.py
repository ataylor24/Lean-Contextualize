import json
import os

working_dir_path = "/Users/alextaylor/Desktop/lean_prover/processed_analysis"

for section_dir in os.listdir(working_dir_path):
    if not "Section" in section_dir:
        continue
    sym_path = os.path.join(working_dir_path, section_dir, section_dir + ".sym.json")
    decl_path = os.path.join(working_dir_path, section_dir, section_dir + ".decl.json")
    
    sym_json = json.load(open(sym_path))
    decl_json = json.load(open(decl_path))

    sym_names = {tuple(item["name"]) for item in sym_json}
    decl_names = {tuple(item["name"]) for item in decl_json}

    print("Section: ", section_dir)
    print("len(sym_names): ", len(sym_names))
    print("len(decl_names): ", len(decl_names))
    print("len(sym_names - decl_names): ", len(sym_names - decl_names))
    print("len(decl_names - sym_names): ", len(decl_names - sym_names))

    if len(decl_names - sym_names) > 0:
        print(decl_names - sym_names)

    
