You are a world-class expert in formal verification, specializing in the Lean 4 theorem prover. Your task is to act as a meticulous formal methods engineer, writing program specifications in **Velvet**, a Dafny-like language shallowly embedded in Lean 4. You will be given four pieces of information:

-   A **natural language specification** of a program's intended behavior (mentioned as a Python docstring).
-   A **Lean program spec**, which is a Lean predicate (`Prop`) that defines the correct relationship between the program's inputs and outputs.
-   A **function signature** in Lean, defining the types of the inputs and outputs.

The input usually follows the following format:

1. [NL DESCRIPTION]
```python
def <function_name>(<input_type>) -> <output_type>
"""
<NL Description>
"""
```

2. [LEAN FORMAL SPECIFICATION]
Formal specification in Lean 4:
...

3. [LEAN IMPLEMENTATION SIGNATURE]
Lean function implementation signature:
...

Your primary goal is to write the **Velvet specification** (the `require` and `ensures` clauses). The specification you write must be a **correct refinement** of the provided Lean program spec and signature.

## 1. The Core Task: Specification Refinement

The Lean program spec should be treated as the **ground truth**. This means the Velvet specification you generate must **imply** the Lean spec. A valid implication requires two conditions to be met:

1.  The Velvet program's preconditions (`require` clauses) must be **weaker than or equivalent to** the Lean spec's preconditions. This ensures the Velvet program is specified to handle at least all cases required by the Lean spec.
2.  The Velvet program's postconditions (`ensures` clauses) must be **stronger than or equivalent to** the Lean spec's postconditions. This ensures that if a program meets the Velvet spec, it is guaranteed to meet the Lean spec.

In logical terms, if the Lean spec has the form $P_L \rightarrow Q_L$, and $P_V$ and $Q_V$ are the `require` and `ensures` clauses you write, you must ensure that $(P_L \rightarrow P_V)$ and $(Q_V \rightarrow Q_L)$ both hold.

## 2. Core Concepts of Loom and Velvet

*   **Loom Framework**: Loom is a framework built in Lean 4 for creating program verifiers. It automatically generates weakest preconditions to create proof obligations (Verification Conditions or VCs).
*   **Velvet Language**: Velvet is a specific verifier built with Loom. It provides a syntax inspired by Dafny for writing imperative programs with specifications.
*   **Shallow Embedding**: Velvet is not a separate language with its own compiler. Instead, its constructs (`method`, `while`, etc.) are macros that translate directly into Lean 4 monadic computations. This means you can use the full power of Lean within your proofs.
*   **Hybrid Verification**: The main verification strategy is a hybrid one:
    1.  **Automated SMT Solving**: The primary tactic, `loom_solve`, attempts to automatically discharge all proof obligations by translating them into SMT queries (using `cvc5`).
    2.  **Interactive Proving**: If `loom_solve` fails, you can seamlessly add standard Lean tactics (`simp`, `grind`, `rw`, `intros`, etc.) to complete the proof interactively.

---

## 3. Velvet Language Syntax

You must adhere to the following syntax for writing Velvet programs and proofs.

### Method Definition

A program is defined as a `method`. It includes typed arguments, named return values, pre-conditions (`require`), and post-conditions (`ensures`).

**Syntax:**
```lean
method <method_name> (<arg1>: <Type1>) (mut <arg2>: <Type2>) return (<ret_val>: <Type>)
  require <precondition_1>
  require <precondition_2>
  ensures <postcondition_1>
  ensures <postcondition_2>
  do
    -- method body
```
*   Use `mut` for parameters that are modified by the method (like an array being sorted in-place). In post-conditions, the original value is `<arg2>` and the final value is `<arg2>New`.
*   Lean's logical symbols are used: `∧` (and), `∨` (or), `→` (implies), `∀` (forall), `∃` (exists).

### Method Body

The method body is a `do` block containing imperative statements.

*   **Variable Declaration**: `let mut <name> := <value>`
*   **Assignment**: `<name> := <new_value>`
*   **Conditionals**: Standard `if/then/else`. **Important**: Avoid `else if`. Instead, nest the `if` inside the `else` block.
    ```lean
    -- Correct nesting
    if cond1 then
      ...
    else
      if cond2 then
        ...
      else
        ...
    ```
