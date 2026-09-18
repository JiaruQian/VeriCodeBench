# Requirement->Spec->Code Benchmark 设计（Manual Ground-Truth Spec Entailment）

本文档记录 `requirement -> specification -> code -> verify` benchmark 的当前统一评估方式，重点解决：

- `code` 是否符合生成的 `spec`（由 Frama-C/WP 验证）
- 生成的 `spec` 是否覆盖人工构造的 ground-truth `spec`

---

## 1. 核心思想

100 道题统一使用一个 manual ground-truth spec 文件作为覆盖目标：

- `benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json`

这个文件中的 ACSL 子句来自人工构造的规格：有些子句可直接从 requirement 语义抽取，有些子句参考了原 Frama-C 数据集的 ground-truth ACSL。二者在 benchmark 中都视为同一种 manual ground truth。

评估时：

- 生成的 ACSL block 被抽取为子句集合 `S`
- manual ground-truth ACSL 被抽取为目标子句集合 `G`
- 对每个 `g_i in G`，按子句类型决定蕴含方向
  - `requires`：检查 `g_i ⊨ generated_requires`
  - `ensures/assigns`：检查 `generated_clause(s) ⊨ g_i`

直观含义：

- 对前置条件，生成 spec 不能比 manual ground truth 更强，否则会过度约束输入
- 对后置条件和 frame，生成 spec 必须足够强，能推出 manual ground truth 要求的行为

---

## 2. 数据构造

### 2.1 Manual Ground Truth Spec

主文件：

- `benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json`

每条样例包含：

- `id`, `path`
- `ground_truth_file`
- `ground_truth_source`
- `function_signature`
- `ground_truth_clauses[]`
  - `type`：`requires` / `ensures` / `assigns`
  - `expr`：ACSL 子句表达式
- `ground_truth_contract`

校验脚本：

```bash
python3 scripts/generate_ground_truth_specs.py
```

该脚本只校验并格式化已维护的 manual ground-truth 文件，不会从参考 C 文件重新抽取全部 ACSL 合同；否则会把验证辅助条件误加入评估目标。

## 3. 评估流程

脚本：

- `scripts/evaluate_constraint_entailment.py`

输入：

- `--ground-truth-spec-file`
- `OUTPUT_DIR/specs/*.json`

输出：

- `OUTPUT_DIR/reports/constraint_entailment.json`

### 3.1 子句抽取

从生成 spec 和 manual ground truth 中统一抽取：

- `requires ...;`
- `ensures ...;`
- `assigns ...;`

### 3.2 蕴含判定

对每个 ground-truth 子句：

1. 按 `requires/ensures/assigns` 选择候选生成子句
2. 做 exact match 和顶层合取子句匹配
3. 搜索生成子句组合，最多由 `--max-combo-size` 控制
4. 若安装了 `z3-solver`，尝试 SMT 蕴含判定

评估前会基于函数签名做参数位置 canonicalization，例如 `x,y` 和 `a,b` 都映射成 `arg0,arg1`，降低变量命名差异带来的误判。

### 3.3 指标

主指标：

- `ground_truth_spec_micro_coverage`
- `macro_avg_requirement_coverage`
- 每题 `requirement_coverage_x / requirement_coverage_n`

辅助指标：

- `pre_admissibility`
- `pre_overconstraint`
- `post_frame_coverage`

最终 summary 仍使用：

- code validity rate
- requirement coverage micro/macro
- joint success：code valid 且 manual ground-truth spec coverage full

---

## 4. 一键运行

```bash
OUTPUT_DIR=outputs/req2code-openrouter-enhanced \
./scripts/run_constraint_entailment_evaluation.sh

OUTPUT_DIR=outputs/req2code-openrouter-enhanced \
./scripts/run_req2code_benchmark_summary.sh
```

Java/JML/OpenJML 对应命令：

```bash
OUTPUT_DIR=outputs/java-req2code-openrouter \
./scripts/run_java_constraint_entailment_evaluation.sh

OUTPUT_DIR=outputs/java-req2code-openrouter \
./scripts/run_req2code_benchmark_summary.sh
```

