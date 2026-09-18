# Code-Only Oracle Contract Benchmark 设计与实施计划

本文档记录当前全链路 benchmark 的规格边界，并规划 C/ACSL 后端的
`code_only_contract` 数据与 code-only pipeline。本文档首先服务于 C 语言实现；完成并验证后，
相同原则可迁移到 Java/JML、Rust/Verus 与 Python/Nagini 后端。

## 1. 背景与目标

当前 benchmark 的主任务是全链路生成：

```text
Requirement -> Generated Function Contract -> Generated Code + Proof Annotations -> Verifier
```

主评估同时检查两个性质：

1. 生成代码是否满足模型自己生成的函数合同；
2. 生成函数合同是否覆盖人工构造的 ground-truth 语义目标。

这种设计保留了规格生成错误向代码生成阶段传播的真实影响，适合作为论文的主要任务。
为了进一步定位失败来源，还需要增加一个隔离的 code-only 诊断任务：固定一个人工构造、
可被 verifier 使用的函数合同，只评估模型实现代码和合成证明注解的能力。

新的诊断任务定义为：

```text
Requirement + Signature + Oracle Function Contract
    -> Generated Code + Implementation-Level Proof Annotations
    -> Verifier
```

本文使用 **oracle function contract** 表示 code-only 输入中的人工函数合同，避免把它与包含
循环不变量和完整证明脚手架的“完整 ground-truth program specification”混淆。

## 2. 当前实现状态

### 2.1 已有的规格分层

当前 C pipeline 已经在数据结构和 prompt 中区分两类规格。

第一类是 canonical function contract：

```text
requires
assigns
ensures
```

它存储在 spec artifact 的 `acsl_block` 中，直接位于目标函数上方。Requirement coverage
评估只针对这一层进行。

第二类是 implementation-level proof annotations：

```text
loop invariant
loop assigns
loop variant
assert / ghost state / other statement annotations
```

它们依赖具体实现，应位于函数体和相应循环附近，不属于函数合同，也不参与当前的
requirement-spec coverage 主指标。

### 2.2 `code_annotation_hints` 的现状

当前 spec generation artifact 还允许包含：

```json
{
  "code_annotation_hints": {
    "loop_invariants": [],
    "loop_assigns": [],
    "loop_variants": []
  }
}
```

这些字段是非约束性的候选提示，不是 canonical function contract。代码生成阶段可参考它们；
verification-guided repair，尤其是 WybeCoder-style repair，可以修改代码体和 statement-level
annotations，但必须冻结 `acsl_block`。

因此，当前系统更准确的描述是：规格阶段生成冻结的函数合同，并可能提供非绑定的 proof
hints；具体循环注解随实现生成，并可在 verifier feedback 下修复。

### 2.3 严格增量 repair 已经成立

当前 `base+repair`、`base+wybecoder`、`base+ce+repair` 与
`base+ce+wybecoder` 使用 `REUSE_ARTIFACTS_FROM` 复用冻结的 spec 和初始 code。
Repair 只允许更新函数体和实现级证明注解，不能通过削弱函数合同制造 verification pass。

已有实验产物表明，匹配的 generation/repair runs 之间 spec artifact 保持不变，而 code
artifact 会发生变化。这一原则应直接复用于 code-only pipeline。

### 2.4 现有 manual ground truth 的用途与限制

当前文件：

```text
benchmarks/frama-c-problems/requirements/requirements_100_ground_truth_specs.json
```

主要用于 requirement coverage evaluation。每道题包含原子化的
`ground_truth_clauses`，类型包括 `requires`、`assigns` 和 `ensures`。

这些原子目标表达了需要评估的需求语义，但不能直接假设它们已经构成 verifier-ready 的
code-only contract，原因包括：

- coverage ground truth 的目标是语义判分，而不是提供可直接执行的统一合同；
- 部分题目的 `ground_truth_contract` 为空；
- 为证明内存安全、算术安全或正常终止所需的函数级条件，可能没有被纳入 coverage targets；
- 原子 clause 需要确定顺序、behavior 结构和合法 ACSL 包装；
- reference contract 中可能混有与参考实现绑定的 proof annotations，不能整体复制给模型。

