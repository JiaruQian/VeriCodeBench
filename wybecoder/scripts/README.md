# Scripts

Utility scripts for dataset preparation, trajectory analysis, and evaluation.

## Dataset Preparation

| Script | Description |
|--------|-------------|
| `clever_to_jsonl.py` | Extract CLEVER `.lean` files into a single JSONL dataset. |
| `verina_to_loom.py` | Convert Verina tasks into Loom method specifications and unsatisfiability theorems. |
| `convert_verina_tests.py` | Convert Verina test cases to Lean `#guard` statements. |
| `simplify_preamble.py` | Standardize the `loom_header` field across dataset JSONL files. |
| `data_processing/clever_add_loom_tests_to_specs.py` | Merge Loom test cases into CLEVER specifications. |

## Evaluation & Analysis

| Script | Description |
|--------|-------------|
| `run_all.py` | Validate JSONL entries against LeanRepl (checks for errors and `sorry` statements). |
| `detect_bad_trajs.py` | Scan passing trajectories for `sorry`, `SMTSorry`, or excessive axiom usage. |
| `confusion.py` | Build a confusion matrix between critique categories and pass status. |
| `create_report.py` | Summarize aborted trajectories using LLM-based reduction. |

