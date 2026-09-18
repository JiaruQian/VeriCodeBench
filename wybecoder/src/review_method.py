# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import json
from logging import getLogger
from pathlib import Path

from src.args import RunArgs
from src.env import Dialog, Message, Task
from src.agent import chat
import re

logger = getLogger()


def try_load_json(s: str) -> dict:
    # first try to json.loads directly, if fails then try to extract markdown code block and json.loads again
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        logger.warning(
            f"Failed to parse JSON directly, trying to extract from markdown code block from: {s}"
        )
        # Try to extract JSON from markdown code block
        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", s, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise


def review(
    args: RunArgs,
    task: Task,
    proposed: str,
) -> tuple[bool, str]:
    """
    Use LLM to review whether to merge the proposed new method.
    Returns (accept, reason)
    """

    if not args.imperativeness_judge:
        return True, "Imperativeness judge disabled"

    fn = Path(__file__).parent.parent / args.prompt_path
    with fn.open() as f:
        system = f.read()

    review_dialog = Dialog(
        [
            Message.user(
                REVIEW_PROMPT.format(
                    description=task["description"],
                    proposed=proposed,
                )
            ),
        ],
        system_prompt=system,
    )

    review_msg: Message = chat(review_dialog, args.model, args.temperature)
    try:
        data = try_load_json(review_msg.content)
        verdict_str = str(data.get("verdict", "")).strip().lower()
        reason = str(data.get("reason", "")).strip()
        accept = verdict_str == "accept"
    except Exception:
        logger.warning(
            f"Imperativeness reviewer returned non-JSON; defaulting to REJECT. Raw: {review_msg.content}"
        )
        accept = False
        reason = review_msg.content

    return accept, reason


REVIEW_PROMPT = """
You are a *review assistant* for Velvet/Lean 4 verification tasks.

Your job is to look at a **proposed method implementation** and decide whether it respects the **Imperative Code Requirement** explained above. 

## Examples

### 1. Direct Copy of the Specification in the Body

For counting unique elements in a sorted list, this must be rejected because the method
body just reuses the exact expression from the postcondition (`nums.eraseDups.length`)
instead of implementing an explicit imperative algorithm. The `eraseDups` function is a
non-constant-time (O(n²)) functional operation that performs the core work of the algorithm.

```lean
method removeDuplicates (nums : List Int) return (result : Nat)
  ensures result - nums.eraseDups.length = 0 ∧
    nums.eraseDups.length ≤ result
  do
    let mut res : Nat := 0
    res := nums.eraseDups.length
    return res
```

### 2. Imperative Shell with Functional Inner Computation

For finding the index maximizing a score, this must be rejected because the core work
(`scoreAt i`) is implemented via **functional** traversals (`take`, `drop`, `foldl`),
even though they are wrapped in a loop. These traversals are O(n), so they are
non-constant-time functional work and constitute the main algorithmic cost.

```lean
method bestIndexByScore (xs : List Nat) return (result : Nat)
  ensures
    let scoreAt := fun (i : Nat) =>
      let pref := xs.take (i+1)
      let suff := xs.drop i
      let sumPrefix := pref.foldl (· + ·) 0
      let sumSuffix := suff.foldl (· + ·) 0
      (Int.ofNat sumPrefix - Int.ofNat sumSuffix)
    result < xs.length ∧
    ∀ j, j < xs.length → scoreAt result ≥ scoreAt j
  do
  let n := xs.length
  let mut bestIdx : Nat := 0
  let mut bestScore : Int := Int.ofNat 0
  let mut i : Nat := 0
  while i < n
    -- invariants omitted in this example
  do
    let pref := xs.take (i+1)
    let suff := xs.drop i
    let sumPrefix := pref.foldl (· + ·) 0
    let sumSuffix := suff.foldl (· + ·) 0
    let score : Int := Int.ofNat sumPrefix - Int.ofNat sumSuffix
    if score > bestScore then
      bestScore := score
      bestIdx := i
    i := i + 1
  return bestIdx
```

### 3. Imperative Code with Constant-Time Primitive Operations

For the same "count unique elements" task, this implementation
uses only loops, mutable state, and O(1) operations.

```lean
method countUnique (nums : List Int) return (result : Nat)
  ensures result = nums.eraseDups.length
  do
    let n := nums.length
    let mut count := 0
    let mut i := 0
    while i < n
    do
      let mut seenBefore := false
      let mut j := 0
      while j < i
      do
        if nums[j]! = nums[i]! then
          seenBefore := true
        j := j + 1
      if !seenBefore then
        count := count + 1
      i := i + 1
    return count
```

### 4. Imperative Code with Imperative Inner Computation

**Imperative** subroutines are explicitly allowed:
they can be recognized by their use of `.extract` for retrieving the computed result from
values in the `VelvetM` monad. If their code is not provided, **you can assume them to be
imperative library functions that respect the Imperative Code Requirement**.
Your task is solely to check whether the caller method is imperative.
Sometimes, the core work of the algorithm is delegated to such imperative subroutines,
and this is acceptable.

```lean
method bestIndexByScore (xs : List Nat) return (result : Nat)
  ensures
    let scoreAt := fun (i : Nat) =>
      let pref := xs.take (i+1)
      let suff := xs.drop i
      let sumPrefix := pref.foldl (· + ·) 0
      let sumSuffix := suff.foldl (· + ·) 0
      (Int.ofNat sumPrefix - Int.ofNat sumSuffix)
    result < xs.length ∧
    ∀ j, j < xs.length → scoreAt result ≥ scoreAt j
  do
  let n := xs.length
  let mut bestIdx : Nat := 0
  let mut bestScore : Int := Int.ofNat 0
  let mut i : Nat := 0
  let prefix_sums := (computePrefixSums xs).extract -- imperative subroutine
  let suffix_sums := (computeSuffixSums xs).extract -- imperative subroutine
  while i < n
    -- invariants omitted in this example
  do
    let score := Int.ofNat prefix_sums[i]! - Int.ofNat suffix_sums[i]!
    if score > bestScore then
      bestScore := score
      bestIdx := i
    i := i + 1
  return bestIdx
```

---

### Output format

Respond with a single JSON object of the form:

```json
{{
  "verdict": "accept" | "reject",
  "reason": "<short explanation>"
}}
```

- "verdict" must be either "accept" or "reject".
- "reason" should briefly explain why, focusing on the points above (imperative vs functional, mirroring the spec, complexity of the operations).

### Review case

{description}


Proposed implementation to review:

```lean
{proposed}
```

Now please provide your review in the specified JSON format.
""".strip()


# standard feedback format:
REVIEW_FEEDBACK_PROMPT = """
The proposed method change was rejected for the following reason:

"{reason}"

Please try again to synthesize a new method implementation that addresses the requirements and the reviewer's concerns.
""".strip()
