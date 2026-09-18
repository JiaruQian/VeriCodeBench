# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

# Real task data from data/mantas/clever_0.lean
# We manually supply the #guard statements in the 'tests' field
SAMPLE_TASK = {
    "loom_header": """
import Auto
import Lean
import Mathlib

import CaseStudies.Velvet.Std
import CaseStudies.TestingUtil

set_option loom.semantics.termination "total"
set_option loom.semantics.choice "demonic"
set_option loom.solver "cvc5"
set_option auto.smt.timeout 3
set_option maxHeartbeats 100000
set_option auto.smt.trust true


method has_close_elements (numbers: List ℚ) (threshold: ℚ) return (res: Bool)
  require numbers.length > 1
  ensures res ↔ (∃ i j, i < numbers.length ∧ j < numbers.length ∧ i ≠ j ∧ abs (numbers[i]! - numbers[j]!) < threshold)
  do
    sorry
""".strip(),
    "signature": {
        "name": "has_close_elements",
        "parameters": {"param_name": ["numbers", "threshold"], "param_type": ["List ℚ", "ℚ"]},
        "return_type": "Bool"
    },
    # Manually supplied #guard statements
    "tests": """
#guard (has_close_elements [1.0, 2.0, 3.0] 0.5).extract == false
#guard (has_close_elements [1.0, 2.8, 3.0, 4.0, 5.0, 2.0] 0.3).extract == true
""".strip()
}

# Valid implementation from data/mantas/clever_0.lean
SAMPLE_CODE = """
import Auto
import Lean
import Mathlib

import CaseStudies.Velvet.Std
import CaseStudies.TestingUtil

set_option loom.semantics.termination "total"
set_option loom.semantics.choice "demonic"
set_option loom.solver "cvc5"
set_option auto.smt.timeout 3
set_option maxHeartbeats 100000
set_option auto.smt.trust true


method has_close_elements (numbers: List ℚ) (threshold: ℚ) return (res: Bool)
  require numbers.length > 1
  ensures res ↔ (∃ i j, i < numbers.length ∧ j < numbers.length ∧ i ≠ j ∧ abs (numbers[i]! - numbers[j]!) < threshold)
  do
    let n := numbers.length
    let mut i : Nat := 0
    let mut found : Bool := false
    -- Outer loop scans the first index i
    while i < n ∧ ¬found
      invariant 0 ≤ i ∧ i ≤ n
      -- found reflects existence of a close pair whose first index is in the scanned prefix [0, i)
      invariant found ↔ (∃ u v, u < i ∧ v < n ∧ u < v ∧ abs (numbers[u]! - numbers[v]!) < threshold)
      decreasing n - i
    do
      let mut j : Nat := i + 1
      -- Inner loop scans the second index j for fixed i
      while j < n ∧ ¬found
        invariant i < n
        invariant i + 1 ≤ j ∧ j ≤ n
        -- Invariant: found is true iff either it was already found among u<i,
        -- or there exists v in [i+1, j) close to i.
        invariant found ↔ ((∃ v, i < v ∧ v < j ∧ abs (numbers[i]! - numbers[v]!) < threshold) ∨
                           (∃ u v, u < i ∧ v < n ∧ u < v ∧ abs (numbers[u]! - numbers[v]!) < threshold))
        decreasing n - j
      do
        if abs (numbers[i]! - numbers[j]!) < threshold then
          found := true
        j := j + 1
      i := i + 1
    return found

-- Helper lemma: symmetry of absolute difference over rationals
lemma abs_sub_comm_rat (x y : ℚ) : abs (x - y) = abs (y - x) := by
  -- abs (-(x - y)) = abs (x - y), and -(x - y) = y - x
  have h : abs (y - x) = abs (x - y) := by
    simpa [neg_sub] using abs_neg (x - y)
  simpa using h.symm

-- If there exists a close pair with i ≠ j, then there exists one with i < j (and vice versa).
lemma exists_ne_iff_exists_lt_close (numbers : List ℚ) (threshold : ℚ) :
  (∃ i j, i < numbers.length ∧ j < numbers.length ∧ i ≠ j ∧ abs (numbers[i]! - numbers[j]!) < threshold)
  ↔
  (∃ i j, i < numbers.length ∧ j < numbers.length ∧ i < j ∧ abs (numbers[i]! - numbers[j]!) < threshold) := by
  constructor
  · intro h
    rcases h with ⟨i, j, hi, hj, hne, habs⟩
    have : i < j ∨ j < i := lt_or_gt_of_ne hne
    cases this with
    | inl hij =>
      exact ⟨i, j, hi, hj, hij, habs⟩
    | inr hji =>
      -- swap indices using symmetry of abs difference
      have habs' : abs (numbers[j]! - numbers[i]!) < threshold := by
        -- rewrite using symmetry abs (a-b) = abs (b-a)
        simpa [abs_sub_comm_rat] using habs
      exact ⟨j, i, hj, hi, hji, habs'⟩
  · intro h
    rcases h with ⟨i, j, hi, hj, hij, habs⟩
    have hne : i ≠ j := ne_of_lt hij
    exact ⟨i, j, hi, hj, hne, habs⟩

-- Make the equivalence available to the SMT solver to rewrite the postcondition shape
attribute [local solverHint] exists_ne_iff_exists_lt_close
attribute [local solverHint] abs_sub_comm_rat

-- Prove correctness of the method, giving the solver a bit more time and adding grind for quantifiers
set_option maxHeartbeats 400000 in
set_option auto.smt.timeout 6 in
prove_correct has_close_elements by
  loom_solve <;> grind
"""

