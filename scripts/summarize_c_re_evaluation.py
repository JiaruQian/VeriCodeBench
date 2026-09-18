#!/usr/bin/env python3
import json
from pathlib import Path

RUNS = {
    "deepseek-default": {"base": "outputs/req2code-base-0622", "base+ce": "outputs/C-ce-only-0623-old", "base+repair": "outputs/C-wybecoder-0623", "base+ce+repair": "outputs/C-ce-wybecoder-0623"},
    "kimi-k2.7-code": {"base": "outputs/C-base-kimi-0629", "base+ce": "outputs/C-ce-kimi-0630", "base+repair": "outputs/C-wybecoder-kimi-0630", "base+ce+repair": "outputs/C-ce-wybecoder-kimi-0630"},
    "qwen3.6-plus": {"base": "outputs/C-base-qwen36plus-0625", "base+ce": "outputs/C-ce-qwen-0626", "base+repair": "outputs/C-wybecoder-qwen-0626", "base+ce+repair": "outputs/C-ce-wybecoder-qwen-0627"},
    "claude-sonnet-5": {"base": "outputs/C-base-claude-0706", "base+ce": "outputs/C-ce-claude-0706", "base+repair": "outputs/C-wybecoder-claude-0706", "base+ce+repair": "outputs/C-ce-wybecoder-claude-0706"},
}

rows = []
for model, variants in RUNS.items():
    for variant, directory in variants.items():
        row = {"model": model, "variant": variant, "output_dir": directory}
        if directory is None:
            row["status"] = "missing_output_dir"
        else:
            summary = json.loads(Path(directory, "reports", "benchmark_summary.json").read_text())["summary"]
            row.update({"status": "ok", "code_validity_rate": summary["code_validity_rate"], "requirement_coverage_macro": summary["requirement_coverage_macro"], "joint_success_rate": summary["joint_success_rate"], "code_valid_count": summary["code_valid_count"], "joint_success_count": summary["joint_success_count"]})
        rows.append(row)

out = Path("outputs/c_re_evaluation_current.json")
out.write_text(json.dumps({"ground_truth": "benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json", "rows": rows}, ensure_ascii=False, indent=2) + "\n")
for row in rows:
    print(row)
print(f"wrote {out}")
