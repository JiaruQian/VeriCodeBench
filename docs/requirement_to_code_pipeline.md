# Requirement -> Spec -> Code -> Verify 管线说明（含增量增强）

本文档说明基于 AutoSpec 重构后的新流程，并给出可直接用于 ablation 的变体：

- `base`：最小可运行基线（单轮）
- `enhanced`：在 `base` 上增加轻量增强模块；其中 `constraint_extraction` 与 `code_repair` 可独立开关

目标是保持实验可复现、对比清晰，而不是一次性推翻原有管线。

## 1. 任务定义

我们定义端到端任务为：

`Requirement -> Spec -> Code -> Verify`

输入：

- 自然语言需求 `r`

输出：

- 形式化规格 `s`（ACSL）
- 程序 `c`（C）

优化目标是双目标：

1. `c |= s`（形式化验证通过）
2. `s ~= r`（规格与需求语义对齐）

> 核心点：不仅追求 verify pass，也要提升 requirement-spec 的覆盖与对齐质量。

## 2. Base Pipeline（Ablation-0）

当前基线流程：

`r --(LLM)--> s --(LLM)--> c --(Frama-C/WP)--> verify`

特征：

- 无结构化约束抽取
- 无 requirement-spec 对齐检查
- 无 verify 失败后的代码修复循环

这条线保留不动，作为稳定对照组。

## 3. Enhanced Pipeline（增量增强，不替换 base）

增强版在 base 之上增加可选轻量模块。默认 `enhanced` 为全开，以保持与旧命令兼容；做 ablation 时可分别关闭。

### 3.1 Requirement -> Constraint Extraction

先把需求拆成结构化约束：

`r -> {preconditions, postconditions, invariants}`

并可给出一个 `function_signature` 候选。输出为 JSON，便于后续评估和复用。

开关：

- CLI：`--enable-constraint-extraction` / `--disable-constraint-extraction`
- OpenRouter wrapper：`ENABLE_CONSTRAINT_EXTRACTION=true|false`

关闭后，spec 生成退回 base 的直接 `requirement -> ACSL` prompt，不再运行 `Constraint -> ACSL Mapping` 与 `Spec Self-Check + Refine`。

### 3.2 Constraint -> ACSL Mapping

将结构化约束映射为 ACSL（`requires/assigns/ensures`）。

相比“直接从 requirement 一步出 ACSL”，这种两阶段方式更稳健：

- 降低 hallucination
- 提高约束覆盖率
- 便于后续做缺失约束分析

输出 JSON 中允许包含 `code_annotation_hints`：

```json
{
  "function_signature": "int f(int *a, int n);",
  "acsl_block": "/*@ requires ...; assigns ...; ensures ...; */",
  "code_annotation_hints": {
    "loop_invariants": ["0 <= i <= n"],
    "loop_assigns": ["i, sum"],
    "loop_variants": ["n - i"]
  },
  "notes": "..."
}
```

`acsl_block` 必须只包含函数合同。`loop invariant`、`loop assigns`、`loop variant`
属于函数体内的 statement annotation，不能写进函数合同。若模型误把这些 loop annotation
写入 `acsl_block`，pipeline 会把它们移入 `code_annotation_hints` 并从合同中删除。

### 3.3 Spec Self-Check + Refine（1~2 轮）

加入轻量对齐检查：

- 输入：`requirement + constraints + spec`
- 输出：`is_aligned / missing_constraints / inconsistent_items / refinement_hints`

若发现缺失或不一致，则自动 refinement（轮数可配）。

形成：

`generate -> check -> refine`

### 3.4 Code Generation with Annotation Hints

代码生成阶段输入：

- `requirement`
- `function_signature`
- 函数合同 `acsl_block`
- `code_annotation_hints`

生成的 C 文件必须把 `acsl_block` 保持在函数定义正上方。若使用 loop hints，
只能把它们作为循环前的 statement annotation 插入函数体，例如：

```c
/*@
  loop invariant 0 <= i <= n;
  loop assigns i, sum;
  loop variant n - i;
*/
while (i < n) {
  ...
}
```

这样保留 `req -> spec -> code` 的结构：spec 阶段可以提出验证所需的循环注解候选，
但这些候选不参与 requirement-spec 主覆盖评估，也不会污染函数合同。

Java/JML/OpenJML 后端额外维护一个 contract-preservation 不变量：

- `specs/*.json` 中的 `jml_block` 是 canonical method contract。
- 代码生成后，pipeline 会按 `function_signature` 找到目标方法，并把 canonical `jml_block`
  程序化地插入或替换到方法定义正上方。
- OpenJML 验证的 Java 源码必须使用这个 canonical contract，不能使用模型在源码中改写出的
  更弱或不同 JML contract。
- 该后处理信息记录在 `reports/results.json` 的 `contract_enforcement` 字段中。

### 3.5 Verification-guided Code Repair（3~5 轮）

`spec -> c0 -> verify`

若验证失败，则把错误信息回灌给 LLM 修复代码：

`c0 -> verify -> c1 -> verify -> ...`

默认设置最大迭代次数，避免无限循环。

开关：

- CLI：`--enable-code-repair` / `--disable-code-repair`
- CLI strategy：`--code-repair-strategy simple|wybecoder`
- OpenRouter wrapper：`ENABLE_CODE_REPAIR=true|false`
- OpenRouter strategy：`CODE_REPAIR_STRATEGY=simple|wybecoder`

关闭后只执行首轮 Frama-C/WP verify，不进入修复循环。也可用 `--code-repair-max-iter 0` 达到等价效果。

当前默认 repair strategy 是 `simple`，也就是把 verifier 失败信息直接回灌给 LLM 生成下一版代码。
实验性 `wybecoder` strategy 借鉴 WybeCoder 的 prove-as-you-generate 思路：先把 Frama-C/WP
失败日志总结为结构化 failure/subgoal plan，再生成多个不同 focus 的修复候选并逐个验证。
它仍然只允许修改代码体和 statement-level annotations，不允许削弱或替换生成的函数合同。
详细迁移方案见 `docs/wybecoder_repair_migration_plan.md`。

Java/JML/OpenJML 的 repair 阶段同样强制保留 canonical `jml_block`。模型可以修改 Java
方法体、helper code 和 loop annotations，但 repair 输出写入文件前会再次用 `specs/*.json`
中的 method contract 覆盖源码中的 JML contract。因此 `code_validity_rate` 表示“代码在生成
spec 下通过 OpenJML”，而不是“代码在 repair 后可能被削弱的源码 contract 下通过 OpenJML”。

Rust/Verus 后端额外做 Rust-only canonicalization：

- 生成的 Rust function signature 若缺少结尾分号，pipeline 会自动补齐。
- 若返回值是未命名形式（例如 `-> u64;`），pipeline 会改写为 Verus 友好的命名返回
  `-> (r: u64);`，并把 generated clauses 中的 `result` 规范化为 `r`。
- pipeline 会过滤当前 Rust/Verus 题集不支持的 C/Viper 风格 spec 片段，例如 `null`、
  `pointer_valid`、`valid`、`wf`、`well_formed`、`fully_owned`、`independent_of`、
  `allocated` 和 `panics`。
- 若 self-check/refine 没有在配置轮数内得到 aligned spec，pipeline 不再盲目使用最后一次
  refinement，而是回退到 refinement 前的 spec；回退信息记录在 `alignment_check` 中。

Python/Nagini 后端额外维护一个 contract-preservation 不变量：

- `specs/*.json` 中的 `nagini_contract` 与结构化 `nagini_clauses` 是 canonical function contract。
- 代码生成后，pipeline 会按 `function_signature` 找到目标函数，并把 canonical
  `Requires(...)`/`Ensures(...)` 语句插入或替换为函数体最前面的语句。
- Nagini 验证的 Python 源码必须使用这个 canonical contract，不能使用模型在源码中改写出的
  更弱或不同 Nagini contract。
- repair 阶段可以修改函数体和 loop `Invariant(...)`，但写回文件前会再次强制恢复 canonical
  function contract。该后处理信息记录在 `reports/results.json` 的
  `contract_enforcement` 字段中。

### 3.6 Requirement-Spec Evaluation

为避免“`spec` 与 `code` 能互相验证，但二者共同偏离 `requirement`”的问题，
当前主评估使用 **Constraint Entailment Framework (CEF)**，见
`docs/constraint_entailment_benchmark.md`。

