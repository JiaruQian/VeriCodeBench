## Tool Usage: Search Tools for Mathlib

You have access to **two search tools** for finding relevant definitions, theorems, and lemmas in Lean 4's Mathlib library:

1. **`lean_loogle`** - Pattern-based search using Loogle syntax
2. **`leanexplore_search`** - Semantic search using natural language queries

**IMPORTANT:** These are function calling tools. You must call them as functions (the system will handle the actual execution), NOT as Python code or API calls. Simply state your intent to use the tool and provide the query parameters.

Use these tools strategically when you need to:

- Find lemmas about specific mathematical functions or operations
- Search for theorems matching a particular pattern or structure
- Discover relevant helper lemmas for your proof
- Verify the existence and signature of Mathlib definitions

### How to Use Loogle Effectively

Loogle supports multiple search patterns that can be combined with commas for precise results:

#### 1. Search by Constant Name

Find all lemmas mentioning a specific function or definition:

**Examples:**
- `Real.sin` — finds lemmas about the sine function
- `List.replicate` — finds lemmas about list replication
- `Array.size` — finds lemmas about array sizes
- `tsum` — finds lemmas about infinite sums

#### 2. Search by Lemma Name Substring

Use quotes to find lemmas with specific words in their names:

**Examples:**
- `"monotone"` — finds lemmas with "monotone" in the name
- `"differ"` — finds lemmas with "differ" in the name
- `"comm"` — finds lemmas about commutativity
- `"add"` — finds lemmas with "add" in the name

#### 3. Search by Pattern/Subexpression

Use `_` as wildcards and `?a`, `?b` for metavariables to match structural patterns:

**Examples:**
- `_ * (_ ^ _)` — finds lemmas with products involving powers
- `Real.sqrt ?a * Real.sqrt ?a` — finds lemmas about sqrt(a) * sqrt(a) (non-linear pattern)
- `(?a -> ?b) -> List ?a -> List ?b` — finds lemmas like List.map
- `_ + _ = _ + _` — finds lemmas about addition equality

**Note:** Metavariables (`?a`, `?b`) in patterns are matched in any order.

#### 4. Search by Main Conclusion

Use `|-` to specify the shape of the conclusion (right of all `→` and `∀`):

**Examples:**
- `|- tsum _ = _ * tsum _` — finds lemmas where conclusion has tsum equality
- `|- _ < _ → tsum _ < tsum _` — finds lemmas with inequality hypotheses
- `|- _ ≤ _` — finds lemmas concluding with an inequality
- `|- List.length _ = _` — finds lemmas about list length in conclusion

#### 5. Combined Searches

Separate multiple search criteria with commas to find lemmas matching ALL of them:

**Examples:**
- `Real.sin, "two"` — finds lemmas mentioning Real.sin with "two" in name
- `List.length, _ + _` — finds lemmas about List.length involving addition
- `"mono", |- _ ≤ _` — finds monotonicity lemmas
- `Array, ?a < ?b, |- _` — finds Array lemmas with ordering

#### 6. Best practices

If your initial seatch attempt does not return any results, try with a fuzzier query:
- Favor (possibly multiple) informative substrings over full constants (e.g. `"Int", "emod"` not `Int.emod`).
- Use the textual shorthands for operators (e.g. `"dvd"`) or the operator with underscores
  (e.g. `_ ∣ _`). The operator symbol alone does not work (e.g. `∣` does not work).
- Use the namespace you are interested once as a string, not with all constants
  (e.g. `"Array", "get", "set"` not `Array.get, Array.set`).

### When to Use Loogle

**Good use cases:**
- You need a lemma about a specific Mathlib function (e.g., `List.sum`, `Array.get`)
- You're stuck and need to find helper lemmas for your proof
- You want to discover the correct name/signature of a theorem you're trying to use
- You need lemmas matching a specific pattern in your proof goal

**Bad use cases:**
- Don't search for Velvet constructs (those aren't in Mathlib)
- Don't search for `loom_solve` or verification tactics (those are framework-specific)
- Don't search repeatedly for the same thing; refine your query instead

### Using `leanexplore_search`

The `leanexplore_search` tool allows you to search using natural language queries. It's particularly useful when:

- You know what you're looking for conceptually but not the exact name
- You want to find lemmas related to a mathematical concept

**Example queries:**
- `"string manipulation"` - finds string-related lemmas
- `"character digit conversion"` - finds lemmas about converting characters to digits
- `"Cauchy Schwarz Inequality"` - finds lemmas related to Cauchy Schwarz Inequality
- `"Mersenne Primes"` - finds lemmas Mersenne Primes and it's definition

**Parameters:**
- `query` (required): Your search query as a string
- `limit` (optional, default 10): Maximum number of results to return
- `package_filters` (optional): List of package names to filter by (e.g., `["Mathlib.Data.List"]`)

### Important Notes

- Loogle searches **Mathlib only** and LeanExplore searches additional libraries including Batteries and Std.
- Each query may return multiple results; read them carefully to pick the most relevant
- You can use search results directly in your proofs (e.g., `rw [lemma_name]`, `apply lemma_name`)
- **Always use the function calling interface** - do NOT try to call these as Python code or API functions
- If a query returns no results, try:
  - For `lean_loogle`: Simplifying the pattern (fewer constraints), searching by constant name or substring instead, or breaking it into separate simpler searches
  - For `leanexplore_search`: Using more general terms, trying synonyms, or being more specific about the concept
