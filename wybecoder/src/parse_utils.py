# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import regex

from src.utils import normalize_empty_lines


DECL_KEYWORDS = [
    "theorem",
    "lemma",
    "prove_correct",
    "method",
    "def",
    "example",
    "structure",
    "inductive",
]

MODIFIERS = [
    "public",
    "private",
    "protected",
    "noncomputable",
    "unsafe",
    "partial",
    "nonrec",
]

MODIFIER_ALT = "|".join(map(regex.escape, MODIFIERS))
KEYWORD_ALT = "|".join(map(regex.escape, DECL_KEYWORDS))

# ---------------------------------------------------------------------------
# Unified "decl header" regex (fixed order, single attribute block, blank lines allowed)
#
# Intuition:
#   - We allow any number of blank lines, spaces, or tabs between declaration parts.
#   - Declaration parts must appear in the following order:
#       1. Zero or more `set_option ... ... in` lines
#       2. At most one `@[ ... ]` attribute block
#       3. Zero or more modifiers (public/private/...)
#       4. A keyword from DECL_KEYWORDS
#
#   This handles:
#       set_option ... in
#       set_option ... in set_option ... in
#       @[simp]
#       private noncomputable
#       theorem foo : ...
#       (with any amount of blank lines or whitespace between parts)
#
#   Example matches:
#       set_option ... in
#       set_option ... in
#       @[simp]
#       private
#       noncomputable
#       theorem foo : ...
#
#   and so on, as long as the order is preserved and there is at most one attribute block.
# ---------------------------------------------------------------------------

DECL_HEADER_RE = regex.compile(
    rf"""
    (?P<header>
        ^[ \t]*                                  # indentation at start of header

        # --- set_option* (each may end in arbitrary whitespace) ---
        (?:
            set_option[ \t]+\S+[ \t]+\S+[ \t]+in
            [ \t\n]*                              # trailing whitespace/newlines
        )*

        # --- attribute* ---
        (?:
            @\[[^\]]*\]
            [ \t\n]*                              # trailing whitespace/newlines
        )*

        # --- modifier* ---
        (?:
            (?:{MODIFIER_ALT})\b
            [ \t\n]*                              # trailing whitespace/newlines
        )*

        # --- keyword (the declaration keyword) ---
        (?P<kw>{KEYWORD_ALT})\b
    )
    """,
    regex.MULTILINE | regex.VERBOSE,
)


def theorem_type(code: str) -> str | None:
    """
    Determine if a block starts with a declaration whose keyword is
    'theorem', 'lemma', or 'prove_correct'. Returns that keyword or None.
    Uses the unified DECL_HEADER_RE.
    """
    try:
        m = DECL_HEADER_RE.search(code, timeout=1.0)
    except TimeoutError:
        return None
    if not m:
        return None
    kw = m.group("kw")
    if kw in ("theorem", "lemma", "prove_correct"):
        return kw
    return None


def _parse_theorem(code: str, delimiter: str = r":=\s+by") -> dict[str, str] | None:
    """
    Parses a theorem/lemma string using a user-provided delimiter regex.

    - 'metadata' : any preceding set_option commands and attribute annotations
    - 'statement': modifiers (if any) + theorem/lemma ... up to and including the proof delimiter
    - 'proof'    : everything after the delimiter

    Returns a dictionary or None if parsing fails.
    """

    pattern_string = rf"""
        ^
        [ \t]*                                      # leading indentation (ignored)
        # options: set_option*
        (?P<options>
            (?:
                [ \t]*set_option[ \t]+\S+[ \t]+\S+[ \t]+in
                [ \t\n]*
            )*
        )
        # attributes: attribute*
        (?P<attributes>
            (?:
                [ \t]*@\[[^\]]*\]
                [ \t\n]*
            )*
        )
        # statement = modifiers (if any) + theorem/lemma ... delimiter
        (?P<statement>
            # modifier*
            (?:
                [ \t]*(?:{MODIFIER_ALT})\b
                [ \t\n]*
            )*
            # keyword
            (?:\btheorem\b|\blemma\b)
            # everything up to the proof delimiter (non-greedy)
            [\s\S]*?
            {delimiter}
        )
        (?P<proof>[\s\S]*)
    """
    theorem_parser_pattern = regex.compile(
        pattern_string,
        regex.DOTALL | regex.VERBOSE | regex.MULTILINE,
    )
    try:
        match = theorem_parser_pattern.search(code, timeout=1.0)
    except TimeoutError:
        return None
    if not match:
        return None

    options = match.group("options") or ""
    attributes = match.group("attributes") or ""
    statement = match.group("statement") or ""
    proof = match.group("proof") or ""

    metadata = f"{options}{attributes}"

    try:
        name_match = regex.search(
            r"(?:\btheorem\b|\blemma\b)\s+(\S+)",
            statement,
            timeout=1.0,
        )
        name = name_match.group(1) if name_match else ""
    except TimeoutError:
        name = ""

    return {
        "name": name.strip(),
        "metadata": metadata.strip(),
        "statement": statement.strip(),
        "proof": proof.rstrip().lstrip("\n"),
    }