CEF 使用统一的 manual ground-truth spec 文件与 ACSL 子句抽取，按子句类型检查蕴含方向：

- `requires`：检查 manual ground-truth `requires` 是否蕴含生成的 `requires`
- `ensures/assigns`：检查生成的 `ensures/assigns` 是否蕴含 manual ground-truth 子句

Java/JML 评估使用同一套 entailment 框架，但 clause 抽取支持 `assignable`、`signals`、
`signals_only`，并将缺失 spec 的题目按 `0/n` 计入 ground-truth coverage 分母。Java summary
还会检查源码中的 JML clauses 是否与 `specs/*.json` 中的 canonical `jml_block` 一致；不一致时
该题的 code validity 视为失败，并在 `contract_mismatch_count` 中统计。

Rust/Verus 评估同样使用同一套 entailment 框架，但 Rust 签名使用 Rust-only parser，
避免把返回类型误识别为参数；并将 `r`、`result` 和 named return 统一 canonicalize 为同一
返回值别名，以减少纯命名差异造成的 coverage 误判。

Python/Nagini 评估同样使用同一套 entailment 框架。Python spec artifact 优先读取结构化
`nagini_clauses`；如果缺失，则回退解析 `nagini_contract` 中的 `Requires(...)` 与
`Ensures(...)`。Python 签名使用 Python-only parser，避免把类型标注如 `x: int` 的 `int`
误识别为参数名；`Result()`/`result` 会统一 canonicalize 为同一返回值别名。缺失 spec 的题目
按 `0/n` 计入 Python ground-truth coverage 分母。

主 ground truth 文件：

- `benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json`

输出文件：

- `reports/constraint_entailment.json`
- `reports/benchmark_summary.json`

`benchmark_summary.json` 汇总三个主指标：

- code valid count / validity rate
- requirement coverage micro/macro
- joint success：code valid 且 requirement coverage full

旧的 LLM-as-a-judge spec evaluation 仍可作为辅助调试入口，但不作为当前 benchmark 的主指标。

## 4. 实现位置

- `autospec/pipeline/requirement_pipeline.py`
  - `RequirementToCodePipeline`：base（保持原逻辑）
  - `EnhancedRequirementToCodePipeline`：enhanced（新增）
- `autospec/pipeline/java_requirement_pipeline.py`
  - Java/JML/OpenJML 后端
- `autospec/pipeline/rust_requirement_pipeline.py`
  - Rust/Verus 后端
- `autospec/pipeline/python_nagini_requirement_pipeline.py`
  - Python/Nagini 后端
- `autospec/verifier/openjml.py`
  - OpenJML verifier adapter
- `autospec/verifier/verus.py`
  - Verus verifier adapter
- `autospec/verifier/nagini.py`
  - Nagini verifier adapter
- `scripts/run_requirement_pipeline.py`
  - 增加 `--pipeline-variant` 与增强参数
- `scripts/run_openrouter_requirement_pipeline.sh`
  - 增加环境变量控制 enhanced 参数
- `scripts/run_python_nagini_requirement_pipeline.py`
  - Python/Nagini LLM generation CLI
- `autospec/pipeline/python_code_only_pipeline.py`
  - Python/Nagini frozen oracle-contract code-only pipeline
- `scripts/run_python_code_only_pipeline.py`
  - Python/Nagini code-only generation and repair CLI
- `scripts/run_openrouter_python_code_only_pipeline.sh`
  - Python/Nagini code-only OpenRouter wrapper
- `scripts/evaluate_python_code_only_oracle.py`
  - Python/Nagini oracle contract consistency checker
- `scripts/run_openrouter_python_nagini_requirement_pipeline.sh`
  - Python/Nagini OpenRouter wrapper
- `scripts/run_python_nagini_constraint_entailment_evaluation.sh`
  - Python/Nagini requirement coverage evaluator wrapper
- `scripts/evaluate_constraint_entailment.py`
  - 对已有 `specs/*.json` 做 manual ground-truth spec 覆盖评估
- `scripts/summarize_req2code_benchmark.py`
  - 汇总代码验证、requirement coverage 与 joint success

## 5. 数据格式

需求数据（数组）示例：

```json
[
  {
    "id": 1,
    "path": "pointers/swap.c",
    "requirement_en": "Given pointers to two integers, swap their stored values in place."
  }
]
```

文本字段读取优先级：

1. `requirement_zh`
2. `requirement_en`
3. `requirement`

## 6. 输出目录

当 `--output-dir outputs/req2code` 时：

- `outputs/req2code/specs/<relative_path>.json`
- `outputs/req2code/code/<relative_path>.c`
- `outputs/req2code/reports/results.partial.json`
- `outputs/req2code/reports/results.json`
- `outputs/req2code/reports/<relative_path>.verify.log`

Enhanced 额外信息会写入 `specs/*.json` 与 `results.json`，包括：

- `enhanced_modules`
- `constraints`
- `alignment_check`
- `code_annotation_hints`
- `moved_loop_annotations`
- `spec_evaluation`（可选的旧 LLM judge 调试信息）
- `repair_attempts` / `repair_history`
- 中间失败日志（`*.repairN.verify.log`）

## 7. 运行方式

严格 ablation 使用 artifact chaining，而不是四组各自独立重跑：

```text
base
  -> base+repair        # 复用 base 的 specs/ 和 code/，只运行 verify/repair
base+ce
  -> base+ce+repair     # 复用 base+ce 的 specs/ 和 code/，只运行 verify/repair
```

这样 `base` 与 `base+repair` 的 requirement coverage 完全一致，
`base+ce` 与 `base+ce+repair` 的 requirement coverage 也完全一致。Code repair
只度量在同一份 generated spec 和初始 code 上，verification-guided repair 能带来多少
verification/joint-success 提升。

推荐所有直接调用 `scripts/run_*_requirement_pipeline.py` 的长任务都显式带上：

- `--request-timeout 120`：单次 LLM/API 生成请求的超时上限，用于保证公平对比。
- `--llm-retries 3 --llm-retry-delay 15`：只对连接中断、`IncompleteRead`、429/5xx 等
  transient 失败做有界重试。
- `--resume`：从已有 `reports/results.partial.json` 或 `reports/results.json` 跳过已完成的
  `status=ok` 任务，失败或半成品任务会重新生成。
- `--signature-file ..._ground_truth_specs.json`：读取固定 `function_signature`；Java
  还读取不含目标 method contract 的 `type_context`（helper 类型的字段与 invariant），
  不把 `ground_truth_contract` 或 `ground_truth_clauses` 发给模型。缺少这个接口上下文时，
  独立生成的模型可能把 `Range.low/high` 改成 `min/max`，或把公开字段改成 getter，造成
  与 requirement 无关的表示漂移。

### 7.1 运行 base（推荐先跑这个做对照）

```bash
PYTHONPATH=. python3 scripts/run_requirement_pipeline.py \
  --requirements-file benchmarks/frama-c-problems/requirements/requirements_100.json \
  --signature-file benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/C-base-dsv41-time-5-0915 \
  --endpoint https://openrouter.ai/api/v1/chat/completions \
  --model deepseek/deepseek-v4.1-flash \
  --api-key-env OPENROUTER_API_KEY \
  --pipeline-variant base \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --temperature 0
```

Java/JML/OpenJML 对应的基础运行方式：

```bash
PYTHONPATH=. python3 scripts/run_java_requirement_pipeline.py \
  --requirements-file benchmarks/java-problems/requirements/requirements_100.json \
  --signature-file benchmarks/java-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/java-base-kimi-0701 \
  --endpoint https://openrouter.ai/api/v1/chat/completions \
  --model moonshotai/kimi-k2.7-code \
  --api-key-env OPENROUTER_API_KEY \
  --openjml-solver /usr/bin/z3 \
  --disable-constraint-extraction \
  --disable-code-repair \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --max-tokens 4096 \
  --temperature 0
```

Rust/Verus 对应的基础运行方式：

```bash
PYTHONPATH=. python3 scripts/run_rust_requirement_pipeline.py \
  --requirements-file benchmarks/rust-verus-problems/requirements/requirements_100.json \
  --signature-file benchmarks/rust-verus-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/rust-base-rust-0707 \
  --endpoint https://openrouter.ai/api/v1/chat/completions \
  --model anthropic/claude-sonnet-5 \
  --api-key-env OPENROUTER_API_KEY \
  --verus-bin verus \
  --pipeline-variant base \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --temperature 0 \
  --max-tokens 4096
```

