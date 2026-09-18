#!/usr/bin/env python3
import json
from pathlib import Path

RUNS = {
    "deepseek-default": {"direct": "outputs/req2code-base-0622", "cgs": "outputs/C-cgs-only-0623-old", "vgcr": "outputs/C-vgcr-0623", "codenova": "outputs/C-cgs-vgcr-0623"},
    "kimi-k2.7-code": {"direct": "outputs/C-base-kimi-0629", "cgs": "outputs/C-cgs-kimi-0630", "vgcr": "outputs/C-vgcr-kimi-0630", "codenova": "outputs/C-cgs-vgcr-kimi-0630"},
    "qwen3.6-plus": {"direct": "outputs/C-base-qwen36plus-0625", "cgs": "outputs/C-cgs-qwen-0626", "vgcr": "outputs/C-vgcr-qwen-0626", "codenova": "outputs/C-cgs-vgcr-qwen-0627"},
    "claude-sonnet-5": {"direct": "outputs/C-base-claude-0706", "cgs": "outputs/C-cgs-claude-0706", "vgcr": "outputs/C-vgcr-claude-0706", "codenova": "outputs/C-cgs-vgcr-claude-0706"},
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
