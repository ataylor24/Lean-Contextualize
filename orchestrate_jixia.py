import os
import subprocess
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial

TEXTBOOK_PATH = "/Users/alextaylor/Desktop/lean_prover/analysis/analysis/Analysis"
JIXIA_EXECUTABLE = "/Users/alextaylor/Desktop/lean_prover/jixia/.lake/build/bin/jixia"
ANALYSIS_WORKSPACE = "/Users/alextaylor/Desktop/lean_prover/analysis/analysis"
PROCESSED_ANALYSIS_WORKSPACE = (
    "/Users/alextaylor/Desktop/lean_prover/processed_analysis"
)


def clean_textbook_filepaths(path: str):
    section_files = []
    for file in os.listdir(path):
        if file.startswith("Section_") and file.endswith(".lean"):
            section_files.append(os.path.join(path, file))
    section_files.sort(
        key=lambda x: (
            int(os.path.basename(x).split("_")[1]),
            os.path.basename(x).split("_")[2].split(".")[0],
        )
    )
    return section_files


def compile_lean_file(file_path: str, section_key: str):
    module_file_path = file_path.replace(".lean", ".mod.json")
    declaration_file_path = file_path.replace(".lean", ".decl.json")
    symbol_file_path = file_path.replace(".lean", ".sym.json")
    elaboration_file_path = file_path.replace(".lean", ".elab.json")
    lines_file_path = file_path.replace(".lean", ".lines.json")
    ast_file_path = file_path.replace(".lean", ".ast.json")

    # Run jixia
    proc = subprocess.run(
        [
            "lake",
            "env",
            JIXIA_EXECUTABLE,
            "-i",
            "-m",
            module_file_path,
            "-d",
            declaration_file_path,
            "-s",
            symbol_file_path,
            "-e",
            elaboration_file_path,
            "-l",
            lines_file_path,
            "-a",
            ast_file_path,
            file_path,
        ],
        cwd=ANALYSIS_WORKSPACE,
        capture_output=True,
        text=True,
    )
    
    if proc.returncode != 0:
        raise RuntimeError(
            f"jixia failed for {file_path} (exit {proc.returncode}).\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )

    # Move processed files into their own folder
    section_workspace = os.path.join(PROCESSED_ANALYSIS_WORKSPACE, section_key)
    os.makedirs(section_workspace, exist_ok=True)

    return {
        "module": shutil.move(
            module_file_path,
            os.path.join(section_workspace, os.path.basename(module_file_path)),
        ),
        "declaration": shutil.move(
            declaration_file_path,
            os.path.join(section_workspace, os.path.basename(declaration_file_path)),
        ),
        "symbol": shutil.move(
            symbol_file_path,
            os.path.join(section_workspace, os.path.basename(symbol_file_path)),
        ),
        "elaboration": shutil.move(
            elaboration_file_path,
            os.path.join(section_workspace, os.path.basename(elaboration_file_path)),
        ),
        "lines": shutil.move(
            lines_file_path,
            os.path.join(section_workspace, os.path.basename(lines_file_path)),
        ),
        "ast": shutil.move(
            ast_file_path,
            os.path.join(section_workspace, os.path.basename(ast_file_path)),
        ),
    }


def _compile_one(file_path: str):
    section_key = os.path.basename(file_path).replace(".lean", "")
    result = compile_lean_file(file_path, section_key)
    return section_key, result


def main():
    os.makedirs(PROCESSED_ANALYSIS_WORKSPACE, exist_ok=True)
    section_files = clean_textbook_filepaths(TEXTBOOK_PATH)
    processed_data = {}
    parallelized = True
    # Don’t exceed cores; leave one core free for the OS
    max_workers = 4

    # If Lake/Jixia thrashes your disk/cores, tune this down (e.g., 2–4)
    # max_workers = 4

    if parallelized:
        with ProcessPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_compile_one, fp): fp for fp in section_files}
            for fut in as_completed(futures):
                fp = futures[fut]
                try:
                    section_key, section_data = fut.result()
                    processed_data[section_key] = section_data
                    print(f"Done: {section_key}")
                except Exception as e:
                    # Keep going; log the failure
                    print(f"[ERROR] Failed on {fp}: {e}")
    else:
        for fp in section_files:
            section_key = os.path.basename(fp).replace(".lean", "")
            if section_key != "Section_3_1":
                continue
            try:
                section_key, section_data = _compile_one(fp)
                processed_data[section_key] = section_data
                print(section_data)
                print(f"Done: {section_key}")
            except Exception as e:
                # Keep going; log the failure
                print(f"[ERROR] Failed on {fp}: {e}")

    # Optionally, inspect the aggregate
    print("All finished.")
    print(f"{len(processed_data)} sections processed.")


if __name__ == "__main__":
    main()