Python/Nagini 对应的基础运行方式：

```bash
PYTHONPATH=. python3 scripts/run_python_nagini_requirement_pipeline.py \
  --requirements-file benchmarks/python-nagini-problems/requirements/requirements_100.json \
  --signature-file benchmarks/python-nagini-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/python-base-kimi-0704 \
  --endpoint https://openrouter.ai/api/v1/chat/completions \
  --model moonshotai/kimi-k2.7-code \
  --api-key-env OPENROUTER_API_KEY \
  --nagini-bin nagini \
  --pipeline-variant base \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --max-tokens 4096 \
  --temperature 0
```

### 7.2 运行 base+ce（严格增量链的第二个生成阶段）

严格 ablation 中，`base+ce` 应只生成带 constraint extraction / spec self-check 的
spec/code，并关闭 repair。后续 `base+ce+repair` 或 `base+ce+wybecoder` 必须复用这里的
artifacts。

```bash
PYTHONPATH=. python3 scripts/run_requirement_pipeline.py \
  --requirements-file benchmarks/frama-c-problems/requirements/requirements_100.json \
  --signature-file benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/C-ce-dsv41-time-5-0916 \
  --endpoint https://openrouter.ai/api/v1/chat/completions \
  --model deepseek/deepseek-v4.1-flash  \
  --api-key-env OPENROUTER_API_KEY \
  --pipeline-variant enhanced \
  --enable-constraint-extraction \
  --spec-self-check-rounds 1 \
  --disable-code-repair \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --max-tokens 4096 \
  --temperature 0 \
  --resume
```

Java/JML/OpenJML 对应的 base+ce 运行方式：

```bash
PYTHONPATH=. python3 scripts/run_java_requirement_pipeline.py \
  --requirements-file benchmarks/java-problems/requirements/requirements_100.json \
  --signature-file benchmarks/java-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/java-ce-kimi-0701 \
  --endpoint https://openrouter.ai/api/v1/chat/completions \
  --model moonshotai/kimi-k2.7-code \
  --api-key-env OPENROUTER_API_KEY \
  --openjml-solver /usr/bin/z3 \
  --enable-constraint-extraction \
  --spec-self-check-rounds 1 \
  --disable-code-repair \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --max-tokens 4096 \
  --temperature 0
```

Rust/Verus 对应的 base+ce 运行方式：

```bash
PYTHONPATH=. python3 scripts/run_rust_requirement_pipeline.py \
  --requirements-file benchmarks/rust-verus-problems/requirements/requirements_100.json \
  --signature-file benchmarks/rust-verus-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/rust-ce-claude-0707 \
  --endpoint https://openrouter.ai/api/v1/chat/completions \
  --model anthropic/claude-sonnet-5 \
  --api-key-env OPENROUTER_API_KEY \
  --verus-bin verus \
  --pipeline-variant enhanced \
  --enhancement-method ce \
  --spec-self-check-rounds 1 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --temperature 0 \
  --max-tokens 4096
```

Python/Nagini 对应的 base+ce 运行方式：

```bash
PYTHONPATH=. python3 scripts/run_python_nagini_requirement_pipeline.py \
  --requirements-file benchmarks/python-nagini-problems/requirements/requirements_100.json \
  --signature-file benchmarks/python-nagini-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/python-ce-kimi-0704 \
  --endpoint https://openrouter.ai/api/v1/chat/completions \
  --model moonshotai/kimi-k2.7-code \
  --api-key-env OPENROUTER_API_KEY \
  --nagini-bin nagini \
  --pipeline-variant enhanced \
  --enhancement-method ce \
  --spec-self-check-rounds 1 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --max-tokens 4096 \
  --temperature 0
```

### 7.3 C/ACSL 严格增量 repair 与 WybeCoder repair

严格 repair ablation 不重新生成 spec/code，而是通过 `--reuse-artifacts-from` 复用已冻结
artifacts。

`base+repair`：复用 `base` 的 `specs/` 与 `code/`，只运行 verification + simple repair。

```bash
PYTHONPATH=. python3 scripts/run_requirement_pipeline.py \
  --requirements-file benchmarks/frama-c-problems/requirements/requirements_100.json \
  --signature-file benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/req2code-base-repair-0520 \
  --pipeline-variant enhanced \
  --disable-constraint-extraction \
  --enable-code-repair \
  --model moonshotai/kimi-k2.7-code \
  --max-tokens 4096 \
  --code-repair-strategy simple \
  --code-repair-max-iter 3 \
  --reuse-artifacts-from outputs/req2code-base-0520 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume
```

`base+ce+repair`：复用 `base+ce` 的 `specs/` 与 `code/`，只运行 verification + simple repair。

```bash
PYTHONPATH=. python3 scripts/run_requirement_pipeline.py \
  --requirements-file benchmarks/frama-c-problems/requirements/requirements_100.json \
  --signature-file benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/req2code-ce-repair-0520 \
  --pipeline-variant enhanced \
  --disable-constraint-extraction \
  --enable-code-repair \
  --model moonshotai/kimi-k2.7-code \
  --max-tokens 4096 \
  --code-repair-strategy simple \
  --code-repair-max-iter 3 \
  --reuse-artifacts-from outputs/req2code-ce-only-0520 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume
```

`base+wybecoder`：复用 `base` 的 `specs/` 与 `code/`，只运行 verification +
WybeCoder-style repair。

```bash
PYTHONPATH=. python3 scripts/run_requirement_pipeline.py \
  --requirements-file benchmarks/frama-c-problems/requirements/requirements_100.json \
  --signature-file benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/C-wybecoder-dsv41-time-5-0916 \
  --pipeline-variant enhanced \
  --disable-constraint-extraction \
  --enable-code-repair \
  --model deepseek/deepseek-v4.1-flash \
  --max-tokens 4096 \
  --code-repair-strategy wybecoder \
  --wybecoder-candidates 3 \
  --code-repair-max-iter 3 \
  --reuse-artifacts-from outputs/C-base-dsv41-time-5-0915 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --max-tokens 4096 \
  --temperature 0 \
  --resume
```

`base+ce+wybecoder`：复用 `base+ce` 的 `specs/` 与 `code/`，只运行 verification +
WybeCoder-style repair。

```bash
PYTHONPATH=. python3 scripts/run_requirement_pipeline.py \
  --requirements-file benchmarks/frama-c-problems/requirements/requirements_100.json \
  --signature-file benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/C-ce-wybecoder-dsv41-time-5-0916 \
  --pipeline-variant enhanced \
  --disable-constraint-extraction \
  --enable-code-repair \
  --model deepseek/deepseek-v4.1-flash \
  --max-tokens 4096 \
  --code-repair-strategy wybecoder \
  --wybecoder-candidates 3 \
  --code-repair-max-iter 3 \
  --reuse-artifacts-from outputs/C-ce-dsv41-time-5-0916 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --max-tokens 4096 \
  --temperature 0 \
  --resume
```

`--reuse-artifacts-from` 会把来源目录的 `specs/` 与 `code/` 复制到当前输出目录，然后
跳过 spec/code 生成，只运行 verification 和可选 repair。用于 `base+repair` /
`base+wybecoder` 时来源应为 base 输出目录；用于 `base+ce+repair` /
`base+ce+wybecoder` 时来源应为 base+ce 输出目录。

### 7.4 Java/JML/OpenJML 严格增量 repair ablation

Java/JML/OpenJML 后端现在已经适配与 C/ACSL 相同的严格增量运行规则：
repair 变体必须通过 `--reuse-artifacts-from` 或 `REUSE_ARTIFACTS_FROM` 复用 frozen
`specs/` 与 `code/`，跳过 spec/code 重新生成，只运行 OpenJML verification 和可选 repair。
因此 Java 的四种主范式可以按下面方式组织：

- `base`：关闭 constraint extraction 与 code repair。
- `base+ce`：开启 constraint extraction/self-check，关闭 code repair。
- `base+wybecoder`：复用 frozen `base` 输出，只运行 WybeCoder-style repair。
- `base+ce+wybecoder`：复用 frozen `base+ce` 输出，只运行 WybeCoder-style repair。

Java `base+repair`（simple repair，复用 `base` 输出）：