def _parse_prove_correct(code: str, delimiter: str = r"by") -> dict[str, str] | None:
    """
    Parses a prove_correct string using a user-provided delimiter regex.
    - 'metadata' : any preceding set_option commands and attribute annotations
    - 'statement': from the first modifier/`prove_correct` up to and including the proof delimiter
    - 'proof'    : everything after the delimiter
    Returns a dictionary or None if parsing fails.
    """
    pattern_string = rf"""
        ^
        [ \t]*                                      # leading indentation
        # options: set_option*
        (?P<options>
            (?:
                [ \t]*set_option[ \t]+\S+[ \t]+\S+[ \t]+in
                [ \t\n]*
            )*
        )
        # attributes: attribute*
        (?P<attributes>
            (?:
                [ \t]*@\[[^\]]*\]
                [ \t\n]*
            )*
        )
        # statement = modifiers (if any) + prove_correct ... delimiter
        (?P<statement>
            # modifier*
            (?:
                [ \t]*(?:{MODIFIER_ALT})\b
                [ \t\n]*
            )*
            # keyword
            \bprove_correct\b
            [\s\S]*?
            {delimiter}
        )
        (?P<proof>[\s\S]*)
    """
    parser_pattern = regex.compile(
        pattern_string,
        regex.DOTALL | regex.VERBOSE | regex.MULTILINE,
    )
    try:
        match = parser_pattern.search(code, timeout=1.0)
    except TimeoutError:
        return None
    if not match:
        return None
    options = match.group("options") or ""
    attributes = match.group("attributes") or ""
    statement = match.group("statement") or ""
    proof = match.group("proof") or ""
    # Combine options + attributes into "metadata"
    metadata = f"{options}{attributes}"
    # Extract the name from the statement
    try:
        name_match = regex.search(
            r"\bprove_correct\b\s+(\S+)",
            statement,
            timeout=1.0,
        )
        name = name_match.group(1) if name_match else ""
    except TimeoutError:
        name = ""
    return {
        "name": name.strip(),
        "metadata": metadata.strip(),
        "statement": statement.strip(),
        "proof": proof.rstrip().lstrip("\n"),
    }


def parse_theorem(code: str) -> dict[str, str] | None:
    t = theorem_type(code)
    if t == "prove_correct":
        return _parse_prove_correct(code)
    elif t in ("theorem", "lemma"):
        return _parse_theorem(code) or _parse_theorem(code, delimiter=r":=")
    else:
        return None


def split_decls_by_keyword(code: str) -> list[str]:
    """
    Split code into blocks at occurrences of the unified DECL_HEADER_RE.
    Everything before the first such group is returned as block 0 (preamble).
    Each subsequent block starts at a header match and extends up to
    (but not including) the next header.
    """
    code = normalize_empty_lines(code.lstrip("\n"))
    blocks: list[str] = []
    try:
        matches = list(DECL_HEADER_RE.finditer(code, timeout=2.0))
    except TimeoutError:
        matches = []
    if not matches:
        return [code] if code else []

    # Preamble: anything before the first group
    first = matches[0]
    if first.start() > 0:
        blocks.append(code[: first.start()])

    # Each header group starts a block
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(code)
        blocks.append(code[start:end])
    return blocks


