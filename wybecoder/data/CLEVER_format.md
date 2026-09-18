
This file documents the JSONL schema produced by the CLEVER extractor (`data/clever.jsonl`). Each line is a JSON object with the following fields:

- id (string): filename without the `.lean` extension, e.g. `id_4_mean_absolute_deviation`.
- description (string): cleaned natural-language description from the Natural Language Description block (inner text of `/ - -/`).
- loom_header (string): the Imports benchmark block content (imports, opens, set_option lines).
- tags (array[string]): tokens extracted from the Tags benchmark block (whitespace-delimited).
- metadata (object): mapping of metadata block name → raw block content (strings), e.g. `{"Reviewer Comments": "...", "CLEVER Original": "..."}`.

The extractor writes one object per transformed `.lean` file, ready for downstream ingestion.