因此，不能简单把 reference source 的全部 ACSL 注解作为 code-only 输入，也不能未经校验地把
coverage clauses 拼接后直接用于正式实验。

### 2.5 Reference source 是首选合同来源

C benchmark 的 100 个 reference programs 位于：

```text
benchmarks/frama-c-problems/ground-truth
```

这些程序已经在 benchmark 构建阶段通过 Frama-C/WP。目标函数上方的 function-level ACSL
因此是构造 `code_only_contract` 的首选来源：它通常比从原子 coverage targets 重新拼装合同
更完整，并且已经和至少一个正确实现共同经过 verifier 检验。

当前目录的静态检查结果进一步说明应采用“定向提取”，而不是复制整个 reference 文件：

- 100 个 reference C files 均可作为候选来源；
- 45 个文件包含 loop annotations；
- 48 个文件包含额外 assertion 或测试辅助内容；
- 48 个文件包含多个 ACSL blocks；
- 5 个目标函数合同使用 `behavior`；
- 27 道题的 manual JSON `ground_truth_contract` 为空，但 reference source 中存在函数合同。

因此，数据构造的默认方向调整为：

```text
Reference target-function contract
    + Atomic ground-truth alignment/audit
    + Necessary manual correction
    -> code_only_contract
```

Reference source 提供 verifier-ready 候选合同；现有 atomic ground truth 继续承担需求语义审计
和 coverage target 的角色。两者不能相互替代。

### 2.6 C 阶段落地状态

C track 已完成 100 道 code-only contract 的构造、合同一致性检查、代码生成与增量 repair
pipeline。canonical 数据位于
`benchmarks/frama-c-problems/requirements/requirements_100_code_only_contracts.json`，运行
入口为 `scripts/run_c_code_only_pipeline.py`，oracle 一致性报告为
`reports/oracle_contract_consistency.json`。该报告用于确认合同冻结并不等价于 requirement
semantic coverage；后者仍由 constraint-entailment evaluator 负责。

构造期间修订了 23 道 C 题的 manual clauses，并扩展 ACSL parser 以避免格式差异造成的假阴性。
task 42 的 GCD divisibility target 虽已保留在 oracle 语义中，但 reference WP 仍出现 timeout，
因此该题应记录为 oracle validation/proof issue，不能以删除目标或过强 requires 绕过。

### 2.7 Rust/Verus 阶段落地状态

Rust track 已从 100 个 reference target-function header 定向提取函数级 `requires/ensures`，
生成 canonical 数据
`benchmarks/rust-verus-problems/requirements/requirements_100_code_only_contracts.json`。
100 道题的 reference clauses 与 curated `ground_truth_clauses` 全部精确一一对应，因此当前
Rust oracle 不需要额外的 verifier-only 前置条件，也没有人工修改合同。

Rust 的合同属于函数头语法，pipeline 冻结的是命名返回值后的 canonical function signature、
`code_only_contract` 文本和结构化 `verus_clauses` 三者。12 个 reference loop invariants 与
12 个 `decreases` clauses 均保留在 reference 函数体中用于数据验收，但不会进入模型输入。
运行入口为 `scripts/run_rust_code_only_pipeline.py`，一致性检查为
`scripts/evaluate_rust_code_only_oracle.py`；检查同时覆盖 spec artifact 与最终 Rust source。
当前 reference validation 为 `100 pass / 100 total`。

## 3. Code-Only 任务的规格边界

### 3.1 应提供给模型的内容

每道题的 code-only 输入应包含：

- 原始自然语言 requirement；
- 固定的函数签名；
- verifier-ready 的 oracle function contract；
- 必要的类型、结构体或全局声明上下文；
- 与所有方法一致的 verifier/toolchain 基本说明。

Oracle function contract 应完整包含函数接口层面的义务：

- semantic preconditions；
- memory-validity、separation 和必要的输入安全条件；
- semantic postconditions；
- frame conditions，例如 `assigns`；
- 必要时的 behavior completeness/disjointness；
- 与函数接口相关的 overflow 或 exceptional-behavior 约束。