def skip_ws(s: str, i: int) -> int:
    while i < len(s) and s[i].isspace():
        i += 1
    return i


def parse_paren_expr(s: str, i: int) -> int:
    """
    Given s[i] == '(', return the index just after the matching ')'.
    If parentheses are unbalanced, returns len(s).
    """
    if i >= len(s) or s[i] != "(":
        raise ValueError("parse_paren_expr: expected '(' at position i")
    depth = 1
    i += 1
    while i < len(s) and depth:
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
        i += 1
    return i


def parse_atom(s: str, i: int) -> int:
    """
    Parse a simple atom starting at i: a maximal run of non-whitespace chars
    not containing '(' or ')' and not crossing common delimiters.
    """
    start = i
    delimiters = set("()[],;{}")
    while i < len(s):
        c = s[i]
        if c.isspace() or c in delimiters:
            break
        i += 1
    return i if i > start else start


def parse_dot_chain(s: str, i: int) -> int:
    """
    Consume zero or more suffixes like `.ident` (optionally with whitespace before the dot).
    Does NOT consume further terms as arguments.
    """
    n = len(s)
    while True:
        i0 = i
        i = skip_ws(s, i)
        if i >= n or s[i] != ".":
            return i0
        i += 1
        start = i
        while i < n and (s[i].isalnum() or s[i] in "_'"):
            i += 1
        if i == start:
            return i0


def parse_term(s: str, i: int) -> int:
    """
    Parse one term beginning at i; returns the end index.
    Term is either a parenthesized expression or an atom, possibly followed by
    dot-chaining suffixes.
    """
    i = skip_ws(s, i)
    if i >= len(s):
        return i
    if s[i] == "(":
        end = parse_paren_expr(s, i)
    else:
        end = parse_atom(s, i)
    return parse_dot_chain(s, end)


def remove_withname_erase(s: str) -> str:
    """
    Rewrite calls to `WithName.erase` applied to a single following term.
    This function scans the input string `s` for occurrences of the literal
    substring ``"WithName.erase"`` and, when it appears as a standalone token
    followed by whitespace and then a “term”, it rewrites:
        WithName.erase <term>
    into:
        (<term>)
    where `<term>` is parsed by a simple heuristic (not a full Lean parser):
    - Leading whitespace after `WithName.erase` is required (at least one space,
      newline, etc.). If `WithName.erase` is immediately followed by a
      non-whitespace character, no rewrite is performed at that location.
    - A “term” is either:
      * a parenthesized expression with balanced parentheses, e.g. ``(x + (y))``,
        in which case the whole parenthesized chunk is consumed; or
      * an “atom”: a maximal run of non-whitespace characters that does not
        include common delimiters ``()[],;{}``.
    If no term can be parsed after the whitespace, the text at that position is
    left unchanged and scanning continues.
    Notes / limitations
    -------------------
    - This is purely textual. It does not understand comments or string
      literals, so parentheses inside them will affect balancing.
    - The transformation wraps the parsed term in parentheses regardless of
      whether it already was parenthesized.
    Parameters
    ----------
    s : str
        Input string.
    Returns
    -------
    str
        A copy of `s` with occurrences of ``WithName.erase <term>`` rewritten
        as ``(<term>)`` where recognized.
    """
    head = "WithName.erase"
    out = []
    i = 0
    n = len(s)

    while True:
        j = s.find(head, i)
        if j == -1:
            out.append(s[i:])
            break

        out.append(s[i:j])
        k = j + len(head)

        # require at least one whitespace char after the head
        if k < n and not s[k].isspace():
            out.append(s[j:k])
            i = k
            continue

        k0 = k
        k = skip_ws(s, k)
        t_start = k
        t_end = parse_term(s, k)
        if t_end == t_start:
            out.append(s[j:k0])
            i = k0
            continue

        out.append("(" + s[t_start:t_end] + ")")
        i = t_end

    return "".join(out)


