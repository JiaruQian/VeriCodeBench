# python-nagini-problems

Python/Nagini requirement-to-code benchmark dataset.

This is the Python-specific extension of the C/ACSL, Java/JML, and
Rust/Verus benchmark tracks. It follows:

```text
Requirement -> Nagini Contract -> Python Code -> Nagini -> Spec Coverage
```

The set is intentionally Python-oriented rather than a direct port of the
C pointer-heavy problems. It prioritizes typed function contracts,
`Optional`/`None` compatibility, list and dictionary mutation, simple
symbolic-execution-friendly pure functions, and preconditions that rule
out common Python runtime exceptions.

## Problem Set

This dataset contains 100 problems.

Category distribution:

- `dict_apis`: 8
- `dict_apis_ext`: 8
- `exception_freedom`: 4
- `exception_freedom_ext`: 4
- `list_basics`: 10
- `list_basics_ext`: 10
- `list_mutation`: 10
- `list_mutation_ext`: 10
- `optional_none`: 8
- `optional_none_ext`: 8
- `scalar_arithmetic`: 10
- `scalar_arithmetic_ext`: 10

## Layout

- `requirements/requirements_100.json`: natural-language requirements.
- `requirements/requirements_100_ground_truth_specs.json`: curated Nagini ground-truth targets.
- `ground-truth/**/*.py`: reference Python implementations annotated with Nagini contracts.

## Verify Reference Implementations

Use the local Nagini installation:

```bash
./scripts/run_nagini_python_problems.sh
```

The reference contracts include permissions such as `Acc(list_pred(a))`
and `Acc(dict_pred(d))`, because Nagini models Python containers through
explicit predicate permissions. Read-only container element postconditions
use `Old(...)` to state facts about the pre-state element values.

Current reference status in this container:

```text
100 pass / 100 total
```