这里的“完整”表示对函数调用者完整，而不是把某个参考实现的证明过程全部暴露给模型。

### 3.2 不应提供给模型的内容

以下内容必须从 oracle input 中排除：

- reference loop invariants；
- reference loop assigns；
- reference loop variants；
- 函数体内的 reference assertions；
- 与参考实现绑定的 ghost variables 和 lemmas；
- reference implementation 本身或能够直接还原其控制流的 proof skeleton；
- 由后续 verifier failure 提前泄漏的 repair hints。

这些内容属于 code/proof synthesis 的评测对象。模型可在初始生成中自行构造，也可由 simple
repair 或 WybeCoder-style repair 在保持 oracle contract 不变的前提下修改。

### 3.3 为什么不能提供完整参考注解

循环不变量由具体算法决定。同一个函数合同可能由 forward loop、backward loop、多个循环、
递归或无循环实现满足。提供参考实现的 loop invariant 会泄漏算法结构，并把 code-only
任务变成给定 proof skeleton 的程序补全任务。

因此，本 benchmark 隔离的是：

> 在正确函数接口合同已知时，模型能否联合生成实现与实现相关的证明注解，并通过 verifier。

它不应被描述为“给定完整形式化证明后生成代码”。

## 4. `code_only_contract` 数据设计

### 4.1 建议的存储方式

第一版可以在现有 100 题 ground-truth JSON 中新增字段，也可以维护独立文件。为了避免改变
当前 coverage evaluator 的稳定输入，建议先使用独立文件：

```text
benchmarks/frama-c-problems/requirements/requirements_100_code_only_contracts.json
```

建议每条记录使用以下 schema：

```json
{
  "id": 1,
  "path": "pointers/swap.c",
  "requirement_en": "...",
  "function_signature": "void swap(int *a, int *b);",
  "code_only_contract": "/*@ ... */",
  "contract_provenance": {
    "source_file": "benchmarks/frama-c-problems/ground-truth/pointers/swap.c",
    "source_function": "swap",
    "extraction_method": "target_function_preceding_acsl_block",
    "source_contract_hash": "...",
    "manually_modified": false
  },
  "contract_clauses": [
    {
      "id": "co1",
      "type": "requires",
      "expr": "\\valid(a)",
      "role": "verification_precondition",
      "source": "manual"
    }
  ],
  "coverage_target_ids": ["r1", "r2"],
  "auxiliary_contract_clause_ids": ["co1"],
  "excluded_reference_annotations": {
    "loop_invariants": 0,
    "loop_assigns": 0,
    "loop_variants": 0,
    "assertions": 0
  },
  "validation": {
    "syntax_valid": true,
    "reference_verifies": true,
    "verifier": "frama-c/wp",
    "timeout_seconds": 120
  },
  "notes": ""
}
```

### 4.2 Clause 角色

`contract_clauses` 应显式区分两类来源：

- `semantic_target`：现有原子化 ground-truth coverage clause；
- `verification_precondition`：为了形成合理、可验证的函数接口而补充，但不应反向提高
  requirement coverage 分数的辅助条件。

这种区分可以避免把“为 verifier 提供足够的调用前提”误算成模型从自然语言需求中应当恢复的
语义目标，也便于后续报告 oracle contract 的构成。

### 4.3 构造原则

每个 `code_only_contract` 应满足：

1. 包含现有人工 ground-truth 的所有适用函数级 clauses；
2. 不包含任何 reference implementation-level proof annotation；
3. 不通过过强前置条件使任务退化或 vacuous；
4. frame 条件与需求语义、函数签名和 reference behavior 一致；
5. ACSL 可解析，且 reference implementation 在保留自身内部 proof annotations 时可验证；
6. 合同文本能够被 pipeline 程序化插入并在 repair 后恢复；
7. 构造过程可审计，补充 clause 必须记录 role、source 和 rationale。

### 4.4 Reference contract 提取规则

