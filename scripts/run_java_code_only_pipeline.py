#!/usr/bin/env python3
from __future__ import annotations
import argparse, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from autospec.llm.openai_compatible import ChatConfig, OpenAICompatibleClient
from autospec.pipeline.java_code_only_pipeline import load_java_code_only_contracts
from autospec.pipeline.java_code_only_contract_pipeline import JavaCodeOnlyContractPipeline, as_java_requirement_items

p=argparse.ArgumentParser(description="Generate and verify Java code under frozen JML oracle contracts.")
p.add_argument("--contracts-file",type=Path,default=Path("benchmarks/java-problems/requirements/requirements_100_code_only_contracts.json")); p.add_argument("--output-dir",type=Path,default=Path("outputs/java-code-only")); p.add_argument("--endpoint",default="https://openrouter.ai/api/v1/chat/completions"); p.add_argument("--model",default="deepseek/deepseek-v3.2"); p.add_argument("--api-key",default=None); p.add_argument("--api-key-env",default="OPENROUTER_API_KEY"); p.add_argument("--temperature",type=float,default=.1); p.add_argument("--max-tokens",type=int,default=4096); p.add_argument("--request-timeout",type=int,default=120); p.add_argument("--llm-retries",type=int,default=3); p.add_argument("--llm-retry-delay",type=int,default=15); p.add_argument("--verify-timeout",type=int,default=120); p.add_argument("--openjml-bin",default=os.getenv("OPENJML_BIN","openjml")); p.add_argument("--openjml-solver",default=os.getenv("OPENJML_SOLVER") or None); p.add_argument("--skip-verify",action="store_true"); p.add_argument("--enable-code-repair",action="store_true"); p.add_argument("--code-repair-max-iter",type=int,default=3); p.add_argument("--code-repair-strategy",choices=["simple","wybecoder"],default="simple"); p.add_argument("--wybecoder-candidates",type=int,default=3); p.add_argument("--reuse-artifacts-from",type=Path); p.add_argument("--task-id",type=int); p.add_argument("--resume",action="store_true")
a=p.parse_args(); key=a.api_key or os.getenv(a.api_key_env) or os.getenv("OPENAI_API_KEY")
if "openrouter.ai" in a.endpoint and not key: raise SystemExit(f"Missing API key. Set {a.api_key_env} or pass --api-key.")
items=load_java_code_only_contracts(a.contracts_file); items=[x for x in items if a.task_id is None or x.id==a.task_id]
if not items: raise SystemExit("no matching contract")
client=OpenAICompatibleClient(ChatConfig(model=a.model,endpoint=a.endpoint,temperature=a.temperature,max_tokens=a.max_tokens,api_key=key,timeout_seconds=a.request_timeout,retry_on_connection_error=a.llm_retries,retry_delay_seconds=a.llm_retry_delay))
pipe=JavaCodeOnlyContractPipeline(contracts=items,llm_client=client,output_dir=a.output_dir,verify_timeout=a.verify_timeout,skip_verify=a.skip_verify,openjml_bin=a.openjml_bin,openjml_solver=a.openjml_solver,enable_code_repair=a.enable_code_repair,code_repair_max_iter=a.code_repair_max_iter,code_repair_strategy=a.code_repair_strategy,wybecoder_candidates=a.wybecoder_candidates,reuse_artifacts_from=a.reuse_artifacts_from,logger=lambda m: print(m,flush=True))
out=pipe.run(as_java_requirement_items(items),resume=a.resume); print(f"[DONE] report={out['report_path']}")
