import os
JIXIA_EXECUTABLE = "/Users/alextaylor/dev/jixia/.lake/build/bin/jixia"
JIXIA_DATA_DIR = "/Users/alextaylor/Desktop/lean_prover/processed_analysis"
BASELINE_DATA_PATH = "/Users/alextaylor/Desktop/lean_prover/baseline_data/tao_analysis_baseline.jsonl"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
JIXIA_WORKING_DIR = os.path.join(os.path.dirname(__file__), "jixia_working_dir")
CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(JIXIA_WORKING_DIR, exist_ok=True)
ANALYSIS_BOOK_DIRECTORY = "/Users/alextaylor/Desktop/lean_prover/analysis/analysis/Analysis"

MAX_DEPTH = -1
COMMENT_PATTERN = r"/\-[\-]?.*?\-\/"