提取器应根据 dataset 中的 `path` 和 `function_signature` 定位目标函数，并只提取紧邻该目标
函数定义之前的 function-level ACSL block。不能假设文件中的第一个或唯一 ACSL block 就是
目标合同，因为 reference 文件可能包含测试函数、多个 annotations 或辅助函数。

提取时应保留所有合法的函数接口合同结构：

- `requires`；
- `assigns`；
- `ensures`；
- `behavior` 与 `assumes`；
- `complete behaviors` 与 `disjoint behaviors`。

提取时应排除：

- 函数体内的 `loop invariant`、`loop assigns` 和 `loop variant`；
- `//@ assert` 或 statement-level `assert`；
- 测试函数、`main` 和它们的 proof goals；
- ghost state、辅助 lemmas 或与 reference control flow 绑定的 proof skeleton；
- 普通注释中的 `FIX`、`PROOF GOALS` 等维护说明。

提取必须基于目标函数位置与 ACSL/C 结构，而不能简单使用“抓取文件中第一个
`/*@ ... */`”的正则规则。第一版可以使用保守 parser 加结构校验；无法唯一定位时应进入人工
审核队列，不能静默选择合同。

### 4.5 Reference 与 atomic ground truth 对齐

提取出的 reference contract 不能因为“曾经验证通过”就自动成为最终 oracle。验证通过只说明
reference implementation 满足它，不保证它对 requirement 最小、完整且不过度约束。

每道题还应执行：

1. 将 reference function contract 分解为 clauses；
2. 与现有 `ground_truth_clauses` 做双向映射；
3. 确认所有适用 semantic targets 均被 oracle contract 覆盖；
4. 将额外 memory safety、separation、frame 等 clauses 标为辅助接口条件；
5. 审核额外 `requires` 是否过强或使 verification vacuous；
6. 对不一致项记录人工决定及 rationale。

Reference contract 可被人工修正，但必须在 `contract_provenance` 中记录修改状态、原始 hash、
最终 hash 和修改原因，保证数据构造过程可审计。

### 4.6 Reference verification 的含义

数据验收时，可以使用 reference implementation 内部原有的 loop invariants 和其他 proof
annotations，因为该步骤只验证 oracle contract 是否合理，不是模型评测。

正式 code-only generation 输入中必须删除这些 reference implementation annotations，且不得
提供 reference code。模型需要重新生成自己的实现级证明注解。

## 5. C Code-Only Pipeline 设计

### 5.1 Pipeline 输入与输出

输入：

```text
requirement
function_signature
code_only_contract
optional type context
```

输出目录建议保持现有结构：

```text
<OUTPUT_DIR>/specs/...             # copied/frozen oracle contract artifact
<OUTPUT_DIR>/code/...              # generated or repaired C source
<OUTPUT_DIR>/reports/results.json  # verification and repair trajectory
```

即使 oracle contract 不是模型生成的，也应复制到 run-specific `specs/` 中，以保证结果自包含、
可复现，并让 contract-preservation 检查复用现有机制。

### 5.2 初始 code generation

新的 code-only prompt 应明确：

- oracle `code_only_contract` 必须原样位于函数定义正上方；
- 模型只能实现给定签名；
- 模型可自行选择算法；
- 模型应根据自己的控制流生成必要的 loop invariants、loop assigns、loop variants 和 asserts；
- 不应把 implementation annotations 写入函数合同；
- 不允许修改、删除、重排或弱化 oracle contract。

`code_annotation_hints` 在主 code-only 设置中建议为空，以确保 proof annotations 真正由 code
synthesis 阶段产生。若未来希望研究 oracle proof hints，可另设明确标注的辅助实验，不应与主
code-only 结果混合。

### 5.3 Contract preservation

不能只依赖 prompt 要求模型保留合同。C code-only pipeline 应增加程序化 enforcement：

1. 从 dataset artifact 读取 canonical `code_only_contract`；
2. 识别目标函数定义；
3. 删除或替换模型输出中目标函数上方的 ACSL function contract；
4. 插入 canonical oracle contract；
5. 抽取源码合同并与 canonical artifact 比较；
6. 不一致或无法安全插入时，将该题记为失败，而不是验证模型自行改写的合同。