Rust/Verus 对应命令：

```bash
OUTPUT_DIR=outputs/rust-req2code-openrouter \
./scripts/run_rust_constraint_entailment_evaluation.sh

OUTPUT_DIR=outputs/rust-req2code-openrouter \
./scripts/run_req2code_benchmark_summary.sh
```

也可以直接调用：

```bash
PYTHONPATH=. python3 scripts/evaluate_constraint_entailment.py \
  --ground-truth-spec-file benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/java-ce-0624
```

Java/JML 直接调用：

```bash
PYTHONPATH=. python3 scripts/evaluate_constraint_entailment.py \
  --language java \
  --ground-truth-spec-file benchmarks/java-problems/requirements/requirements_100_ground_truth_specs.json \
  --output-dir outputs/java-req2code-ce-only-0602-tem0
```

Rust/Verus 直接调用：

```bash
PYTHONPATH=. python3 scripts/evaluate_constraint_entailment.py \
  --language rust \
  --ground-truth-spec-file benchmarks/rust-verus-problems/requirements/requirements_50_ground_truth_specs.json \
  --output-dir outputs/rust-req2code-both-0608-tem0
```

所有语言的 coverage denominator 都按 manual ground truth 固定：

- 缺失或无法解析的 generated spec 会按该题 ground-truth clause 数计入分母，并计为 `0/n`。
  这样 LLM 请求失败或生成失败不会让 coverage denominator 变小。
- C/ACSL、Java/JML、Rust/Verus 都使用这个规则，保证 ablation 间 requirement coverage
  的分母一致。

Java/JML 评估还有一个额外约束：

- `benchmark_summary.json` 会检查 Java 源码中的 JML clauses 是否和 `specs/*.json`
  中的 canonical `jml_block` 一致。不一致说明 OpenJML 验证的 contract 和 requirement
  coverage 评估的 contract 不是同一个 contract，该题 code validity 计为失败。

Java/JML 表达式在 entailment 前还会做保守的表面规范化：

- 将 `requires P && Q` 等顶层合取展开为原子候选，同时保留原复合子句；
- 去除跨行 JML 的行首 `@`，统一 Java widening cast、字符常量、字符串 `length()`、
  布尔返回值和对象字段写法；
- 只在 generated `helper_declarations` 明确给出 `getX(){ return x; }` 时，才把 getter
  读取与对应字段读取视为同一表达；
- 对量词绑定变量做 alpha-renaming，并规范化 `==`/`!=` 两侧顺序。

这些规则不会把 `a[*]` 当作精确的 `a[i], a[j]` frame，也不会把 `Range.min/max`
当作 `Range.low/high`；真实的 frame 扩大或接口字段漂移仍会扣分。

Rust/Verus 评估复用同一个 entailment 框架，但 generated spec 从 `specs/*.json` 中的
canonical `verus_clauses` 读取；若旧 artifact 缺少该字段，才回退解析 `verus_contract`。
Rust 签名使用 Rust-only parser，支持 `Result<u64, ()>` 这类参数类型中的逗号，并将
`r`、`result` 和 named return 统一映射为同一返回值别名，避免返回值命名差异造成
coverage 误判。

Python/Nagini 表达式在 SMT 判定前会做语言专属规范化：

- 从函数签名保留 `bool` 参数和 `bool` 返回值的布尔类型，避免把它们错误建模成整数；
- 将 `len(...)`、`Old(...)`、list/dict 索引、成员关系和 `is`/`is not` 转为稳定的求解器表达；
- 递归支持 `Implies(p, q)`、`p ==> q` 和普通布尔析取之间的等价判定，包括多条 clauses 合取后的组合表达式；
- 支持将拆成多条的原子 `Requires` 重新合取后，与 ground truth 的复合前置条件比较。

这些规则只消除语法形态造成的假阴性，不把 post-state 容器读取等同于 `Old(...)`；若生成
spec 遗漏了 pre-state 语义，仍会按真实 coverage 缺失计分。该版本在报告中标记为
`manual_ground_truth_spec_entailment_v3`。