def remove_withname_mk_erase(s: str) -> str:
    """
    Replace Lean-style “erase wrapper” expressions of the form:
        (WithName.mk' <arg1> <arg2>).erase
    with just:
        <arg1>
    across the entire input string.
    Parsing behavior:
    - Searches left-to-right for the literal marker ``"(WithName.mk'"``.
    - Parses two arguments after ``WithName.mk'``:
      * Each argument may be either:
        - a parenthesized expression with balanced parentheses, e.g. ``(i + (1 : ℕ))``
        - an atom (a maximal run of non-whitespace characters not containing ``(`` or ``)``),
          e.g. ``x``, ``Nat.succ``, ``_``.
    - Requires the second argument to be followed by a closing ``)`` and then an attribute
      access exactly ``.erase`` (not ``.eraser``, etc.).
    - On a successful match, replaces the entire substring
      ``(WithName.mk' <arg1> <arg2>).erase`` with the textual substring for ``<arg1>``.
    - If the expected shape is not found at a candidate location, leaves the text unchanged
      and continues scanning.
    Limitations:
    - This is not a full Lean parser. It does not account for comments or string literal
      syntax; parentheses occurring inside quotes/comments will still affect the simple
      parenthesis balancer.
    - The atom heuristic may not cover every Lean tokenization edge case.
    Parameters
    ----------
    s : str
        Input string that may contain occurrences of ``(WithName.mk' ... ...).erase``.
    Returns
    -------
    str
        A copy of ``s`` with all recognized occurrences replaced by their first argument.
    """
    target = "(WithName.mk'"

    def is_erase_at(pos: int) -> bool:
        if not s.startswith(".erase", pos):
            return False
        end = pos + len(".erase")
        if end >= len(s):
            return True
        return not (s[end].isalnum() or s[end] in "_'")

    out = []
    i = 0

    while True:
        j = s.find(target, i)
        if j == -1:
            out.append(s[i:])
            break

        out.append(s[i:j])
        k = j + len(target)

        k = skip_ws(s, k)
        arg1_start = k
        arg1_end = parse_term(s, k)
        if arg1_end == arg1_start:
            out.append(s[j : j + 1])
            i = j + 1
            continue

        k = skip_ws(s, arg1_end)
        arg2_start = k
        arg2_end = parse_term(s, k)
        if arg2_end == arg2_start:
            out.append(s[j : j + 1])
            i = j + 1
            continue

        k = skip_ws(s, arg2_end)
        if k >= len(s) or s[k] != ")":
            out.append(s[j : j + 1])
            i = j + 1
            continue
        k += 1

        if not is_erase_at(k):
            out.append(s[j : j + 1])
            i = j + 1
            continue

        out.append(s[arg1_start:arg1_end])
        i = k + len(".erase")

    return "".join(out)


def _test_remove_withname_mk_erase():
    # 1) Basic example
    s = '(WithName.mk\' (i + (1 : ℕ)) (Lean.Name.anonymous.mkStr "i")).erase'
    assert remove_withname_mk_erase(s) == "(i + (1 : ℕ))"

    # 2) Works inside a larger string
    s = 'pre ((WithName.mk\' (i + (1 : ℕ)) (Lean.Name.anonymous.mkStr "i")).erase) post'
    assert remove_withname_mk_erase(s) == "pre ((i + (1 : ℕ))) post"

    # 3) Multiple occurrences
    s = "A (WithName.mk' (x) n).erase B (WithName.mk' (y + (z)) m).erase C"
    assert remove_withname_mk_erase(s) == "A (x) B (y + (z)) C"

    # 4) arg1 is an atom (not parenthesized)
    s = "(WithName.mk' x (Lean.Name.anonymous)).erase"
    assert remove_withname_mk_erase(s) == "x"

    # 5) arg2 contains parentheses; must still match correctly
    s = "(WithName.mk' (x) (f (g (h)))).erase"
    assert remove_withname_mk_erase(s) == "(x)"

    # 6) ".erase" appears later; should only consume when pattern matches exactly
    s = "before (WithName.mk' (x) (y)).erase after .erase tail"
    assert remove_withname_mk_erase(s) == "before (x) after .erase tail"

    # 7) Not a match: missing .erase
    s = "before (WithName.mk' (x) (y)) after"
    assert remove_withname_mk_erase(s) == "before (WithName.mk' (x) (y)) after"

    # 8) Not a match: has ')foo' not ').erase'
    s = "(WithName.mk' (x) (y)).eraser"
    assert remove_withname_mk_erase(s) == "(WithName.mk' (x) (y)).eraser"

    # 9) Not a match: wrong head symbol
    s = "(WithName.mkk' (x) (y)).erase"
    assert remove_withname_mk_erase(s) == "(WithName.mkk' (x) (y)).erase"

    # 10) Whitespace variations
    s = "(WithName.mk'   (x + (y))   (name)  ).erase"
    assert remove_withname_mk_erase(s) == "(x + (y))"

    # 11) .method in arg1
    s = "(WithName.mk' (x + (y)).length (name)).erase"
    assert remove_withname_mk_erase(s) == "(x + (y)).length", remove_withname_mk_erase(
        s
    )

    # 12) Adjacent text around the pattern
    s = "Z(WithName.mk' (x) (y)).erase W"
    assert remove_withname_mk_erase(s) == "Z(x) W"

    # 13) Nested inside other parentheses
    s = "(((WithName.mk' (x) (y)).erase))"
    assert remove_withname_mk_erase(s) == "(((x)))"

    # 14) .erase followed by another .method
    s = '(WithName.mk\' ((rest)).tail (Lean.Name.anonymous.mkStr "rest")).erase.length'
    assert remove_withname_mk_erase(s) == "((rest)).tail.length"


