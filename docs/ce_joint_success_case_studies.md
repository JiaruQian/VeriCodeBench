# CGS Joint Success Case Studies

Based on the Claude run artifacts in each language container, this document selects representative problems from the three configurations Direct, CGS, and CodeNova to illustrate the bidirectional impact of the Constraint-Guided Specification (CGS)-enhanced spec on `code_valid` and `joint_success`.

- Judgment criteria come from `per_problem` in `<run>/reports/benchmark_summary.json`
  (`code_valid`, `requirement_coverage_x/n`, `joint_success`).
- Failure causes come from `verification` in `<run>/reports/results.json` and the same-named `*.verify.log`.
- `joint_success = code_valid && requirement_coverage_x == requirement_coverage_n`.
- Dataset: 100 problems per language. CGS = constraint extraction + spec self-check;
  CodeNova = code repair by Verifier-Guided Candidate Repair (VGCR) on top of the frozen CGS spec.

## Run Directories Used

| Language | Container | Direct | CGS | CodeNova |
| --- | --- | --- | --- | --- |
| C | `Spec` (root `/workspace`) | `outputs/C-base-claude-0706` | `outputs/C-cgs-claude-0706` | `outputs/C-cgs-vgcr-claude-0706` |
| Java | `spec-java` (root `/workspace`) | `outputs/java-base-claude-0706` | `outputs/java-cgs-claude-0707` | `outputs/java-cgs-vgcr-claude-0707` |
| Rust | `spec-rust` | `outputs/rust-base-rust-0707` | `outputs/rust-cgs-claude-0707` | `outputs/rust-cgs-vgcr-claude-0709` |
| Python | `spec-python` | `outputs/python-base-claude-0714` | `outputs/python-cgs-claude-0714` | `outputs/python-cgs-vgcr-claude-0715`\* |

\* For Python, only the `*-offline-repaired` directories of CodeNova have complete evaluation reports, so Python's
CodeNova numbers come from `outputs/python-cgs-vgcr-claude-0715-offline-repaired`;
for comparability, Direct/CGS also use the same-source `*-offline-repaired`.

## Overall Metrics

| Language | Direct (valid/joint/cov) | CGS | CodeNova |
| --- | --- | --- | --- |
| C | 73 / 39 / .749 | 56 / 34 / .768 | 77 / 40 / .768 |
| Java | 90 / 65 / .908 | 82 / 63 / .911 | 97 / 73 / .911 |
| Rust | 72 / 51 / .692 | 71 / 49 / .706 | 98 / 55 / .706 |
| Python (repaired) | 79 / 76 / .937 | 90 / 85 / .963 | 90 / 85 / .963 |

C/Java/Rust show the same pattern: **coverage goes up, valid goes down, joint goes down; CodeNova then raises
valid/joint back up**. Python's repaired set is the exception (see the note at the end).

---

## 1. CGS Breaks Problems That Were Originally Joint Successes (Harder Logic, Not Just Syntax)

Filter: `Direct.joint_success=True`, `CGS.joint_success=False`, `CGS.code_valid=False`,
and the failure comes from proof/verification difficulty rather than parsing or type-syntax errors.

### 1.1 C id 5 `pointers/incr_a_by_b.c` — Aliased frame clause causes proof timeout

- Direct: `code_valid=True`, coverage `2/2`, joint success.
- CGS: coverage is still `2/2`, but `code_valid=False`.

CGS added a frame fact for the read pointer:

```c
ensures *a == \old(*a) + \old(*b);
ensures *b == \old(*b);      // added by CGS
```

The prover needs to show that after `*a = *a + *b;` the contents pointed to by `b` are unchanged,
i.e., it must rule out aliasing between `a` and `b`; consequently the new goal cannot be completed
within the time limit:

```text
[wp] 5 goals scheduled
[wp] [Timeout] typed_incr_a_by_b_ensures_2 (Qed 7ms) (Alt-Ergo 10s)
[wp] Proved goals:   4 / 5   (Timeout: 1)
```

Direct is `4/4`. This is a typical case where "the stronger contract itself is not wrong, but it
makes the proof obligation harder".

### 1.2 Java id 16 `array_extrema/Problem016_ArrayMin.java` — Existential loop invariant is unprovable

