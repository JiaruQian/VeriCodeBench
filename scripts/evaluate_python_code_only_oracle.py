import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from autospec.pipeline.python_code_only_pipeline import contract_hash, extract_reference_contract, load_python_code_only_contracts, normalize_contract

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--oracle-file",type=Path,default=Path("benchmarks/python-nagini-problems/requirements/requirements_100_code_only_contracts.json")); p.add_argument("--specs-dir",type=Path,required=True); p.add_argument("--code-dir",type=Path); p.add_argument("--report-file",type=Path,required=True); a=p.parse_args(); items=load_python_code_only_contracts(a.oracle_file); results=[]
    for x in items:
        sf=a.specs_dir/Path(x.path).with_suffix(".json"); r={"id":x.id,"path":x.path,"status":"ok","signature_match":False,"contract_match":False,"oracle_contract_hash":contract_hash(x.code_only_contract)}
        if not sf.exists(): r.update(status="missing_spec",error="spec artifact not found")
        else:
            obj=json.loads(sf.read_text()); actual=str(obj.get("code_only_contract") or obj.get("nagini_contract") or ""); r["signature_match"]=normalize_contract(str(obj.get("function_signature","")))==normalize_contract(x.function_signature); r["contract_match"]=normalize_contract(actual)==normalize_contract(x.code_only_contract); r["artifact_contract_hash"]=contract_hash(actual)
            if not r["signature_match"] or not r["contract_match"]: r.update(status="mismatch",error="canonical oracle changed")
        if a.code_dir is not None and r["status"]=="ok":
            cf=a.code_dir/x.path
            if not cf.exists(): r.update(status="missing_code",error="code artifact not found")
            else:
                try: actual,_=extract_reference_contract(cf.read_text(),x.function_signature); r["source_contract_match"]=normalize_contract(actual)==normalize_contract(x.code_only_contract)
                except Exception as e: r["source_contract_match"]=False; r["source_contract_error"]=str(e)
                if not r["source_contract_match"]: r.update(status="mismatch",error="source contract mismatch")
        results.append(r); print(f"[TASK] id={x.id} status={r['status']} path={x.path}")
    matched=sum(x["status"]=="ok" for x in results); report={"method":"frozen_python_nagini_oracle_contract_consistency","oracle_file":str(a.oracle_file),"specs_dir":str(a.specs_dir),"code_dir":str(a.code_dir) if a.code_dir else None,"total":len(results),"matched":matched,"coverage":matched/len(results) if results else 0.0,"results":results}; a.report_file.parent.mkdir(parents=True,exist_ok=True); a.report_file.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n"); print(f"[DONE] oracle_contract_coverage={report['coverage']:.3f} report={a.report_file}"); raise SystemExit(0 if matched==len(results) else 1)
if __name__ == "__main__": main()