```bash
PYTHONPATH=. python3 scripts/run_java_requirement_pipeline.py \
  --requirements-file benchmarks/java-problems/requirements/requirements_100.json \
  --signature-file benchmarks/java-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/java-base-repair-0624 \
  --reuse-artifacts-from outputs/java-base-0624 \
  --openjml-solver /usr/bin/z3 \
  --disable-constraint-extraction \
  --enable-code-repair \
  --code-repair-strategy simple \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --temperature 0
```

Java `base+wybecoder`（复用 `base` 输出）：

```bash
PYTHONPATH=. python3 scripts/run_java_requirement_pipeline.py \
  --requirements-file benchmarks/java-problems/requirements/requirements_100.json \
  --signature-file benchmarks/java-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/java-wybecoder-kimi-0702 \
  --reuse-artifacts-from outputs/java-base-kimi-0701 \
  --openjml-solver /usr/bin/z3 \
  --disable-constraint-extraction \
  --model moonshotai/kimi-k2.7-code \
  --max-tokens 4096 \
  --enable-code-repair \
  --code-repair-strategy wybecoder \
  --wybecoder-candidates 3 \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --temperature 0
```

Java `base+ce`（生成 frozen CE artifacts，不 repair）：

```bash
PYTHONPATH=. python3 scripts/run_java_requirement_pipeline.py \
  --requirements-file benchmarks/java-problems/requirements/requirements_100.json \
  --signature-file benchmarks/java-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/java-ce-only-0624 \
  --openjml-solver /usr/bin/z3 \
  --enable-constraint-extraction \
  --model moonshotai/kimi-k2.7-code \
  --max-tokens 4096 \
  --spec-self-check-rounds 1 \
  --disable-code-repair \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --temperature 0
```

Java `base+ce+wybecoder`（复用 `base+ce` 输出）：

```bash
PYTHONPATH=. python3 scripts/run_java_requirement_pipeline.py \
  --requirements-file benchmarks/java-problems/requirements/requirements_100.json \
  --signature-file benchmarks/java-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/java-ce-wybecoder-kimi-0702 \
  --reuse-artifacts-from outputs/java-ce-kimi-0701 \
  --openjml-solver /usr/bin/z3 \
  --model moonshotai/kimi-k2.7-code \
  --max-tokens 4096 \
  --disable-constraint-extraction \
  --enable-code-repair \
  --code-repair-strategy wybecoder \
  --wybecoder-candidates 3 \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --temperature 0
```

`--reuse-artifacts-from` 会把来源目录的 `specs/` 与 `code/` 复制到当前 Java 输出目录，
并在写回源码前强制恢复 `specs/*.json` 中的 canonical `jml_block`。repair 可以修改方法体、
helper code 和 loop annotations，但不能削弱或替换 generated JML method contract。

Rust/Verus 现在也支持与 C/Java 相同的 artifact chaining。严格 `base+repair`、
`base+wybecoder`、`base+ce+repair`、`base+ce+wybecoder` 应设置
`--reuse-artifacts-from`，只复用 frozen `specs/` 与 `code/` 并运行 verification + repair。

Rust/Verus `base+wybecoder`（复用 `base` 输出）：

```bash
PYTHONPATH=. python3 scripts/run_rust_requirement_pipeline.py \
  --requirements-file benchmarks/rust-verus-problems/requirements/requirements_100.json \
  --signature-file benchmarks/rust-verus-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/rust-wybecoder-claude-0709 \
  --reuse-artifacts-from outputs/rust-base-rust-0707 \
  --verus-bin verus \
  --model anthropic/claude-sonnet-5 \
  --max-tokens 4096 \
  --pipeline-variant enhanced \
  --disable-constraint-extraction \
  --enable-code-repair \
  --code-repair-strategy wybecoder \
  --wybecoder-candidates 3 \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --max-tokens 4096 \
  --temperature 0
```

Rust/Verus `base+ce+wybecoder`（复用 `base+ce` 输出）：

```bash
PYTHONPATH=. python3 scripts/run_rust_requirement_pipeline.py \
  --requirements-file benchmarks/rust-verus-problems/requirements/requirements_100.json \
  --signature-file benchmarks/rust-verus-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/rust-ce-wybecoder-claude-0709 \
  --reuse-artifacts-from outputs/rust-ce-claude-0707 \
  --verus-bin verus \
  --model anthropic/claude-sonnet-5 \
  --max-tokens 4096 \
  --pipeline-variant enhanced \
  --disable-constraint-extraction \
  --enable-code-repair \
  --code-repair-strategy wybecoder \
  --wybecoder-candidates 3 \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --max-tokens 4096 \
  --temperature 0
```

Rust/Verus 的 Verus contract 不像 Java/JML 那样需要回写独立 comment block；复用时 pipeline
会复制 frozen `specs/*.json` 和 `code/*.rs`，并使用 spec artifact 中的 `verus_clauses`
作为 repair prompt 的冻结合同。

Rust pipeline 会在首次生成和每个 repair candidate 上强制写回 canonical
`verus_clauses`，因此 repair 只能修改函数体、helper proof 与循环注解。汇总阶段还会比较
spec artifact 与实际验证源码中的 contract；发现 contract 漂移时，该题 code validity
直接计为失败。旧 Rust artifact 可通过 `scripts/migrate_rust_outputs_v2.py` 复制到
`*-offline-v2` 后进行 raw-clause 恢复、contract 锁定、Verus 重验和 coverage 重算。

Rust coverage evaluator 进一步对语义等价的 contract 形态做保守匹配：布尔与 typed enum
表面写法、等价整数边界、按相同 guard 拆开的多条 `ensures`、`if/else`，以及用“长度、
修改位置、未修改区间”表达的 `Seq.update`/`push`/`subrange`。序列规则只有在长度、点值和
frame 条件全部存在时才命中，不会把部分 frame 当作完整序列效果。

Python/Nagini 对应的非严格 code repair ablation：

```bash
PYTHONPATH=. python3 scripts/run_python_nagini_requirement_pipeline.py \
  --requirements-file benchmarks/python-nagini-problems/requirements/requirements_100.json \
  --signature-file benchmarks/python-nagini-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/python-nagini-req2code-repair-only-0610 \
  --nagini-bin nagini \
  --pipeline-variant enhanced \
  --enhancement-method repair \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --temperature 0
```

Python/Nagini 严格 `base+repair`（复用 `base` 输出，只运行 verification + simple repair）：

```bash
PYTHONPATH=. python3 scripts/run_python_nagini_requirement_pipeline.py \
  --requirements-file benchmarks/python-nagini-problems/requirements/requirements_100.json \
  --signature-file benchmarks/python-nagini-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/python-nagini-base-repair-0627 \
  --reuse-artifacts-from outputs/python-nagini-base-0627 \
  --nagini-bin nagini \
  --model moonshotai/kimi-k2.7-code \
  --max-tokens 4096 \
  --pipeline-variant enhanced \
  --disable-constraint-extraction \
  --enable-code-repair \
  --code-repair-strategy simple \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --temperature 0
```

Python/Nagini 严格 `base+wybecoder`（复用 `base` 输出，只运行 verification + WybeCoder-style repair）：

```bash
PYTHONPATH=. python3 scripts/run_python_nagini_requirement_pipeline.py \
  --requirements-file benchmarks/python-nagini-problems/requirements/requirements_100.json \
  --signature-file benchmarks/python-nagini-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/python-wybecoder-kimi-ds-0706 \
  --reuse-artifacts-from outputs/python-base-kimi-0704 \
  --model deepseek/deepseek-v3.2 \
  --nagini-bin nagini \
  --pipeline-variant enhanced \
  --disable-constraint-extraction \
  --enable-code-repair \
  --code-repair-strategy wybecoder \
  --wybecoder-candidates 3 \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --max-tokens 4096 \
  --temperature 0
```

Python/Nagini 严格 `base+ce+repair`（复用 `base+ce` 输出，只运行 verification + simple repair）：

```bash
PYTHONPATH=. python3 scripts/run_python_nagini_requirement_pipeline.py \
  --requirements-file benchmarks/python-nagini-problems/requirements/requirements_100.json \
  --signature-file benchmarks/python-nagini-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/python-nagini-ce-repair-0627 \
  --reuse-artifacts-from outputs/python-nagini-ce-0627 \
  --nagini-bin nagini \
  --model moonshotai/kimi-k2.7-code \
  --max-tokens 4096 \
  --pipeline-variant enhanced \
  --disable-constraint-extraction \
  --enable-code-repair \
  --code-repair-strategy simple \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --temperature 0
```

