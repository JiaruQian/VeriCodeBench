# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from src.env import Dialog, Env, Message


def goedel_initial_prompt(statement: str) -> str:
    # include `sorry` https://huggingface.co/deepseek-ai/DeepSeek-Prover-V2-7B
    assert statement.endswith(":= by"), statement
    # replace last occurrence of "":= by" with ":= by sorry"
    statement = statement.rsplit(":= by", 1)[0] + ":= by sorry"
    return DS_PROVER_INITIAL_PROMPT.format(statement=statement)


def initial_prover_prompt(
    model_name: str,
    statement: str,
    proof: str,
    errors: str,
    allow_subgoal_change: bool,
) -> str:
    if "goedel" in model_name.lower():
        return goedel_initial_prompt(statement)

    # otherwise assume general purpose models:
    # - initial turn will already by error correction on auto proof
    # - include note abpout modifying statement

    if allow_subgoal_change:
        allow_note = "\n\n" + MODIFY_STATEMENT_NOTE
        disallow_note = ""
    else:
        allow_note = ""
        disallow_note = "\n" + NO_MODIFY_STATEMENT_NOTE

    return PROVE_PROMPT.format(
        statement=statement,
        proof=proof,
        errors=errors,
        modify_statement_note=allow_note,
        no_modify_statement_note=disallow_note,
    )


def initial_prover_dialog(
    model_name: str,
    dialog: Dialog,
    statement: str,
    proof: str,
    errors: str,
    allow_subgoal_change: bool,
) -> Dialog:
    """
    Initial prover dialog based on the model name,
    either creating a new dialog or modifying the existing one.
    """
    msg = Message.user(
        initial_prover_prompt(
            model_name=model_name,
            statement=statement,
            proof=proof,
            errors=errors,
            allow_subgoal_change=allow_subgoal_change,
        )
    )
    if "goedel" in model_name.lower():
        return Dialog([msg])
    else:
        dialog.messages.append(msg)
        return dialog


def shrink_goedel_dialog(dialog: Dialog) -> Dialog:
    """
    Shrink a Goedel prover dialog by removing all but the last code blocks from
    the assistant messages
    """
    new_messages = []
    for msg in dialog.messages:
        if msg.role == "assistant":
            code = Env.extract_code(msg.content, last=True)
            new_content = f"```lean4\n{code}\n```"
            new_messages.append(Message.assistant(new_content))
        else:
            new_messages.append(msg)
    return Dialog(new_messages, system_prompt=dialog.system_prompt)


def prover_followup_dialog(
    model_name: str,
    dialog: Dialog,
    turn: int,
    max_turns: int,
    errors: str,
    shrink_threshold_chars: int | None = None,
) -> Dialog:
    """
    Format a follow-up prompt for the prover model based on the model name.
    Shrink the dialog for Goedel models in case they become too long.

    Args:
        model_name (str): The name of the model being used.
        dialog (Dialog): The current dialog history, might be modified in-place.
        turn (int): 1-based number of the current bug fixing iteration.
        max_turns (int): Maximum number of bug fixing iterations allowed.
        errors (str): The error messages to be included in the prompt.
        shrink_threshold_chars (int | None): If set, the character length threshold
            for shrinking Goedel dialogs. If None, no shrinking is performed.
    """
    if "goedel" in model_name.lower():
        msg = GOEDEL_FOLLOWUP_PROMPT.format(turn=turn, errors=errors)
    else:
        # otherwise assume general purpose models:
        msg = PROVER_FOLLOWUP_PROMPT.format(
            turn=turn, max_turns=max_turns, errors=errors
        )

    if "goedel" not in model_name.lower():
        shrink_threshold_chars = None
    shrink_threshold_chars = shrink_threshold_chars or float("inf")
    dialog_chars = sum(len(m.content) for m in dialog.messages) + len(
        dialog.system_prompt or ""
    )
    if dialog_chars > shrink_threshold_chars:
        dialog = shrink_goedel_dialog(dialog)

    dialog.append(Message.user(msg))
    return dialog


# Goedel prover initial prompt template, includes its favorite header
DS_PROVER_INITIAL_PROMPT = """
Complete the following Lean 4 code:

```lean4
import Mathlib
import Aesop

set_option maxHeartbeats 0

open BigOperators Real Nat Topology Rat

{statement}
```

Before producing the Lean 4 code to formally prove the given theorem, provide a detailed proof plan outlining the main proof steps and strategies.
The plan should highlight key ideas, intermediate lemmas, and proof structures that will guide the construction of the final formal proof.
""".strip()