- Direct: `code_valid=True`, coverage `5/5`, joint success.
- CGS: coverage is still `5/5`, but `code_valid=False`.

CGS introduced an existential quantifier in the loop invariant:

```java
/*@ loop_invariant (\exists int k; 0 <= k && k < i; a[k] == min) || i == 0;
  @ loop_invariant \forall int k; 0 <= k && k < i; min <= a[k];
  @ loop_assigns min, i;
  @ loop_decreases a.length - i;
  @*/
while (i < a.length) { ... }
```

OpenJML cannot establish preservation of this invariant:

```text
verify: The prover cannot establish an assertion (LoopInvariant) in method min
  @ loop_invariant (\exists int k; 0 <= k && k < i; a[k] == min) || i == 0;
```

Direct's `\exists int k; 0 <= k && k < i; min == a[k]` (without `|| i == 0`) is provable together
with the loop body, whereas CGS's strengthened version is instead unprovable.

### 1.3 Python id 94 `dict_apis_ext/Problem094_DictKeyMapsToSelf.py` — Stronger disjunctive postcondition is unprovable

- Direct: `code_valid=True`, coverage `4/4`, joint success.
- CGS: coverage is still `4/4`, but `code_valid=False`.

CGS appended a length disjunction clause:

```python
Ensures(key in d)
Ensures(len(d) == Old(len(d)) or (key not in Old(d) and len(d) == Old(len(d)) + 1))  # added by CGS
Ensures(d[key] == key)
```

Nagini cannot prove this disjunction for the same implementation:

```text
Postcondition of dict_key_maps_to_self might not hold.
Assertion ((len(d) == Old(len(d))) or
          ((key not in Old(d)) and (len(d) == (Old(len(d)) + 1)))) might not hold.
```

Direct only requires `key in d` and `d[key] == key`, so it passes; after CGS strengthening, code
validity is lost.

> Similar case (as a supplement): Java id 3 `array_basics/Problem003_FirstElement.java`
> because CGS adds `normal_behavior` + two `exceptional_behavior` clauses and an array frame fact,
> making `return a[0];` trigger `PossiblyTooLargeIndex`.

---

## 2. CGS Directly Fixes Coverage, Thereby Achieving Joint Success

Filter: `Direct.code_valid=True` but coverage is not full (`joint_success=False`),
`CGS.code_valid=True` and coverage is completed (`joint_success=True`). That is, CGS supplies the
contract goals that ground truth missed but the Direct spec did not express.

### 2.1 C id 13 `more_arrays/equal_arrays.c` — Refined from a "two-condition" form into per-behavior contracts

- Direct: coverage `4/6`, not joint.
- CGS: coverage `6/6`, joint success.

Direct only gives a single biconditional:

```c
ensures \result == 1 <==> (\forall integer i; 0 <= i < n ==> a[i] == b[i]);
ensures \result == 0 || \result == 1;
```

CGS explicitly splits it into two behaviors that match the coverage targets:

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

The coverage count rises from 4/6 to 6/6 while remaining verifiable.

### 2.2 Rust id 36 `vec_mutation/Problem036_VecPop.rs` — Sequence effect split into length + pointwise frame

- Direct: coverage `2/3`, not joint.
- CGS: coverage `3/3`, joint success.

Direct expresses the whole sequence effect with a single subrange fact:

```rust
ensures v@ == old(v)@.subrange(0, old(v).len() as int - 1)
```

CGS splits it into two independently checkable units, "length change + pointwise equality":

```rust
ensures v.len() == old(v).len() - 1
ensures forall|i: int| 0 <= i < v.len() ==> v[i] == old(v)[i]
```

The coverage checker requires a sequence effect to have all three kinds of facts — length, changed
elements, and unchanged regions; Direct's combined formulation counts as only partial coverage
(2/3), while CGS's split formulation completes it to 3/3.

### 2.3 Python id 57 `scalar_arithmetic_ext/Problem057_ChooseIf.py` — Fills in the other branch

- Direct: coverage `1/2`, not joint.
- CGS: coverage `2/2`, joint success.

Direct only constrains the branch where `flag` is true:

```python
Ensures(Implies(flag, Result() == x))
```

