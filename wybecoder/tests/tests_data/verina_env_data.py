# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

# Sample task data extracted from verina_at4_part1.jsonl
SAMPLE_TASK = {
    "loom_header": """
import Auto
import Lean
import Mathlib
import Loom.MonadAlgebras.NonDetT.Extract
import Loom.MonadAlgebras.WP.Tactic
import Loom.MonadAlgebras.WP.DoNames'
import CaseStudies.Velvet.Std
import CaseStudies.TestingUtil
open TotalCorrectness DemonicChoice
set_option auto.smt.trust true
set_option auto.smt true
set_option auto.smt.timeout 4
set_option auto.smt.solver.name "cvc5"
set_option maxHeartbeats 400000

method DoubleQuadruple (x : Int) return (result : (Int × Int))
  ensures result.fst = 2 * x ∧ result.snd = 2 * result.fst
  do
    sorry
""".strip(),
    "signature": {
        "name": "DoubleQuadruple",
        "parameters": {"param_name": ["x"], "param_type": ["Int"]},
        "return_type": "(Int × Int)"
    },
    "tests": {
        "input": ["{\"x\": 0}", "{\"x\": 1}"],
        "expected": [["(0, 0)"], ["(2, 4)"]]
    }
}

# Valid implementation
SAMPLE_CODE = """
import Auto
import Lean
import Mathlib
import Loom.MonadAlgebras.NonDetT.Extract
import Loom.MonadAlgebras.WP.Tactic
import Loom.MonadAlgebras.WP.DoNames'
import CaseStudies.Velvet.Std
import CaseStudies.TestingUtil
open TotalCorrectness DemonicChoice
set_option auto.smt.trust true
set_option auto.smt true
set_option auto.smt.timeout 4
set_option auto.smt.solver.name "cvc5"
set_option maxHeartbeats 400000

method DoubleQuadruple (x : Int) return (result : (Int × Int))
  ensures result.fst = 2 * x ∧ result.snd = 2 * result.fst
  do
    let a := 2 * x
    let b := 2 * a
    return (a, b)

prove_correct DoubleQuadruple by
  loom_solve
  trivial
"""

CODE_WITH_AXIOM = """
axiom Bad.Axiom : True

method DoubleQuadruple (x : Int) return (result : (Int × Int))
  ensures result.fst = 2 * x ∧ result.snd = 2 * result.fst
  do
    have : True := Bad.Axiom
    let a := 2 * x
    let b := 2 * a
    return (a, b)

prove_correct DoubleQuadruple by
  loom_solve
  trivial
"""