GOEDEL_FOLLOWUP_PROMPT = """
The proof (Round {turn}) is not correct. Following is the compilation error message, where we use <error></error> to signal the position of the error.

{errors}

Before producing the Lean 4 code to formally prove the given theorem, provide a detailed analysis of the error message.
""".strip()


MODIFY_STATEMENT_NOTE = """
NOTE: If the statement has an error, you can change it **slightly** so that the theorem compiles and can be proved.
The goal is to make the parser understand the type whose pretty printing I copied into the theorem statement
(because pretty printing and parsing are not exact inverses in Lean).
In particular, you can make the following adjustments:
- Replacing `{{fst := ..., snd := ...}}` with `MProdWithNames.mk' ... ...`
- Similar for `{{data := }}` and `String.mk`
- Removing `WithName.mk'` and `WithName.erase` (which are defeq to the wrapped object)
- Replacing `↑` cast annotation with explicit `(<expr> : <type>)` casts

Make **minimal** adjustments for the statement to compile.
In particalur, do NOT change the semantics of the statement.
Also, stay as close as possible type-theoretic content of the statement I copied,
e.g. use `MProdWithNames.mk' fst1 snd1 = MProdWithNames.mk' fst2 snd2` not `fst1 = fst2 ∧ snd1 = snd2`
if there is an equality `{{fst := fst1, snd := snd1}} = {{fst := fst2, snd := snd2}}` in the statement I copied.
You will later have to integrate your proof into the main correctness theorem,
so any shortcuts you take here will make the final proof reconstruction very difficult.
""".strip()


NO_MODIFY_STATEMENT_NOTE = """
Do not modify the statement please, a string comparison will be used to check that it wasn't tampered with.
""".strip()


PROVE_PROMPT = """
For proving the correctness of this method, I need to prove the following theorem:
```lean
{statement}
  sorry
```

I automatically ran the following initial attempt:
```lean
{proof}
```

But got the following errors:

{errors}

Can you please provide a complete Lean proof for this theorem by replacing my initial proof attempt?
(You can decide to fix it or discard it and write a new proof from scratch.){no_modify_statement_note}
You can add additional helper lemmas before the theorem if needed.
Do not use `sorry`, `admit`, `axiom` or other incomplete proof steps.

Please return the code of the theorem (and potential helper lemmas) in triple backticks ```lean ... ```.
I will only read the last `lean` code block.{modify_statement_note}

NOTE: It can happen that the goal is not provable as stated (even evidently and trivially, the goal was auto-generated).
In this case, the method implementation or invariant annotations need to be adjusted.
If the theorem is unprovable, please write a few sentences in a block of `--` line comments stating exactly:
- which verification condition (see theorem name) is unprovable,
- a concise account of what it says and why it is unprovable,
- what needs to be changed in the method body or invariant annotations to make it provable.
Then propose a modified `method` body that addresses this problem (outside the comments and keeping the method specification header unchanged).
Do NOT change the theorem statement or prove that it is false but discard this proof obligation
and modify the method body and invariant annotations instead.
This will generate the verification conditions that need to be proved, hopefully resulting in a provable theorem.

In NO CIRCUMSTANCES, add macro rules and notation that change the semantics and circumvent the actual intended
statement. Don't redefine `false` to be `true` or similar tricks but fix the method if the statement is unprovable.

Remember the **imperative code requirements** which are strictly enforced:
the entire asymptotically non-constant-time core must be written with explicit loops and mutable state,
not using higher-order traversals, recursive traversals, or library calls that hide iteration (map, fold, filter, sort, etc.).
Functional style is allowed only for truly O(1) operations (arithmetic, comparisons, tuple ops, single indexing, simple conditionals)
and in ghost/invariant code, not for any real data traversal or reorganization.
In particular, do NOT use functional code that directly mimics the functional specification, which would make verification trivial but
useless for our purposes.
Modify imperative code by adjusting loop condiations, invariants etc., not by cheating your way out of the Loom setup.

NOTE: lemmas without `:= by` are not supported, in particular, `match` cannot be omitted with `|`-style theorems.
""".strip()


PROVER_FOLLOWUP_PROMPT = """
I ran the code but got the following errors (bug fixing iteration {turn} of {max_turns}):
Could you please figure out what went wrong and fix them?
Please return the new code for the block you suggested/edited above, again in triple backticks.

{errors}

NOTE: If the theorem is unprovable, please edit the `method` body instead as explained above.
""".strip()
