#!/usr/bin/env python3
"""Reconcile a repaired Python variant with its frozen baseline monotonically."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Dict


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Keep repair code only for baseline-invalid/repair-valid problems and "
            "restore all frozen baseline specs."
        )
    )
    parser.add_argument("--baseline-output-dir", type=Path, required=True)
    parser.add_argument("--repair-output-dir", type=Path, required=True)
    return parser.parse_args()


def _load_report(output_dir: Path) -> Dict[str, Any]:
    return json.loads((output_dir / "reports" / "results.json").read_text())


def _valid(row: Dict[str, Any]) -> bool:
    return bool((row.get("verification") or {}).get("valid"))


def _copy_log(source_row: Dict[str, Any], target: Path) -> str:
    source_text = str((source_row.get("verification") or {}).get("details_file") or "")
    source = Path(source_text)
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_file():
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
    else:
        target.write_text(str((source_row.get("verification") or {}).get("message") or ""))
    return str(target)


def main() -> None:
    args = parse_args()
    baseline_dir = args.baseline_output_dir.resolve()
    repair_dir = args.repair_output_dir.resolve()
    if baseline_dir == repair_dir:
        raise SystemExit("baseline and repair directories must differ")

    baseline_report = _load_report(baseline_dir)
    repair_report = _load_report(repair_dir)
    baseline_rows = {int(row["id"]): row for row in baseline_report.get("results", [])}
    repair_rows = {int(row["id"]): row for row in repair_report.get("results", [])}
    if set(baseline_rows) != set(repair_rows):
        raise SystemExit("baseline and repair reports contain different problem ids")

    repair_specs = repair_dir / "specs"
    if repair_specs.exists():
        shutil.rmtree(repair_specs)
    shutil.copytree(baseline_dir / "specs", repair_specs)

    accepted_repairs = []
    retained_baseline = []
    reconciled_rows = []
    for problem_id in sorted(baseline_rows):
        baseline_row = baseline_rows[problem_id]
        repair_row = dict(repair_rows[problem_id])
        use_repair = not _valid(baseline_row) and _valid(repair_row)
        selected_row = repair_row if use_repair else baseline_row

        relative_code = Path(str(repair_row.get("path") or baseline_row.get("path") or ""))
        target_code = repair_dir / "code" / relative_code
        source_code_text = str(selected_row.get("code_file") or "")
        source_code = Path(source_code_text)
        if not use_repair and source_code.is_file():
            target_code.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_code, target_code)

        target_spec = repair_specs / relative_code.with_suffix(".json")
        target_log = repair_dir / "reports" / relative_code.with_suffix(".nagini.log")
        selected_verification = dict(selected_row.get("verification") or {})
        if selected_verification:
            selected_verification["details_file"] = _copy_log(selected_row, target_log)
            selected_verification["monotonic_selection"] = (
                "accepted_verified_repair" if use_repair else "retained_frozen_baseline"
            )

        historical_verification = repair_row.get("verification")
        repair_row["spec_file"] = str(target_spec) if target_spec.is_file() else ""
        repair_row["code_file"] = str(target_code) if target_code.is_file() else ""
        repair_row["status"] = selected_row.get("status", repair_row.get("status"))
        repair_row["verification"] = selected_verification
        repair_row["monotonic_reconciliation"] = {
            "baseline_output_dir": str(baseline_dir),
            "selection": (
                "accepted_verified_repair" if use_repair else "retained_frozen_baseline"
            ),
            "baseline_valid": _valid(baseline_row),
            "historical_repair_valid": _valid(repair_rows[problem_id]),
            "historical_repair_verification": historical_verification,
        }
        reconciled_rows.append(repair_row)
        if use_repair:
            accepted_repairs.append(problem_id)
        else:
            retained_baseline.append(problem_id)

    repair_report["results"] = reconciled_rows
    repair_report["processed"] = len(reconciled_rows)
    repair_report["verified"] = sum(1 for row in reconciled_rows if row.get("verification"))
    repair_report["passed"] = sum(1 for row in reconciled_rows if _valid(row))
    repair_report["monotonic_reconciliation"] = {
        "baseline_output_dir": str(baseline_dir),
        "accepted_repair_problem_ids": accepted_repairs,
        "retained_baseline_problem_ids": retained_baseline,
        "policy": "accept repair iff baseline invalid and repair valid",
    }
    results_file = repair_dir / "reports" / "results.json"
    results_file.write_text(json.dumps(repair_report, ensure_ascii=False, indent=2) + "\n")
    print(
        f"[INFO] repair_output={repair_dir} passed={repair_report['passed']} "
        f"accepted_repairs={accepted_repairs}"
    )


if __name__ == "__main__":
    main()
