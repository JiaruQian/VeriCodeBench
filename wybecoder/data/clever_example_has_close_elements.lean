/- Copyright (c) Meta Platforms, Inc. and affiliates.
   All rights reserved.
   This source code is licensed under the license found in the
   LICENSE file in the root directory of this source tree. -/

import Auto
import Aesop
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

#guard ((has_close_elements ([1, 2, 3]: List Rat) 0.5).extract) = false
#guard ((has_close_elements ([1, 2.8, 3, 4, 5, 2]: List Rat) 0.3).extract) = true
