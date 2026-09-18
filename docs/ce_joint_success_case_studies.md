# CE 与 Joint Success：典型成败案例集

本文基于各语言容器中的 Claude run 产物，选取 `base`、`base+ce`、`base+ce+wybecoder`
三档的代表性题目，说明“CE 增强 spec”对 `code_valid` 与 `joint_success` 的双向影响。

- 判定口径来自 `<run>/reports/benchmark_summary.json` 的 `per_problem`
  （`code_valid`、`requirement_coverage_x/n`、`joint_success`）。
- 失败原因来自 `<run>/reports/results.json` 的 `verification` 及同名 `*.verify.log`。
- `joint_success = code_valid && requirement_coverage_x == requirement_coverage_n`。
- 数据集：各语言 100 题。CE = constraint extraction + spec self-check；
  `+both` = 在 CE spec 冻结的前提下由 WybeCoder 做代码修复。

## 使用的 run 目录

| 语言 | 容器 | base | +ce | +both |
| --- | --- | --- | --- | --- |
| C | `Spec`（根 `/workspace`） | `outputs/C-base-claude-0706` | `outputs/C-ce-claude-0706` | `outputs/C-ce-wybecoder-claude-0706` |
| Java | `spec-java`（根 `/workspace`） | `outputs/java-base-claude-0706` | `outputs/java-ce-claude-0707` | `outputs/java-ce-wybecoder-claude-0707` |
| Rust | `spec-rust` | `outputs/rust-base-rust-0707` | `outputs/rust-ce-claude-0707` | `outputs/rust-ce-wybecoder-claude-0709` |
| Python | `spec-python` | `outputs/python-base-claude-0714` | `outputs/python-ce-claude-0714` | `outputs/python-ce-wybecoder-claude-0715`\* |

\* Python 的 `+both` 只有 `*-offline-repaired` 目录带完整评测报告，故 Python 的
`+both` 数字取自 `outputs/python-ce-wybecoder-claude-0715-offline-repaired`；
为可比，`base/+ce` 也取同源的 `*-offline-repaired`。

## 总体指标

| 语言 | base (valid/joint/cov) | +ce | +both |
| --- | --- | --- | --- |
| C | 73 / 39 / .749 | 56 / 34 / .768 | 77 / 40 / .768 |
| Java | 90 / 65 / .908 | 82 / 63 / .911 | 97 / 73 / .911 |
| Rust | 72 / 51 / .692 | 71 / 49 / .706 | 98 / 55 / .706 |
| Python (repaired) | 79 / 76 / .937 | 90 / 85 / .963 | 90 / 85 / .963 |

C/Java/Rust 呈现同一模式：**coverage 上升、valid 下降、joint 下降；`+both` 再把
valid/joint 拉起**。Python 的 repaired 集是例外（见文末备注）。

---

## 1. CE 把原本 joint success 的题弄坏（逻辑变难，非纯语法）

筛选条件：`base.joint_success=True`、`ce.joint_success=False`、`ce.code_valid=False`，
且失败来自证明/验证难度，而非解析或类型语法错误。

### 1.1 C id 5 `pointers/incr_a_by_b.c` —— 别名 frame 子句导致证明超时

- base：`code_valid=True`，coverage `2/2`，joint success。
- +ce：coverage 仍为 `2/2`，但 `code_valid=False`。

CE 为读指针补了 frame 事实：

```c
ensures *a == \old(*a) + \old(*b);
ensures *b == \old(*b);      // CE 新增
```

证明器需要证明 `*a = *a + *b;` 之后 `b` 的指向内容未变，即要排除 `a` 与 `b` 别名，
于是新增目标无法在时限内完成：

```text
[wp] 5 goals scheduled
[wp] [Timeout] typed_incr_a_by_b_ensures_2 (Qed 7ms) (Alt-Ergo 10s)
[wp] Proved goals:   4 / 5   (Timeout: 1)
```

base 为 `4/4`。这是“更强的契约本身没错，但把证明义务变难”的典型。

### 1.2 Java id 16 `array_extrema/Problem016_ArrayMin.java` —— 存在性循环不变式不可证

- base：`code_valid=True`，coverage `5/5`，joint success。
- +ce：coverage 仍为 `5/5`，但 `code_valid=False`。

CE 在循环不变式中引入了存在量词：

