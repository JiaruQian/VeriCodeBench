# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from logging import getLogger

from src.env import (
    Env,
    Task,
    Dialog,
    Message,
    STARTER,
)


logger = getLogger()


class CleverSpecEnv(Env):
    @classmethod
    def initial(cls, task: Task) -> Dialog:
        system = cls.get_system_prompt(task)
        user = INITIAL.format(**(task | {"starter": STARTER}))
        return Dialog([Message.user(user)], system)

    @classmethod
    def evaluate(
        cls,
        task: Task,
        code: str,
        diagnostics: dict,
        goedel_format: bool = False,
        start_line: str | None = None,
    ) -> tuple[bool, str | None]:
        return super()._evaluate(
            diagnostics,
            allow_sorry=True,
            goedel_format=goedel_format,
            start_line=start_line,
        )


INITIAL = """
Please help me obtain the Velvet specification from the given natural language description, lean specification and lean implementation signature.

1. [NL DESCRIPTION]

```python
{problem_spec_nl}
```

2. [LEAN FORMAL SPECIFICATION]

Formal specification in Lean 4:

```lean
{problem_spec_formal_ground_truth}
```

3. [LEAN IMPLEMENTATION SIGNATURE]

Lean function implementation signature:

```lean
{implementation_signature}
```

Please return your code in triple backticks ```lean ... ``` so that I can copy it into a file.
I will only read the last `lean` code block and not perform any other actions in the source directory.
You can start like this:
```lean
{starter}
```
In your solution, please do not include anything else besides the imports, set options and the Velvet method specification with require and ensures. Do not attempt to implement the method. Do not include any other text, explanation, or code. Make sure that you include `do sorry` as a temporary placeholder for the missing proof. Do not include `prove_correct` in your answer.
""".strip()