# Invalid implementation with axioms from data/mantas/clever_0_axiom.lean
SAMPLE_CODE_AXIOM = """
import Auto
import Lean
import Mathlib

import CaseStudies.Velvet.Std
import CaseStudies.TestingUtil

set_option loom.semantics.termination "total"
set_option loom.semantics.choice "demonic"
set_option loom.solver "cvc5"
set_option auto.smt.timeout 3
set_option maxHeartbeats 100000
set_option auto.smt.trust true


method has_close_elements (numbers: List ℚ) (threshold: ℚ) return (res: Bool)
  require numbers.length > 1
  ensures res ↔ (∃ i j, i < numbers.length ∧ j < numbers.length ∧ i ≠ j ∧ abs (numbers[i]! - numbers[j]!) < threshold)
  do
    let n := numbers.length
    let mut i : Nat := 0
    let mut found : Bool := false
    -- Outer loop scans the first index i
    while i < n ∧ ¬found
      invariant 0 ≤ i ∧ i ≤ n
      -- found reflects existence of a close pair whose first index is in the scanned prefix [0, i)
      invariant found ↔ (∃ u v, u < i ∧ v < n ∧ u < v ∧ abs (numbers[u]! - numbers[v]!) < threshold)
      decreasing n - i
    do
      let mut j : Nat := i + 1
      -- Inner loop scans the second index j for fixed i
      while j < n ∧ ¬found
        invariant i < n
        invariant i + 1 ≤ j ∧ j ≤ n
        -- Invariant: found is true iff either it was already found among u<i,
        -- or there exists v in [i+1, j) close to i.
        invariant found ↔ ((∃ v, i < v ∧ v < j ∧ abs (numbers[i]! - numbers[v]!) < threshold) ∨
                           (∃ u v, u < i ∧ v < n ∧ u < v ∧ abs (numbers[u]! - numbers[v]!) < threshold))
        decreasing n - j
      do
        if abs (numbers[i]! - numbers[j]!) < threshold then
          found := true
        j := j + 1
      i := i + 1
    return found
  
axiom _false_1 (numbers : List ℚ) (threshold : ℚ) : Prop

axiom _false_2 (numbers : List ℚ) (threshold : ℚ) : False

prove_correct has_close_elements by
  exfalso
  exact _false_2 numbers threshold
"""