Java 和 Python 后端已有类似 contract enforcement 机制，C 后端可以复用其设计思想，但需要
使用 C signature/ACSL parser，不能依赖脆弱的任意正则替换。

### 5.4 Verification 与 repair

初始代码由 Frama-C/WP 验证。失败后可以运行两种 repair strategy：

```text
simple:
  verifier log -> one repair candidate -> verify

wybecoder:
  verifier log -> failure/subgoal plan
               -> multiple focused candidates
               -> verify candidates
```

Repair 可修改：

- 函数体逻辑；
- 局部变量和控制流；
- loop invariants/assigns/variants；
- statement assertions 和必要的 implementation proof annotations。

Repair 不可修改：

- 函数签名；
- oracle function contract；
- 外部类型上下文；
- requirement 或 benchmark input。

每个 candidate 写入并验证前都应重新执行 contract enforcement。

### 5.5 建议的实验范式

Code-only 隔离实验不再需要 CE，因为 oracle contract 已经给定。主要比较：

```text
oracle-contract + generation
oracle-contract + simple repair
oracle-contract + WybeCoder repair
```

其中两个 repair 版本必须复用完全相同的初始 code artifact。不能分别重新采样 initial code，
否则 repair strategy 的收益会与 generation sampling variance 混合。

若需要与全链路四范式对应，可以把 code-only 结果作为独立诊断表，而不是强行映射为
`base/base+ce/base+wybecoder/base+ce+wybecoder` 四组。CE 在 oracle contract 条件下没有待增强
的 spec generation 阶段。

## 6. 指标与报告

### 6.1 主指标

Code-only 主指标建议包括：

- initial code validity rate；
- post-repair code validity rate；
- absolute repair gain；
- repair success among initial failures；
- verifier timeout/error rate；
- contract mismatch/enforcement failure count。

### 6.2 辅助指标

可进一步报告：

- 平均 repair rounds；
- 平均 verifier calls；
- WybeCoder candidate pass position；
- failure taxonomy；
- loop-containing problems 与 loop-free problems 的分组结果；
- 首次生成是否包含 loop invariant/assigns/variant；
- repair 是否新增或修改实现级 proof annotations。

### 6.3 与全链路结果的关系

全链路结果回答：

> 模型能否从需求出发，生成正确合同，并实现满足该合同的可验证代码？

Code-only oracle-contract 结果回答：

> 当函数合同错误被控制后，模型能否生成实现及其证明注解？

两者的差异可用于诊断规格生成瓶颈，但不能简单相减并解释为严格的独立概率，因为 code
generation 难度会随合同强度、表达形式和实现自由度变化。

## 7. 实施步骤

### Phase 1：构造数据

1. 为 100 道 C 题读取 requirement、signature、atomic ground-truth clauses 和 reference source；
2. 按签名定位目标函数，提取其正上方的 function-level ACSL block；
3. 保留 `requires/assigns/ensures/behavior`，排除所有 implementation-level annotations；
4. 将提取合同与 atomic ground-truth clauses 对齐并标记 clause role；
5. 人工审核缺失语义、过强前置条件、额外 verifier conditions 和提取歧义；
6. 对必要修改记录 source/final hashes 与 rationale；
7. 生成独立的 `requirements_100_code_only_contracts.json`。

### Phase 2：数据校验工具

实现 deterministic validator：

- 校验 schema、id/path/signature 对齐；
- 检查提取合同确实紧邻目标函数，而不是测试函数或其他 ACSL block；
- 解析 `code_only_contract`；
- 检查禁止的 loop/statement annotations 未进入合同；
- 检查 coverage target ids 均可回溯到现有 ground truth；
- 检查 reference clauses、semantic targets 与辅助 clauses 的映射完整性；
- 将 oracle contract 注入 reference implementation；
- 保留 reference 内部 proof annotations并运行 Frama-C/WP；
- 输出逐题 validation report。