```java
/*@ loop_invariant (\exists int k; 0 <= k && k < i; a[k] == min) || i == 0;
  @ loop_invariant \forall int k; 0 <= k && k < i; min <= a[k];
  @ loop_assigns min, i;
  @ loop_decreases a.length - i;
  @*/
while (i < a.length) { ... }
```

OpenJML 无法建立该不变式的保持：

```text
verify: The prover cannot establish an assertion (LoopInvariant) in method min
  @ loop_invariant (\exists int k; 0 <= k && k < i; a[k] == min) || i == 0;
```

base 的 `\exists int k; 0 <= k && k < i; min == a[k]`（无 `|| i == 0`）与循环体配合
可证，CE 的加强版本反而不可证。

### 1.3 Python id 94 `dict_apis_ext/Problem094_DictKeyMapsToSelf.py` —— 更强的析取后置不可证

- base：`code_valid=True`，coverage `4/4`，joint success。
- +ce：coverage 仍为 `4/4`，但 `code_valid=False`。

CE 追加了长度析取子句：

```python
Ensures(key in d)
Ensures(len(d) == Old(len(d)) or (key not in Old(d) and len(d) == Old(len(d)) + 1))  # CE 新增
Ensures(d[key] == key)
```

Nagini 对同一实现无法证明该析取：

```text
Postcondition of dict_key_maps_to_self might not hold.
Assertion ((len(d) == Old(len(d))) or
          ((key not in Old(d)) and (len(d) == (Old(len(d)) + 1)))) might not hold.
```

base 只要求 `key in d` 与 `d[key] == key`，因此可过；CE 加强后 code validity 丢失。

> 同类（可作补充）：Java id 3 `array_basics/Problem003_FirstElement.java`
> 因 CE 增加 `normal_behavior` + 两个 `exceptional_behavior` 与数组帧事实，使
> `return a[0];` 触发 `PossiblyTooLargeIndex`。

---

## 2. CE 直接修好 coverage，从而达成 joint success

筛选条件：`base.code_valid=True` 但 coverage 不满（`joint_success=False`），
`ce.code_valid=True` 且 coverage 补齐（`joint_success=True`）。即 CE 补上了
ground-truth 漏掉、但 base spec 没有表达的契约目标。

### 2.1 C id 13 `more_arrays/equal_arrays.c` —— 由“双条件”细化为分行为契约

- base：coverage `4/6`，不 joint。
- +ce：coverage `6/6`，joint success。

base 只给出一个双向蕴含：

```c
ensures \result == 1 <==> (\forall integer i; 0 <= i < n ==> a[i] == b[i]);
ensures \result == 0 || \result == 1;
```

CE 显式拆成两个覆盖目标一致的行为：

```c
behavior all_equal:
  assumes \forall integer i; 0 <= i < n ==> a[i] == b[i];
  ensures \result == 1;
behavior not_equal:
  assumes \exists integer i; 0 <= i < n && a[i] != b[i];
  ensures \result == 0;
complete behaviors;
disjoint behaviors;
```

覆盖数从 4/6 升到 6/6，同时保持可验证。

### 2.2 Rust id 36 `vec_mutation/Problem036_VecPop.rs` —— 序列效应拆分成长度 + 逐点 frame

- base：coverage `2/3`，不 joint。
- +ce：coverage `3/3`，joint success。

base 用单条 subrange 事实表达整个序列效应：

```rust
ensures v@ == old(v)@.subrange(0, old(v).len() as int - 1)
```

CE 拆成“长度变化 + 逐点相等”两个可独立核对的单位：

```rust
ensures v.len() == old(v).len() - 1
ensures forall|i: int| 0 <= i < v.len() ==> v[i] == old(v)[i]
```

覆盖器要求序列效应同时具备长度、变更元素、未变更区域三类事实，base 的整合写法
只能算部分覆盖（2/3），CE 的拆分写法补齐为 3/3。

### 2.3 Python id 57 `scalar_arithmetic_ext/Problem057_ChooseIf.py` —— 补上另一分支

- base：coverage `1/2`，不 joint。
- +ce：coverage `2/2`，joint success。

base 只约束了 `flag` 为真的一支：

```python
Ensures(Implies(flag, Result() == x))
```

CE 补上互补分支：

```python
Ensures(Implies(flag, Result() == x))
Ensures(Implies(not flag, Result() == y))
```

覆盖数 1/2 → 2/2，joint success。

> 可作补充：Java id 49 `scalar_arithmetic/Problem049_SameSignNonzero.java`
> 由 `\result <==> ((x > 0) == (y > 0))` 展开为
> `\result == ((x > 0 && y > 0) || (x < 0 && y < 0))`，coverage 2/3 → 3/3。

