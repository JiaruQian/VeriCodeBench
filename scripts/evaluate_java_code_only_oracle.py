#!/usr/bin/env python3
"""Validate frozen Java/JML code-only oracle contracts."""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path

def norm(s: str) -> str: return " ".join(s.strip().split())
def digest(s: str) -> str: return hashlib.sha256(norm(s).encode()).hexdigest()

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--oracle-file",type=Path,default=Path("benchmarks/java-problems/requirements/requirements_100_code_only_contracts.json")); p.add_argument("--specs-dir",type=Path,required=True); p.add_argument("--code-dir",type=Path,default=None); p.add_argument("--report-file",type=Path,required=True); p.add_argument("--task-id",type=int,default=None); a=p.parse_args()
    rows=json.loads(a.oracle_file.read_text()); rows=[r for r in rows if a.task_id is None or int(r["id"])==a.task_id]; results=[]
    for r in rows:
        sf=a.specs_dir/Path(r["path"]).with_suffix(".json"); expected=norm(r["code_only_contract"]); x={"id":int(r["id"]),"path":r["path"],"status":"ok","signature_match":False,"contract_match":False,"oracle_contract_hash":digest(expected)}
        if not sf.exists(): x.update(status="missing_spec",error="spec artifact not found")
        else:
            obj=json.loads(sf.read_text()); actual=norm(str(obj.get("code_only_contract") or obj.get("jml_block") or "")); x["signature_match"]=norm(str(obj.get("function_signature","")))==norm(r["function_signature"]); x["contract_match"]=actual==expected; x["artifact_contract_hash"]=digest(actual)
            if not x["signature_match"] or not x["contract_match"]: x.update(status="mismatch",error="canonical oracle signature/contract changed")
        results.append(x); print(f"[TASK] id={x['id']} status={x['status']} path={x['path']}")
    matched=sum(x["status"]=="ok" and x["signature_match"] and x["contract_match"] for x in results); report={"method":"frozen_java_oracle_contract_consistency","oracle_file":str(a.oracle_file),"specs_dir":str(a.specs_dir),"total":len(results),"matched":matched,"coverage":matched/len(results) if results else 0.0,"results":results}; a.report_file.parent.mkdir(parents=True,exist_ok=True); a.report_file.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n"); print(f"[DONE] oracle_contract_coverage={report['coverage']:.3f} report={a.report_file}"); raise SystemExit(0 if matched==len(results) else 1)
if __name__=="__main__": main()