Python/Nagini 严格 `base+ce+wybecoder`（复用 `base+ce` 输出，只运行 verification + WybeCoder-style repair）：

```bash
PYTHONPATH=. python3 scripts/run_python_nagini_requirement_pipeline.py \
  --requirements-file benchmarks/python-nagini-problems/requirements/requirements_100.json \
  --signature-file benchmarks/python-nagini-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/python-ce-wybecoder-kimi-0706 \
  --reuse-artifacts-from outputs/python-ce-kimi-0704 \
  --model moonshotai/kimi-k2.7-code \
  --max-tokens 4096 \
  --nagini-bin nagini \
  --pipeline-variant enhanced \
  --disable-constraint-extraction \
  --enable-code-repair \
  --code-repair-strategy wybecoder \
  --wybecoder-candidates 3 \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume \
  --temperature 0
```

Python/Nagini 复用 frozen artifacts 时会复制 `specs/*.json` 和 `code/*.py`，并在验证或 repair 前
按 spec artifact 中的 canonical `nagini_contract` 重新强制写回函数体开头，确保 repair 不能削弱
或替换生成的函数合同。

### 7.5 只跑单个任务（调试 prompt 最常用）

```bash
PYTHONPATH=. python3 scripts/run_requirement_pipeline.py \
  --task-id 17 \
  --requirements-file benchmarks/frama-c-problems/requirements/requirements_100.json \
  --signature-file benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/req2code-debug \
  --pipeline-variant enhanced \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume
```

Java/JML/OpenJML 对应命令：

```bash
PYTHONPATH=. python3 scripts/run_java_requirement_pipeline.py \
  --task-id 17 \
  --requirements-file benchmarks/java-problems/requirements/requirements_100.json \
  --signature-file benchmarks/java-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/java-req2code-debug \
  --openjml-solver /usr/bin/z3 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume
```

Rust/Verus 对应命令：

```bash
PYTHONPATH=. python3 scripts/run_rust_requirement_pipeline.py \
  --task-id 17 \
  --requirements-file benchmarks/rust-verus-problems/requirements/requirements_100.json \
  --signature-file benchmarks/rust-verus-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/rust-req2code-debug \
  --pipeline-variant enhanced \
  --enhancement-method both \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume
```

Python/Nagini 对应命令：

```bash
PYTHONPATH=. python3 scripts/run_python_nagini_requirement_pipeline.py \
  --task-id 17 \
  --requirements-file benchmarks/python-nagini-problems/requirements/requirements_100.json \
  --signature-file benchmarks/python-nagini-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/python-nagini-req2code-debug \
  --pipeline-variant enhanced \
  --enhancement-method both \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --resume
```

### 7.6 C/ACSL code-only oracle-contract 评测

Code-only 任务固定人工构造并验证过的函数合同，只评估模型生成 C 实现与实现级证明注解的能力：

`Requirement + Signature + Oracle Contract -> Code + Proof Annotations -> Frama-C/WP`

它使用独立入口 `scripts/run_c_code_only_pipeline.py`，不会运行 spec generation、constraint
extraction 或 spec self-check。每次生成和 repair 后，pipeline 都会程序化恢复
`requirements_100_code_only_contracts.json` 中的 canonical ACSL contract；模型只能修改函数体、
loop annotations 和 statement annotations。

初始生成（不 repair）：

```bash
PYTHONPATH=. python3 scripts/run_c_code_only_pipeline.py \
  --contracts-file benchmarks/frama-c-problems/requirements/requirements_100_code_only_contracts.json \
  --output-dir outputs/c-code-only-base-claude-0826 \
  --model anthropic/claude-sonnet-5 \
  --api-key-env OPENROUTER_API_KEY \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --max-tokens 4096 \
  --temperature 0 \
  --resume
```

Simple repair 必须复用上面的初始 `specs/` 和 `code/`：

```bash
PYTHONPATH=. python3 scripts/run_c_code_only_pipeline.py \
  --contracts-file benchmarks/frama-c-problems/requirements/requirements_100_code_only_contracts.json \
  --output-dir outputs/c-code-only-simple-0825 \
  --reuse-artifacts-from outputs/c-code-only-base-0825 \
  --model anthropic/claude-sonnet-5 \
  --api-key-env OPENROUTER_API_KEY \
  --enable-code-repair \
  --code-repair-strategy simple \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --max-tokens 4096 \
  --temperature 0 \
  --resume
```

WybeCoder repair 同样复用完全相同的初始 artifacts：

```bash
PYTHONPATH=. python3 scripts/run_c_code_only_pipeline.py \
  --contracts-file benchmarks/frama-c-problems/requirements/requirements_100_code_only_contracts.json \
  --output-dir outputs/c-code-only-wybecoder-claude-0826 \
  --reuse-artifacts-from outputs/c-code-only-base-claude-0826 \
  --model anthropic/claude-sonnet-5 \
  --api-key-env OPENROUTER_API_KEY \
  --enable-code-repair \
  --code-repair-strategy wybecoder \
  --wybecoder-candidates 3 \
  --code-repair-max-iter 3 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --max-tokens 4096 \
  --temperature 0 \
  --resume
```

OpenRouter wrapper 等价命令：

```bash
OUTPUT_DIR=outputs/c-code-only-base-0825 \
MODEL=anthropic/claude-sonnet-5 \
ENABLE_CODE_REPAIR=false \
bash scripts/run_openrouter_c_code_only_pipeline.sh

OUTPUT_DIR=outputs/c-code-only-wybecoder-0825 \
REUSE_ARTIFACTS_FROM=outputs/c-code-only-base-0825 \
MODEL=anthropic/claude-sonnet-5 \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=wybecoder \
bash scripts/run_openrouter_c_code_only_pipeline.sh
```

Code-only 的 oracle consistency 必须单独评估，不能用 requirement entailment coverage 代替。
该检查直接比较 frozen oracle contract 与输出 `specs/` artifact；因此只要 pipeline 没有改写
contract，结果应为 100%，且不依赖 C/ACSL 到 Z3 的表达式解析：

```bash
OUTPUT_DIR=outputs/c-code-only-base-0825 \
bash scripts/run_code_only_oracle_evaluation.sh
```

该命令生成 `reports/oracle_contract_consistency.json`。原有
`run_constraint_entailment_evaluation.sh` 仍用于 requirement semantic coverage；它回答的是
oracle contract 是否覆盖人工 semantic targets，而不是 oracle contract 是否被正确保留。

### 7.6.1 Java/JML code-only oracle-contract 评测

Java code-only 任务沿用相同的严格增量语义：固定
`benchmarks/java-problems/requirements/requirements_100_code_only_contracts.json` 中的
方法级 JML 合同，只评估 Java 实现与实现级循环注解。入口为
`scripts/run_java_code_only_pipeline.py`，不会执行 spec generation、constraint extraction
或 spec self-check；每次生成和 repair 后都会恢复 canonical `jml_block`。

初始生成（不 repair）：

moonshotai/kimi-k2.7-code
qwen/qwen3.6-plus

```bash
PYTHONPATH=. python3 scripts/run_java_code_only_pipeline.py \
  --contracts-file benchmarks/java-problems/requirements/requirements_100_code_only_contracts.json \
  --output-dir outputs/java-code-only-base-claude-0827 \
  --model anthropic/claude-sonnet-5 \
  --api-key-env OPENROUTER_API_KEY \
  --openjml-solver /usr/bin/z3 \
  --verify-timeout 120 --request-timeout 120 \
  --llm-retries 3 --llm-retry-delay 15 \
  --max-tokens 4096 --temperature 0 --resume
```

Simple repair 和 WybeCoder repair 必须复用相同的初始 artifacts：