---

## 3. CE 单独把可过的题弄坏，`+both` 又修回来

筛选条件：`base.joint_success=True`、`ce.joint_success=False`、`both.joint_success=True`
（且 coverage 保持一致）。这体现 WybeCoder 修复在“更强的 spec 让代码更难写”时的补偿价值。

### 3.1 Java id 16 `array_extrema/Problem016_ArrayMin.java` —— 用见证变量替换存在量词

- base：joint success（`5/5`）。
- +ce：`code_valid=False`（存在性循环不变式不可证，见 1.2）。
- +both：`code_valid=True`，coverage `5/5`，joint success。

WybeCoder 没有削弱契约，而是在实现中引入显式见证变量 `minIdx`，把不可证的存在量词
换成具体等式：

```java
int min = a[0];
int minIdx = 0;                 // 新增见证
int i = 1;
/*@ loop_invariant 0 <= minIdx && minIdx < i;
  @ loop_invariant a[minIdx] == min;
  @ loop_invariant \forall int k; 0 <= k && k < i; min <= a[k];
  @ loop_assigns min, minIdx, i;
  @ loop_decreases a.length - i;
  @*/
while (i < a.length) {
    if (a[i] < min) { min = a[i]; minIdx = i; }
    i++;
}
```

### 3.2 Java id 3 `array_basics/Problem003_FirstElement.java` —— 补前置守卫使索引义务可证

- base：joint success（`4/4`）。
- +ce：`code_valid=False`（`PossiblyTooLargeIndex` at `return a[0];`）。
- +both：`code_valid=True`，coverage `4/4`，joint success。

CE 契约包含 `a == null` 与 `a.length == 0` 的 `exceptional_behavior`。WybeCoder
在实现里显式抛出对应异常，从而让 `a[0]` 的数组越界义务消失：

```java
int first(int[] a) {
    if (a == null) {
        throw new NullPointerException();
    }
    if (a.length == 0) {
        throw new ArrayIndexOutOfBoundsException();
    }
    return a[0];
}
```

### 3.3 C id 21 `loops/mult.c` —— 恢复溢出常量依赖

- base：joint success（`2/2`）。
- +ce：`code_valid=False`（Frama-C 解析阶段中止）。
- +both：`code_valid=True`，coverage `2/2`，joint success。

CE 前置条件引用了溢出常量：

```c
requires a >= 0;
requires a == 0 || (INT_MIN <= a * b && a * b <= INT_MAX);
```

CE 生成的代码缺少 `#include <limits.h>`，Frama-C 报
`unbound logic variable INT_MAX ... treated as fatal error`；WybeCoder 修复补回了
`#include <limits.h>`，契约与覆盖均保持不变。

> 同类：C id 35 `wp1.c`、43 `diff.c`、45 `add.c`、46 `absolute_value.c`；
> 题目归属相同模式（CE 引入 `INT_MIN/INT_MAX` 约束但代码未引入头文件）。
> Rust 侧对应现象见 id 23 `vec_immutable/Problem023_VecFirst.rs`
> （CE 增加 `ensures *v == *old(v)` → `E0308` 可变性类型错，`+both` 修复后 joint）。

---

## 结论

- **CE 的收益在 coverage**：它能把 ground-truth 目标表达得更完整（分类 2），
  这也是总体 coverage micro 在四语言上一致上升的原因。
- **CE 的代价在 code validity**：更强的 pre/post/loop 义务会引入
  别名、存在量词、析取等更难（甚至超出自动证明器能力）的证明目标（分类 1）。
- **WybeCoder 的价值在于补偿**：在不改动 CE 契约、不牺牲 coverage 的前提下，
  通过实现层的守卫、见证变量、frame/头文件补齐等修复，把 CE 造成的
  validity 损失救回来（分类 3），最终使 `+both` 的 valid 与 joint success
  高于 base 与 `+ce`。

## 备注：Python 的差异

Python/Nagini 的 `base/+ce` 在未经 offline repair 的裸产物上同样呈现
`valid 63→35、coverage .934→.963、joint 61→31` 的下降；但该批产物存在
已知的契约规范化缺陷，`*-offline-repaired` 是修复后的可比结果，此时
CE 反而是净收益（79/76 → 90/85）。因此 Python 的 CLI 结论与
C/Java/Rust 不完全一致，正文因此以 repaired 集为准并单独标注。