### Phase 3：Code-only generation

增加独立 CLI/wrapper，避免通过复杂 flag 把现有全链路入口变成两种任务：

```text
scripts/run_c_code_only_pipeline.py
scripts/run_openrouter_c_code_only_pipeline.sh
```

第一版可复用现有 LLM client、verifier adapter、artifact layout 和 repair strategy classes。

### Phase 4：严格增量 repair

1. 先运行一次 oracle-contract generation，冻结 `specs/` 和 initial `code/`；
2. simple repair 与 WybeCoder repair 分别从同一 source output 复制 artifacts；
3. 记录 source artifact hashes；
4. 验证 repair runs 的 oracle specs 完全相同；
5. 将所有 repair trajectory 写入 `results.json`。

### Phase 5：小规模 smoke test

正式 100 题实验前，选择覆盖以下类型的 5 至 10 道题：

- scalar、无循环；
- pointer mutation；
- array traversal；
- loop invariant required；
- assigns/frame sensitive；
- overflow or memory-safety sensitive。

先验证数据、contract enforcement、initial generation、simple repair、WybeCoder repair 和 summary
全链路均能运行，再扩展到完整数据集。

## 8. 验收标准

进入正式实验前，应满足：

- 100/100 条 code-only dataset 通过 schema validation；
- 100/100 条 oracle contracts 可由 Frama-C 解析；
- reference implementations 在 oracle contracts 下达到预先规定的验证通过标准；
- oracle inputs 不包含 reference loop/statement proof annotations；
- initial generation 与所有 repair candidates 均执行 contract enforcement；
- repair 前后 canonical oracle contract hash 不变；
- simple 与 WybeCoder 使用同一批 initial code；
- 缺失输出、API failure 和 parse failure 均按固定分母计为失败；
- report 可以区分 generation failure、contract enforcement failure、verification failure 和 timeout。

如果某题的 reference implementation 无法在合理的 oracle contract 下验证，应先修复或标记数据
问题，不能通过泄漏 reference proof skeleton 或增加不合理的强前置条件来获得 pass。

## 9. 需要特别避免的风险

### 9.1 把 reference verification 当作语义充分性证明

Reference program 通过 Frama-C/WP 只证明该实现满足给定合同，不证明合同完整表达 requirement，
也不证明前置条件不过强。Reference contract 必须与 atomic ground truth 对齐并经过人工审计。

### 9.2 Oracle contract 过强

不能用排除合法输入或直接固定内部状态的前置条件使任务变得平凡。新增 precondition 必须具有
接口层面的合理解释，并记录为辅助 verification clause。

### 9.3 Oracle contract 不完整

如果遗漏 frame、memory validity 或必要的正常行为条件，verification failure 可能来自数据合同，
而不是模型代码能力。Reference verification 是必要的 dataset gate。

### 9.4 泄漏参考算法

任何 loop invariant、循环边界演化、ghost accumulator 或中间数组性质都可能暴露 reference
control flow。正式输入中只保留函数接口层合同。

### 9.5 合同被 repair 悄然修改

Prompt discipline 不足以保证公平性。必须程序化恢复 canonical contract，并在 summary 中把
contract mismatch 记为失败。

### 9.6 把辅助条件误算为 requirement coverage

`code_only_contract` 可以比 coverage target 更适合 verifier，但新增 clauses 不应反向改变已有
全链路 requirement coverage 指标。两个数据角色必须保持显式分离。

## 10. 预期论文表述

建议将该实验描述为：

> To diagnose implementation and proof-synthesis capability independently of contract generation,
> we introduce a code-only setting with an oracle function contract. The oracle contains the full
> interface-level preconditions, postconditions, and frame conditions, but excludes all
> implementation-specific proof annotations such as loop invariants. Models must jointly synthesize
> the implementation and such annotations, while the oracle contract remains frozen throughout
> verifier-guided repair.

该设置是全链路主评测的诊断补充，而不是替代。全链路仍是论文的主要任务；code-only 用于回答
在正确函数合同已知时，代码与证明注解生成能力还剩下多少瓶颈。