def _test_remove_withname_erase():
    # 1) Basic atom argument
    s = "WithName.erase x"
    assert remove_withname_erase(s) == "(x)"

    # 2) Parenthesized argument (nested parens)
    s = "WithName.erase (i + (1 : ℕ))"
    assert remove_withname_erase(s) == "((i + (1 : ℕ)))"

    # 3) Preserves precedence by inserting parens
    s = "WithName.erase i + 1"
    assert remove_withname_erase(s) == "(i) + 1"

    # 4) Works inside a larger expression
    s = "f (WithName.erase x) + g"
    assert remove_withname_erase(s) == "f ((x)) + g"

    # 5) Multiple occurrences
    s = "WithName.erase x, WithName.erase (y + z)"
    assert remove_withname_erase(s) == "(x), ((y + z))"

    # 6) Whitespace variations
    s = "WithName.erase    x"
    assert remove_withname_erase(s) == "(x)"

    # 7) Newline after head (should work; we require whitespace, not a single space)
    s = "WithName.erase\nx"
    assert remove_withname_erase(s) == "(x)"

    # 8) Not a match: head is a prefix of a longer identifier
    s = "WithName.eraseFoo x"
    assert remove_withname_erase(s) == "WithName.eraseFoo x"

    # 9) Not a match: no whitespace after head => likely attribute / longer token
    s = "WithName.erase.x"
    assert remove_withname_erase(s) == "WithName.erase.x"

    # 10) Edge: no argument
    s = "WithName.erase"
    assert remove_withname_erase(s) == "WithName.erase"


if __name__ == "__main__":
    sample_lean_code = """
/-!
This is a module comment.
-/
import Mathlib.Data.Nat.Basic

@[simp, someAttr] private noncomputable theorem myThm (n : Nat) : True := by
  trivial

set_option maxHeartbeats 100000 in theorem a : True := trivial

set_option maxHeartbeats 1600000 in
@[simp] private lemma b : True := by
  trivial

set_option auto.smt.timeout 12 in prove_correct isPeakValley by
  loom_solve <;> simp_all
"""

    declarations = split_decls_by_keyword(sample_lean_code)

    print(f"\nFound {len(declarations)} blocks.\n")
    print("========================================\n")

    for i, decl in enumerate(declarations):
        print(f"### BLOCK {i} ###")
        print(decl)
        print("\n----------------------------------------\n")

        t = theorem_type(decl)
        if t:
            print(f"  -> Type: {t}")
            print(parse_theorem(decl))
            print(theorem_type(decl))
        else:
            print("  -> Type: Other")
        print("\n========================================\n")

    _test_remove_withname_mk_erase()
    _test_remove_withname_erase()