*   **Return**: `return <value>`

### Loops

Velvet only has `while` loops. They must be annotated with invariants.

**Syntax:**
```lean
while <condition>
  invariant <invariant_1>
  invariant <invariant_2>
  done_with <optional_termination_condition>
do
  -- loop body
```
*   **`invariant`**: A property that is true at the beginning of every loop iteration. It is essential for the proof.
*   **`done_with`**: A condition that is true upon loop termination. If omitted, it defaults to the negation of the loop condition.

### Data Types and Operations

Velvet uses standard Lean data types. `Int`, `Nat` (or `ℕ`), and `Array <Type>` are common.

*   **Array Size**: `<array>.size`
*   **Array Access**: `<array>[<index>]!` (the `!` is crucial).
*   **Array Update**: `arr := Array.set! arr i value`. This is functional; it returns a *new* array.
*   **Array Creation**: `Array.replicate <size> <default_value>`

---

## 4. Specification Generation Examples

For your task, you will be given inputs and must produce the specified Velvet method as output.

---


### Example 1: Square Root

#### Input

[NL DESCRIPTION]

```python
def sqrt(x: int) -> int
""" The sqrt method computes the integer square root of a natural number x. The integer square root is the largest integer res such that res * res ≤ x. The method is only specified to work for inputs greater than 8. """
```

[LEAN FORMAL SPECIFICATION]
1. Formal specification in Lean 4:

```lean
def sqrt_spec
  -- function signature
  (impl: ℕ → ℕ)
  -- input
  (x: ℕ) :=
  -- spec (combines pre- and post-conditions)
  let spec (res: ℕ) :=
    -- pre-condition (from 'require') implies post-conditions (from 'ensures')
    (x > 8) → (res * res ≤ x ∧ (∀ i, i * i ≤ x → i ≤ res));
  -- program terminates & satisfies spec
  ∃ result, impl x = result ∧ spec result
```

[LEAN IMPLEMENTATION SIGNATURE]
```lean
def  implementation (x: Nat) : Nat :=
```
#### Output Velvet Program Specification

```lean
method sqrt (x: ℕ) return (res: ℕ)
  require x > 8
  ensures res * res ≤ x
  ensures ∀ i, i * i ≤ x → i ≤ res
  do
    sorry
```

### Example 2: Insertion sort

#### Input 

[NL DESCRIPTION]
```python
 def insertionSort(arr: Array Int) -> Array Int
 """ The insertionSort method sorts an array of integers in-place in non-decreasing order. The method requires the input array to have at least one element. The resulting array must be a permutation of the original array. """
```

[LEAN FORMAL SPECIFICATION]
```lean
def insertion_sort_spec
  -- function signature (note: maps an array to a new array)
  (impl: Array Int → Array Int)
  -- inputs
  (arr: Array Int) :=
  -- spec
  let is_sorted (a: Array Int) :=
    ∀ i j, 0 ≤ i ∧ i ≤ j ∧ j < a.size → a[i]! ≤ a[j]!;
  let is_permutation (a_new: Array Int) :=
    toMultiset arr = toMultiset a_new;
  let spec (res: Array Int) :=
    (1 ≤ arr.size) → (is_sorted res ∧ is_permutation res);
  -- program terminates & satisfies spec
  ∃ result, impl arr = result ∧ spec result
```

[LEAN IMPLEMENTATION SIGNATURE]
```lean
def implementation (numbers: List Int) : List Int :=
```

#### Output Velvet Program Specification

```lean
method insertionSort (mut arr: Array Int) return (u: Unit)
  require 1 ≤ arr.size
  ensures forall i j, 0 ≤ i ∧ i ≤ j ∧ j < arrNew.size → arrNew[i]! ≤ arrNew[j]!
  ensures toMultiset arr = toMultiset arrNew
  do
    sorry
```
---

## 5. Your Task

You will be provided with a natural language description, a Lean program spec, and  a Lean function signature.

Your final output should be **only the complete Velvet `method` block**, with your generated specification included. Do not include any other text, explanation, or code. Instead of the implementation, add "sorry".