```bash
PYTHONPATH=. python3 scripts/run_java_code_only_pipeline.py \
  --contracts-file benchmarks/java-problems/requirements/requirements_100_code_only_contracts.json \
  --output-dir outputs/java-code-only-simple \
  --reuse-artifacts-from outputs/java-code-only-base \
  --model anthropic/claude-sonnet-5 --api-key-env OPENROUTER_API_KEY \
  --openjml-solver /usr/bin/z3 --enable-code-repair \
  --code-repair-strategy simple --code-repair-max-iter 3 --resume

PYTHONPATH=. python3 scripts/run_java_code_only_pipeline.py \
  --contracts-file benchmarks/java-problems/requirements/requirements_100_code_only_contracts.json \
  --output-dir outputs/java-code-only-wybecoder-claude-0827 \
  --reuse-artifacts-from outputs/java-code-only-base-claude-0827 \
  --model anthropic/claude-sonnet-5 --api-key-env OPENROUTER_API_KEY \
  --openjml-solver /usr/bin/z3 --enable-code-repair \
  --code-repair-strategy wybecoder --wybecoder-candidates 3 \
  --code-repair-max-iter 3 --max-tokens 4096 --temperature 0 --resume
```

Java oracle consistency 单独运行：

```bash
PYTHONPATH=. python3 scripts/evaluate_java_code_only_oracle.py \
  --oracle-file benchmarks/java-problems/requirements/requirements_100_code_only_contracts.json \
  --specs-dir outputs/java-code-only-base/specs \
  --report-file outputs/java-code-only-base/reports/java_oracle_contract_consistency.json
```

### 7.6.2 Rust/Verus code-only oracle-contract 评测

Rust code-only 数据位于
`benchmarks/rust-verus-problems/requirements/requirements_100_code_only_contracts.json`。
构造器按 dataset signature 定位 reference target function，只提取函数头中的
`requires/ensures`；函数体、loop invariants、`decreases`、assertions 和 proof code 不会进入
oracle input。100 道 reference contracts 与人工 semantic targets 精确一一对应，当前无需添加
auxiliary contract clauses，reference Verus 回归为 100/100 pass。

初始生成：

```bash
PYTHONPATH=. python3 scripts/run_rust_code_only_pipeline.py \
  --contracts-file benchmarks/rust-verus-problems/requirements/requirements_100_code_only_contracts.json \
  --output-dir outputs/rust-code-only-base-claude-0827 \
  --model anthropic/claude-sonnet-5 \
  --api-key-env OPENROUTER_API_KEY \
  --verus-bin verus --verify-timeout 120 \
  --request-timeout 120 --llm-retries 3 --llm-retry-delay 15 \
  --max-tokens 4096 --temperature 0 --resume
```

Repair 必须复用同一批 initial artifacts：

```bash
PYTHONPATH=. python3 scripts/run_rust_code_only_pipeline.py \
  --output-dir outputs/rust-code-only-simple \
  --reuse-artifacts-from outputs/rust-code-only-base \
  --model anthropic/claude-sonnet-5 --api-key-env OPENROUTER_API_KEY \
  --enable-code-repair --code-repair-strategy simple \
  --code-repair-max-iter 3 --resume

PYTHONPATH=. python3 scripts/run_rust_code_only_pipeline.py \
  --output-dir outputs/rust-code-only-wybecoder-claude-0828 \
  --reuse-artifacts-from outputs/rust-code-only-base-claude-0827 \
  --model anthropic/claude-sonnet-5 --api-key-env OPENROUTER_API_KEY \
  --enable-code-repair --code-repair-strategy wybecoder \
  --wybecoder-candidates 3 --code-repair-max-iter 3 --resume
```

Rust 合同嵌在函数头中，因此 enforcement 同时恢复 canonical named signature 与结构化
`verus_clauses`。一致性检查既比较 `specs/*.json`，也重新抽取 `code/*.rs` 中的目标函数头：

```bash
OUTPUT_DIR=outputs/rust-code-only-base \
bash scripts/run_rust_code_only_oracle_evaluation.sh
```

OpenRouter wrapper 为 `scripts/run_openrouter_rust_code_only_pipeline.sh`。它与 C/Java 保持相同
的 `ENABLE_CODE_REPAIR`、`CODE_REPAIR_STRATEGY`、`WYBECODER_CANDIDATES`、
`REUSE_ARTIFACTS_FROM`、`TASK_ID` 和 `RESUME` 语义。

在 C code-only 模式下，`run_constraint_entailment_evaluation.sh` 会读取
`task_type=code_only_oracle_contract` 并采用 oracle-specific 语义方向：允许为内存安全、溢出和
终止性加入辅助 `requires`，但要求 oracle contract 蕴含每个 audited semantic target。C/ACSL
解析器会正确处理量词绑定分号、行内注释、链式比较、`\result`、标签和指针解引用；不能把
parser failure 当成 coverage failure。

输出仍采用统一布局：`specs/` 保存 frozen oracle artifacts，`code/` 保存初始或 repaired C，
`reports/results.json` 保存 initial/post-repair validity、repair trajectory 与
`contract_enforcement`。Rust/Verus 已使用独立 code-only contract 数据与 pipeline；
Python/Nagini 已使用独立 code-only contract 数据与 pipeline，并保持相同 CLI 语义、artifact chaining 和指标字段。

### 7.6.3 Python/Nagini code-only oracle contract 运行方式：

该流程跳过模型规格生成，直接读取固定的
`benchmarks/python-nagini-problems/requirements/requirements_100_code_only_contracts.json`。
模型只生成实现及实现级 `Invariant`/`Assert`，oracle function contract 在生成和 repair 阶段均被冻结。

```bash
PYTHONPATH=. python3 scripts/run_python_code_only_pipeline.py \
  --contracts-file benchmarks/python-nagini-problems/requirements/requirements_100_code_only_contracts.json \
  --output-dir outputs/python-code-only-base-claude-0902 \
  --endpoint https://openrouter.ai/api/v1/chat/completions \
  --model anthropic/claude-sonnet-5 \
  --api-key-env OPENROUTER_API_KEY \
  --nagini-bin nagini \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --max-tokens 4096 \
  --temperature 0 \
  --resume
```

code-only 的 repair 变体必须复用同一批 initial code，不能重新采样：

```bash
PYTHONPATH=. python3 scripts/run_python_code_only_pipeline.py \
  --contracts-file benchmarks/python-nagini-problems/requirements/requirements_100_code_only_contracts.json \
  --output-dir outputs/python-code-only-wybecoder-kimi-0902 \
  --endpoint https://openrouter.ai/api/v1/chat/completions \
  --model moonshotai/kimi-k2.7-code \
  --api-key-env OPENROUTER_API_KEY \
  --nagini-bin nagini \
  --enable-code-repair \
  --code-repair-strategy wybecoder \
  --wybecoder-candidates 3 \
  --code-repair-max-iter 3 \
  --reuse-artifacts-from outputs/python-code-only-kimi-0902 \
  --verify-timeout 120 \
  --request-timeout 120 \
  --llm-retries 3 \
  --llm-retry-delay 15 \
  --max-tokens 4096 \
  --temperature 0 \
  --resume
```

也可以使用 OpenRouter wrapper：

```bash
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=wybecoder \
REUSE_ARTIFACTS_FROM=outputs/python-code-only-kimi-0902 \
OUTPUT_DIR=outputs/python-code-only-wybecoder-kimi-0902 \
scripts/run_openrouter_python_code_only_pipeline.sh
```

oracle artifact 一致性检查：

```bash
PYTHONPATH=. python3 scripts/evaluate_python_code_only_oracle.py \
  --oracle-file benchmarks/python-nagini-problems/requirements/requirements_100_code_only_contracts.json \
  --specs-dir outputs/python-code-only-kimi-0902/specs \
  --code-dir outputs/python-code-only-kimi-0902/code \
  --report-file outputs/python-code-only-kimi-0902/reports/oracle_contract_consistency.json
```

### 7.7 跳过验证（仅生成）

```bash
PYTHONPATH=. python3 scripts/run_requirement_pipeline.py --skip-verify
```

Java/JML 对应命令：

```bash
PYTHONPATH=. python3 scripts/run_java_requirement_pipeline.py --skip-verify
```

Rust/Verus 对应命令：

```bash
PYTHONPATH=. python3 scripts/run_rust_requirement_pipeline.py --skip-verify
```

Python/Nagini 对应命令：

```bash
PYTHONPATH=. python3 scripts/run_python_nagini_requirement_pipeline.py --skip-verify
```

## 8. OpenRouter 一键脚本

`scripts/run_openrouter_requirement_pipeline.sh` 支持以下变量：

