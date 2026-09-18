# Anonymous source release

VeriCodeBench contains benchmark source code, datasets, ground-truth contracts,
evaluation scripts, and documentation for C/Frama-C, Java/OpenJML, Rust/Verus,
and Python/Nagini. It also includes CodeNova, which combines Constraint-Guided
Specification (CGS) with Verifier-Guided Candidate Repair (VGCR).

## Release contents

The release starts with a new Git history attributed to `Anonymous Authors`
(`anonymous@example.invalid`). Original history, remotes, nested Git metadata,
local credentials, caches, experiment outputs, and reference-paper PDFs are
not part of the source snapshot. The case-study documentation refers to
experiments whose generated artifacts are not included in this source release.

The internal `autospec` Python package name is retained for import
compatibility. All method components are implemented within `autospec/`; CGS,
VGCR, and the Constraint Entailment Framework (CEF) are self-contained and do
not import any third-party repair framework.

Third-party license notices, attribution, public dependency links, and standard
tool accounts such as `/home/opam` are retained. They identify upstream
dependencies and native verification toolchains (Frama-C/WP, OpenJML, Verus,
Nagini) rather than the authors of this submission.

## Portable workspace

Run commands from the repository root. Bind-mount the checkout with
`-v "$(pwd)":/workspace` and use `/workspace` inside a container, as shown in
the main README. No author-specific host path is required.

The Dockerfile builds the C environment. Setup guidance for the other language
environments is in `docs/multilanguage_benchmark_plan.md`; pre-existing local
container images and container filesystems are not included in this repository.

Supply API credentials through environment variables. Local `.env` files and
generated `outputs/` are excluded from Git and Docker build contexts.

## Further distribution

A private GitHub repository is the storage source for this release. Its owner
and authenticated push activity are account metadata, so its URL is not an
anonymous submission URL. Use an anonymous distribution service for the review
link. Distribute a Git source archive or the working files without `.git/`;
local `.git/config` necessarily records the private storage remote.
