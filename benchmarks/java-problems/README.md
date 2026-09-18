# java-problems

Java/OpenJML requirement-to-code benchmark dataset.

This is the first Java-specific extension of the C/ACSL benchmark. It follows:

```text
Requirement -> JML Spec -> Java Code -> OpenJML -> Spec Coverage
```

The set intentionally is not a one-to-one port of the C pointer-heavy problems.
It prioritizes arrays, loops, search, maximum/minimum, sortedness, mutation
frames, nullability, object invariants, and exception behavior.

## Problem Set

This dataset contains 100 problems. Every reference implementation
in `ground-truth/` is expected to pass OpenJML ESC in the Java/OpenJML container.

Category distribution:

- `array_basics`: 5
- `array_extra`: 16
- `array_extrema`: 2
- `array_ordering`: 2
- `array_predicates`: 2
- `array_search`: 3
- `boolean_logic`: 8
- `exceptions`: 12
- `loop_arithmetic`: 2
- `mutable_arrays`: 8
- `nullability`: 1
- `object_frames`: 4
- `object_invariants`: 3
- `scalar_arithmetic`: 24
- `strings_chars`: 8

## Layout

- `requirements/requirements_100.json`: natural-language requirements.
- `requirements/requirements_100_ground_truth_specs.json`: curated JML ground-truth targets.
- `requirements/requirements_44*.json`: legacy 44-problem subset retained for reproducibility.
- `ground-truth/**/*.java`: reference Java implementations annotated with JML.

## Verify Reference Implementations

Use the local OpenJML installation:

```bash
./scripts/run_openjml_java_problems.sh
```

On arm64, OpenJML ESC needs an explicit solver:

```bash
OPENJML_SOLVER=/usr/bin/z3 ./scripts/run_openjml_java_problems.sh
```

Current reference status in this container with `OPENJML_SOLVER=/usr/bin/z3`:

```text
100 pass / 100 total
```