- `PIPELINE_VARIANT=base|enhanced`
- `ENABLE_CONSTRAINT_EXTRACTION=true|false`（enhanced 生效，默认 true）
- `SPEC_SELF_CHECK_ROUNDS`（enhanced 生效）
- `ENABLE_CODE_REPAIR=true|false`（enhanced 生效，默认 true）
- `CODE_REPAIR_MAX_ITER`（enhanced 生效）
- `CODE_REPAIR_STRATEGY=simple|wybecoder`（C/ACSL、Java/JML、Rust/Verus 与 Python/Nagini enhanced 生效，默认 simple）
- `WYBECODER_CANDIDATES`（C/ACSL、Java/JML、Rust/Verus 与 Python/Nagini wybecoder repair 生效，默认 3）
- `REUSE_ARTIFACTS_FROM`（C/ACSL、Java/JML、Rust/Verus 与 Python/Nagini 严格 repair ablation 必须设置）
- `ENABLE_SPEC_EVALUATION=true|false`（enhanced 生效，默认 false）
- `SIGNATURE_FILE`（固定 function signature 来源；C 默认
  `benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json`）
- `REQUEST_TIMEOUT`（单次 LLM/API 请求超时，默认 120）
- `LLM_RETRIES`、`LLM_RETRY_DELAY`（transient LLM/API 失败的有界重试，默认 3 / 15）
- `RESUME=true|false`（是否跳过已有报告中 `status=ok` 的任务，默认 false）
- `TASK_ID`、`SKIP_VERIFY`、`MODEL` 等

生成 `base+ce` 的示例：

```bash
PIPELINE_VARIANT=enhanced \
ENABLE_CONSTRAINT_EXTRACTION=true \
SPEC_SELF_CHECK_ROUNDS=1 \
ENABLE_CODE_REPAIR=false \
ENABLE_SPEC_EVALUATION=true \
REQUEST_TIMEOUT=120 \
LLM_RETRIES=3 \
LLM_RETRY_DELAY=15 \
RESUME=true \
OUTPUT_DIR=outputs/req2code-ce-only-0520 \
./scripts/run_openrouter_requirement_pipeline.sh
```

严格 `base+repair` 示例：

```bash
PIPELINE_VARIANT=enhanced \
ENABLE_CONSTRAINT_EXTRACTION=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=simple \
CODE_REPAIR_MAX_ITER=3 \
REUSE_ARTIFACTS_FROM=outputs/req2code-base-0520 \
REQUEST_TIMEOUT=120 \
LLM_RETRIES=3 \
LLM_RETRY_DELAY=15 \
RESUME=true \
OUTPUT_DIR=outputs/req2code-base-repair-0520 \
./scripts/run_openrouter_requirement_pipeline.sh
```

严格 `base+ce+wybecoder` 示例：

```bash
PIPELINE_VARIANT=enhanced \
ENABLE_CONSTRAINT_EXTRACTION=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=wybecoder \
WYBECODER_CANDIDATES=3 \
CODE_REPAIR_MAX_ITER=3 \
REUSE_ARTIFACTS_FROM=outputs/req2code-ce-only-0520 \
REQUEST_TIMEOUT=120 \
LLM_RETRIES=3 \
LLM_RETRY_DELAY=15 \
RESUME=true \
OUTPUT_DIR=outputs/req2code-ce-wybecoder-0520 \
./scripts/run_openrouter_requirement_pipeline.sh
```

Java/JML/OpenJML 对应的一键脚本：

```bash
ENABLE_CODE_REPAIR=true \
ENABLE_CONSTRAINT_EXTRACTION=true \
SPEC_SELF_CHECK_ROUNDS=1 \
CODE_REPAIR_MAX_ITER=3 \
REQUEST_TIMEOUT=120 \
LLM_RETRIES=3 \
LLM_RETRY_DELAY=15 \
RESUME=true \
OUTPUT_DIR=outputs/java-req2code-openrouter \
OPENJML_SOLVER=/usr/bin/z3 \
./scripts/run_openrouter_java_requirement_pipeline.sh
```

Java 严格 `base+wybecoder` 一键脚本示例：

```bash
ENABLE_CONSTRAINT_EXTRACTION=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=wybecoder \
WYBECODER_CANDIDATES=3 \
CODE_REPAIR_MAX_ITER=3 \
REUSE_ARTIFACTS_FROM=outputs/java-base-0624 \
REQUEST_TIMEOUT=120 \
LLM_RETRIES=3 \
LLM_RETRY_DELAY=15 \
RESUME=true \
OUTPUT_DIR=outputs/java-base-wybecoder-0624 \
OPENJML_SOLVER=/usr/bin/z3 \
./scripts/run_openrouter_java_requirement_pipeline.sh
```

Java 严格 `base+ce+wybecoder` 一键脚本示例：

```bash
ENABLE_CONSTRAINT_EXTRACTION=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=wybecoder \
WYBECODER_CANDIDATES=3 \
CODE_REPAIR_MAX_ITER=3 \
REUSE_ARTIFACTS_FROM=outputs/java-ce-only-0624 \
REQUEST_TIMEOUT=120 \
LLM_RETRIES=3 \
LLM_RETRY_DELAY=15 \
RESUME=true \
OUTPUT_DIR=outputs/java-ce-wybecoder-0624 \
OPENJML_SOLVER=/usr/bin/z3 \
./scripts/run_openrouter_java_requirement_pipeline.sh
```

Rust/Verus 对应的一键脚本：

```bash
PIPELINE_VARIANT=enhanced \
ENHANCEMENT_METHOD=both \
SPEC_SELF_CHECK_ROUNDS=1 \
CODE_REPAIR_MAX_ITER=3 \
REQUEST_TIMEOUT=120 \
LLM_RETRIES=3 \
LLM_RETRY_DELAY=15 \
RESUME=true \
OUTPUT_DIR=outputs/rust-req2code-openrouter \
./scripts/run_openrouter_rust_requirement_pipeline.sh
```

Rust 严格 `base+wybecoder` 一键脚本示例：

```bash
PIPELINE_VARIANT=enhanced \
ENABLE_CONSTRAINT_EXTRACTION=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=wybecoder \
WYBECODER_CANDIDATES=3 \
CODE_REPAIR_MAX_ITER=3 \
REUSE_ARTIFACTS_FROM=outputs/rust-base-0626 \
REQUEST_TIMEOUT=120 \
OUTPUT_DIR=outputs/rust-base-wybecoder-0626 \
./scripts/run_openrouter_rust_requirement_pipeline.sh
```

Rust 严格 `base+ce+wybecoder` 一键脚本示例：

```bash
PIPELINE_VARIANT=enhanced \
ENABLE_CONSTRAINT_EXTRACTION=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=wybecoder \
WYBECODER_CANDIDATES=3 \
CODE_REPAIR_MAX_ITER=3 \
REUSE_ARTIFACTS_FROM=outputs/rust-ce-only-0626 \
REQUEST_TIMEOUT=120 \
OUTPUT_DIR=outputs/rust-ce-wybecoder-0626 \
./scripts/run_openrouter_rust_requirement_pipeline.sh
```

Python/Nagini 对应的一键脚本：

```bash
PIPELINE_VARIANT=enhanced \
ENHANCEMENT_METHOD=both \
SPEC_SELF_CHECK_ROUNDS=1 \
CODE_REPAIR_MAX_ITER=3 \
REQUEST_TIMEOUT=120 \
LLM_RETRIES=3 \
LLM_RETRY_DELAY=15 \
RESUME=true \
OUTPUT_DIR=outputs/python-nagini-req2code-openrouter \
./scripts/run_openrouter_python_nagini_requirement_pipeline.sh
```

Python/Nagini 严格 `base+wybecoder` 一键脚本示例：

```bash
PIPELINE_VARIANT=enhanced \
ENABLE_CONSTRAINT_EXTRACTION=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=wybecoder \
WYBECODER_CANDIDATES=3 \
CODE_REPAIR_MAX_ITER=3 \
REUSE_ARTIFACTS_FROM=outputs/python-nagini-base-0627 \
REQUEST_TIMEOUT=120 \
LLM_RETRIES=3 \
LLM_RETRY_DELAY=15 \
RESUME=true \
OUTPUT_DIR=outputs/python-nagini-base-wybecoder-0627 \
./scripts/run_openrouter_python_nagini_requirement_pipeline.sh
```

Python/Nagini 严格 `base+ce+repair` 一键脚本示例：