CGS adds the complementary branch:

```python
Ensures(Implies(flag, Result() == x))
Ensures(Implies(not flag, Result() == y))
```

Coverage 1/2 → 2/2, joint success.

> As a supplement: Java id 49 `scalar_arithmetic/Problem049_SameSignNonzero.java`
> expands `\result <==> ((x > 0) == (y > 0))` into
> `\result == ((x > 0 && y > 0) || (x < 0 && y < 0))`, coverage 2/3 → 3/3.

---

## 3. CGS Alone Breaks Passing Problems, and CodeNova Fixes Them Back

Filter: `Direct.joint_success=True`, `CGS.joint_success=False`, `CodeNova.joint_success=True`
(and coverage stays consistent). This shows the compensating value of VGCR repair when "a stronger
spec makes the code harder to write".

### 3.1 Java id 16 `array_extrema/Problem016_ArrayMin.java` — Replacing the existential quantifier with a witness variable

- Direct: joint success (`5/5`).
- CGS: `code_valid=False` (existential loop invariant unprovable, see 1.2).
- CodeNova: `code_valid=True`, coverage `5/5`, joint success.

VGCR does not weaken the contract; instead it introduces an explicit witness variable `minIdx` in
the implementation, replacing the unprovable existential quantifier with a concrete equality:

```java
int min = a[0];
int minIdx = 0;                 // new witness
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

### 3.2 Java id 3 `array_basics/Problem003_FirstElement.java` — Adding precondition guards to make the index obligation provable

- Direct: joint success (`4/4`).
- CGS: `code_valid=False` (`PossiblyTooLargeIndex` at `return a[0];`).
- CodeNova: `code_valid=True`, coverage `4/4`, joint success.

The CGS contract includes `exceptional_behavior` for `a == null` and `a.length == 0`. VGCR
explicitly throws the corresponding exceptions in the implementation, so the array-out-of-bounds
obligation for `a[0]` disappears:

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

### 3.3 C id 21 `loops/mult.c` — Restoring the overflow-constant dependency

- Direct: joint success (`2/2`).
- CGS: `code_valid=False` (Frama-C parsing phase aborts).
- CodeNova: `code_valid=True`, coverage `2/2`, joint success.

The CGS precondition references overflow constants:

```c
requires a >= 0;
requires a == 0 || (INT_MIN <= a * b && a * b <= INT_MAX);
```

The CGS-generated code lacks `#include <limits.h>`, and Frama-C reports
`unbound logic variable INT_MAX ... treated as fatal error`; the VGCR repair restores
`#include <limits.h>`, keeping both the contract and coverage unchanged.

> Similar: C id 35 `wp1.c`, 43 `diff.c`, 45 `add.c`, 46 `absolute_value.c`;
> these problems follow the same pattern (CGS introduces `INT_MIN/INT_MAX` constraints but the code does not include the header).
> The corresponding Rust phenomenon is id 23 `vec_immutable/Problem023_VecFirst.rs`
> (CGS adds `ensures *v == *old(v)` → `E0308` mutability type error; CodeNova repairs it to become joint).

---

## Conclusion

- **CGS's benefit is in coverage**: it can express ground-truth goals more completely (category 2),
  which is also why the overall coverage micro consistently rises across the four languages.
- **CGS's cost is in code validity**: stronger pre/post/loop obligations introduce harder proof
  goals such as aliasing, existential quantifiers, and disjunctions (even beyond the capability of
  automatic provers) (category 1).
- **VGCR's value is compensation**: without changing the CGS contract or sacrificing coverage, it
  rescues the validity loss caused by CGS (category 3) through implementation-level guards, witness
  variables, and frame/header fixes, ultimately making CodeNova's valid and joint success higher
  than Direct and CGS.

## Note: The Python Difference

Python/Nagini's `Direct/CGS` also shows on the raw artifacts without offline repair a decline of
`valid 63→35, coverage .934→.963, joint 61→31`; but that batch of artifacts has a known
contract-normalization defect, and `*-offline-repaired` is the repaired, comparable result, in
which CGS is instead a net benefit (79/76 → 90/85). Therefore Python's CLI conclusion is not fully
consistent with C/Java/Rust, so the main text uses the repaired set and marks it separately.
