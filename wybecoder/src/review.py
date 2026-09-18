# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from logging import getLogger
from pathlib import Path
import json

from src.data import ProblemContext, AgentResult, Action
from src.env import Dialog, Message
from src.agent import chat
from src.utils import render_diff

logger = getLogger()


def review_merge(
    ctx: ProblemContext,
    res: AgentResult,
) -> tuple[bool, str]:
    """
    Use LLM to review whether to merge the proposed changes.
    Returns (should_merge, reason)

    Calls imperativeness judge for METHOD actions.
    """
    if not ctx.args.merge_review:
        return True, "Auto-merge enabled"

    if res.action not in {Action.ADD, Action.METHOD} and not res.errors:
        # Only review ADD and METHOD actions
        return (
            True,
            f"No review required for successful actions of type {res.action.value}",
        )

    proposed = ctx.current.add_decls(ctx.task, res)
    current_code = ctx.current.render()
    proposed_code = proposed.render()
    res.diff_reviewed = render_diff(current_code, proposed_code)

    # Build the diff description
    if res.action == Action.METHOD:
        current_method = ctx.current.decls[ctx.current.method_idx]
        proposed_method = proposed.decls[proposed.method_idx]
        diff_description = f"""
**Current method implementation:**
```lean
{current_method.render()}
```

**Proposed method implementation:**
```lean
{proposed_method.render()}
```
"""
    elif res.action == Action.ADD:
        new_decls = proposed.decls[proposed.add_idx : -1]  # Exclude correctness theorem
        new_rendered = "\n".join(d.render() for d in new_decls)
        diff_description = f"""
**Proposed new declarations to add:**
```lean
{new_rendered}
```
"""
    elif res.action in {Action.PROVE_CORRECT, Action.DISPROVE}:
        diff_description = f"""
**Current final theorem:**
```lean
{ctx.current.main_theorem.render()}
```

**Proposed final theorem:**
```lean
{proposed.main_theorem.render()}
```
"""
    else:
        raise ValueError(f"Unexpected action type for merge review: {res.action}")

    fn = Path(__file__).parent.parent / "data" / "prompt_multi.md"
    with fn.open() as f:
        system = f.read()

    new_errors = res.errors or ""
    new_errors_str = (
        f"\n\n**New errors after proposed changes:**\n```\n{new_errors}\n```"
        if res.errors
        else ""
    )
    review_dialog = Dialog(
        [
            Message.user(
                MERGE_REVIEW_PROMPT.format(
                    current_errors=ctx.current.errors or "None",
                    current_code=current_code,
                    diff_description=diff_description,
                    proposed_code=proposed_code,
                    new_errors=new_errors_str,
                    diff=res.diff_reviewed,
                )
            ),
        ],
        system_prompt=system,
    )

    review_msg: Message = chat(review_dialog, ctx.args.model, ctx.args.temperature)

    try:
        data = json.loads(review_msg.content)
        verdict_str = str(data.get("verdict", "")).strip().lower()
        reason = str(data.get("reason", "")).strip()
        accept = verdict_str == "accept"
    except Exception:
        logger.warning(
            f"Merge reviewer returned non-JSON; defaulting to ACCEPT. Raw: {review_msg.content}"
        )
        accept = True
        reason = review_msg.content

    return accept, reason


MERGE_REVIEW_PROMPT = """
You are a code review assistant for a Lean 4 proof verification system.
A sub-agent has proposed changes to fix errors in the current proof attempt.

**Current errors:**
```
{current_errors}
```

**Current file state:**
```lean
{current_code}
```

{diff_description}

**Full proposed file after changes:**
```lean
{proposed_code}
```{new_errors}

**Rendered diff:**
```diff
{diff}
```

# Your Task

Review whether these changes should be merged into the main file.
The declarations have been run through Lean to guard for syntax errors,
and to check all proofs.

Consider:
1. **Relevance**: Could the changes help address the current problems?
2. **Complementarity**: Do the changes add useful declarations / knowledge, and are they not redundant with existing contents?
3. **Progress**: Do they represent forward progress on the problem?

**Important**: Be permissive rather than restrictive. Only reject changes if they are clearly problematic, redundant, or counterproductive.

### Output format

Respond with a single JSON object of the form:

```json
{{
  "verdict": "accept" | "reject",
  "reason": "<short explanation>"
}}
```

- "verdict" must be either "accept" or "reject".
- "reason" should briefly explain why.

Now provide your review in the specified JSON format.
""".strip()