```bash
PIPELINE_VARIANT=enhanced \
ENABLE_CONSTRAINT_EXTRACTION=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=simple \
CODE_REPAIR_MAX_ITER=3 \
REUSE_ARTIFACTS_FROM=outputs/python-nagini-ce-0627 \
REQUEST_TIMEOUT=120 \
LLM_RETRIES=3 \
LLM_RETRY_DELAY=15 \
RESUME=true \
OUTPUT_DIR=outputs/python-nagini-ce-repair-0627 \
./scripts/run_openrouter_python_nagini_requirement_pipeline.sh
```

Python/Nagini 严格 `base+ce+wybecoder` 一键脚本示例：

```bash
PIPELINE_VARIANT=enhanced \
ENABLE_CONSTRAINT_EXTRACTION=false \
ENABLE_CODE_REPAIR=true \
CODE_REPAIR_STRATEGY=wybecoder \
WYBECODER_CANDIDATES=3 \
CODE_REPAIR_MAX_ITER=3 \
REUSE_ARTIFACTS_FROM=outputs/python-nagini-ce-0627 \
REQUEST_TIMEOUT=120 \
LLM_RETRIES=3 \
LLM_RETRY_DELAY=15 \
RESUME=true \
OUTPUT_DIR=outputs/python-nagini-ce-wybecoder-0627 \
./scripts/run_openrouter_python_nagini_requirement_pipeline.sh
```

Rust/Python ablation 可通过 `PIPELINE_VARIANT=base`，或
`PIPELINE_VARIANT=enhanced ENHANCEMENT_METHOD=ce|repair|both` 选择。严格 repair /
wybecoder ablation 使用 `REUSE_ARTIFACTS_FROM` 复用 base 或 base+ce 输出。

后评估脚本（只评估已有输出，不重新生成）：

- `scripts/run_constraint_entailment_evaluation.sh`
  - 输入：`OUTPUT_DIR/specs/*.json` + 固定 manual ground-truth spec 文件
  - 输出：`OUTPUT_DIR/reports/constraint_entailment.json`
  - 评估指标：ground-truth spec coverage、post/frame coverage、pre over-constraint

示例：

```bash
OUTPUT_DIR=outputs/req2code-openrouter-enhanced \
./scripts/run_constraint_entailment_evaluation.sh
```

Java/JML 对应命令：

```bash
OUTPUT_DIR=outputs/java-req2code-openrouter \
./scripts/run_java_constraint_entailment_evaluation.sh
```

Rust/Verus 对应命令：

```bash
OUTPUT_DIR=outputs/rust-req2code-openrouter \
./scripts/run_rust_constraint_entailment_evaluation.sh
```

Python/Nagini 对应命令：

```bash
OUTPUT_DIR=outputs/python-nagini-req2code-openrouter \
./scripts/run_python_nagini_constraint_entailment_evaluation.sh
```

生成最终 benchmark summary：

```bash
OUTPUT_DIR=outputs/req2code-openrouter-enhanced \
./scripts/run_req2code_benchmark_summary.sh
```

Java/JML 对应命令：

```bash
OUTPUT_DIR=outputs/java-req2code-openrouter \
./scripts/run_req2code_benchmark_summary.sh
```

Rust/Verus 对应命令同样使用统一 summary：

```bash
OUTPUT_DIR=outputs/rust-req2code-openrouter \
./scripts/run_req2code_benchmark_summary.sh
```

Python/Nagini 对应命令同样使用统一 summary：

```bash
OUTPUT_DIR=outputs/python-nagini-req2code-openrouter \
./scripts/run_req2code_benchmark_summary.sh
```

## 9. 实验与对比建议（论文友好）

建议至少报告四组：

1. `base`
2. `base+ce`（只开 constraint extraction / spec self-check）
3. `base+repair`（复用 base artifacts，只开 code repair）
4. `base+ce+repair`（复用 base+ce artifacts，只开 code repair）

其中 `base+repair` 必须继承 `base` 的 `specs/` 与 `code/`；`base+ce+repair` 必须继承
`base+ce` 的 `specs/` 与 `code/`。独立重跑可以作为随机性/鲁棒性补充实验，但不作为主
ablation 的边际贡献依据。

关键指标：

- verify pass rate
- 平均修复轮数
- requirement-spec 缺失约束数（来自 `alignment_check`）
- requirement coverage micro/macro（来自 `benchmark_summary.json`）
- joint success（来自 `benchmark_summary.json`）
- 每题 token/时延成本（可选）

## 10. 当前边界与后续可选增强

当前增强仍保持“轻量改造”原则，尚未做：

- spec-aware code skeleton（如 `requires` -> 显式检查模板）
- requirement 与 spec 的 embedding 匹配（方法 B，可作为后续增强）
- 更细粒度的约束类型标签（安全性、边界、单调性等）

这些可以作为下一阶段增量，不影响现有 base/enhanced 可比性。

## 11. C/ACSL 阶段总结与多语言迁移基线

C 语言 track 已完成从数据、解析、评估到 pipeline 的闭环，后续 Java、Rust、Python 应以本节
约束作为迁移基线。

### 11.1 已完成事项

- **Ground truth 审计**：修订 23 个题目的截断量词、参数名、数组下标、behavior、assigns 和表达式错误；修订由 `scripts/fix_c_ground_truth_clauses.py` 保留为可重放脚本。
- **ACSL/C 解析**：entailment evaluator 已处理量词绑定分号、行内注释、链式比较、`\result`/`result`、ACSL label、指针解引用和复杂等式规范化。解析失败不能直接记为 coverage failure。
- **Code-only oracle**：100 道 C 题拥有独立 canonical `code_only_contract`，只包含接口级 requires/assigns/ensures，不泄漏 loop invariant、variant 或其他实现级证明注解。
- **合同保持**：初始生成和每轮 repair 前后都会恢复 canonical 合同，并记录 `contract_enforcement`；simple repair 和 WybeCoder repair 复用同一批 initial artifacts。
- **统一评估**：完整链路报告 code validity、requirement coverage（micro/macro）和 joint success；code-only 另用 `oracle_contract_consistency.json` 检查合同是否被篡改。

### 11.2 当前 C 结果与数据边界

重评估使用修订后的 ground truth、解析器和评估方向。DeepSeek default 的 Direct 基线为
`outputs/req2code-base-0622`；四模型四范式汇总写入 `outputs/c_re_evaluation_current.json`。
100% 只适用于通过审计且未被改写的 code-only oracle 一致性检查；完整链路 coverage 仍真实反映
模型生成 spec 与人工 semantic targets 的对齐程度。

task 42（GCD）的 divisibility semantic target 已保留，但 reference WP 证明目前超时。它应标记
为 oracle validation/proof issue 并单独跟踪，不能删除 target、削弱合同或增加不合理前置条件。

当前重评估汇总（`Code Valid`、`Coverage`、`Joint` 分别为通过题数/100、macro coverage、通过题数/100）：

| Model | Direct | Direct + CE | Direct + repair | Direct + CE + repair |
| --- | --- | --- | --- | --- |
| DeepSeek default | 34 / 0.4327 / 14 | 30 / 0.6047 / 17 | 60 / 0.4327 / 21 | 54 / 0.6047 / 24 |
| Kimi-k2.7-code | 68 / 0.6831 / 26 | 71 / 0.7350 / 31 | 86 / 0.6831 / 30 | 86 / 0.7350 / 35 |
| Qwen3.6-plus | 50 / 0.5233 / 21 | 39 / 0.7131 / 23 | 64 / 0.5233 / 25 | 66 / 0.7131 / 29 |
| Claude-Sonnet-5 | 73 / 0.7826 / 39 | 56 / 0.7879 / 34 | 80 / 0.7826 / 41 | 77 / 0.7879 / 40 |

该表只代表当前 C 数据和评估规则下的结果；迁移到其他语言时应保留字段含义，不直接比较不同
验证器的绝对难度。

### 11.3 Java/Rust/Python 迁移要求

每种语言都应提供独立的 requirement/signature/ground-truth、canonical code-only contract、
reference validation、生成/合同恢复/verifier/repair/summary pipeline，并使用语言专属 parser
和 verifier auxiliary-condition 规则。spec-only 条件天然满足时无需另造 spec-only track；
code-only 不得把 verifier 辅助条件当成需求覆盖；repair 只能修改实现和实现级注解；缺失输出、
解析失败、验证错误和 timeout 使用固定分母计入报告。语言特有题目先分别报告，不在语义统一前
合并成跨语言总分。
