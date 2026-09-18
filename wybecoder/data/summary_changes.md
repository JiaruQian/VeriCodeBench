# Summary of changes CLEVER

## 1. words_string 

You will be given a string of words separated by commas or spaces. Your task is
to split the string into words and return an array of the words.

### Spec: 

```
method words_string (s: String) return (result: List String)
  ensures result = [] ↔ ((∀ x ∈ s.toList, x = ' ' ∨ x = ',') ∨ s = "")
  ensures let first_word (s' : String) := s'.takeWhile (fun c => c ≠ ',' ∧ c ≠ ' ');
          let rec nth_start (n : Nat) : Nat :=
            if n = 0 then 0
            else
              let prev := nth_start (n - 1);
              let rest := s.drop (prev + 1);
              let next_word := first_word rest;
              prev + 1 + next_word.length;
          ∀ i < result.length,
            result[i]! = (s.drop (nth_start i)).takeWhile (fun c => c ≠ ',' ∧ c ≠ ' ')
  ensures result ≠ [] →
          let reconstruction := result.foldl (fun acc word => acc ++ word ++ "?") "";
          reconstruction = ((s.replace "," "?").replace " " "?") ++ "?"
  do
    sorry
```

### GPT5 complain: 

-- ESCALATE: The given specification appears internally inconsistent for general strings:
-- - The second postcondition states that each result[i] is exactly the substring of s
--   consisting of maximal runs of characters not equal to ',' or ' ' (so dots remain inside words).
-- - The third postcondition, however, requires that the fold reconstruction equals the string
--   where '.' is also replaced by '?'. This cannot hold when s contains dots because the words
--   contributed to the fold contain dots unchanged (by the second postcondition), while the
--   right-hand side has all dots replaced. This yields a mismatch unless s contains no dots
--   or result = [] (in which case the implication vacuously holds), but the first postcondition
--   forbids returning [] unless s is empty or all separators (',' or ' '), i.e., not allowing
--   dots. Therefore, for arbitrary strings containing '.', the second and third postconditions
--   are mutually incompatible.
-- I implemented the intended splitter that matches the nth_start definition (including empty
-- segments for consecutive separators) and ensured the first postcondition by returning []
-- only when s="" or all separators. Proving the third postcondition for all strings would
-- require altering the word-content to replace '.' inside words, which directly contradicts
-- the second postcondition. Consequently, a full proof in Velvet cannot be completed as-is.


### Updated spec:

1. Updated the 2nd ensures to handle leading separators (',' or space) and multiple consecutive separators between words.
2. Replaced the 3rd ensures with a completeness condition: result.length equals the number of words in s (word = maximal run of characters that are not ',' or space). Together with (2), this should prevent result from being a strict prefix of the true split => completeness. The previous ensures we had was attempting to do a reconstruction. This is not possible for all cases. Actually there are so many cases where reconstruction is not possible from result -> s.

## Mantas review:

The original specification for the reconstruction property (3rd postcondition) was indeed inconsistent and brittle.
1. **Dot replacement inconsistency**: It required replacing `.` with `?` in the original string `s`, but the word extraction logic (2nd postcondition) preserves dots within words. For an input like `"a.b"`, the implementation returns `["a.b"]` (reconstructs to `"a.b?"`), but the spec required `"a?b?"`.
2. **Separator handling**: Simple string replacement converts every separator to a `?`. For inputs with consecutive separators like `"a,,b"`, the implementation returns `["a", "b"]` (reconstructs to `"a?b?"`), but the original spec required `"a??b?"`.

I replaced the simplistic string replacement with a structural normalization approach. The new `ensures` clause defines a `normalize` function that mimics the word splitting logic: skipping separators, taking words, and appending `?`. This ensures the reconstruction  includes edge cases with multiple separators or dots, making the specification consistent.


```
method words_string (s: String) return (result: List String)
  ensures result = [] ↔ ((∀ x ∈ s.toList, x = ' ' ∨ x = ',') ∨ s = "")
  ensures let first_word (s' : String) := s'.takeWhile (fun c => c ≠ ',' ∧ c ≠ ' ');
          let rec nth_start (n : Nat) : Nat :=
            if n = 0 then
              let leading_seps := s.takeWhile (fun c => c = ',' ∨ c = ' ');
              leading_seps.length
            else
              let prev := nth_start (n - 1);
              let rest := s.drop prev;
              let prev_word_len := (rest.takeWhile (fun c => c ≠ ',' ∧ c ≠ ' ')).length;
              let after_prev := prev + prev_word_len;
              let sep_len := ((s.drop after_prev).takeWhile (fun c => c = ',' ∨ c = ' ')).length;
              after_prev + sep_len;
          ∀ i < result.length,
            result[i]! = (s.drop (nth_start i)).takeWhile (fun c => c ≠ ',' ∧ c ≠ ' ')
  ensures
    result != [] →
          let is_sep (c : Char) := c = ',' ∨ c = ' ';
          let rec normalize (fuel : Nat) (cs : List Char) : String :=
            match fuel with
            | 0 => ""
            | n + 1 =>
              match cs.dropWhile is_sep with
              | [] => ""
              | cs' =>
                let word := cs'.takeWhile (fun c => ¬ is_sep c)
                let rest := cs'.dropWhile (fun c => ¬ is_sep c)
                String.mk word ++ "?" ++ normalize n rest
          let reconstruction := result.foldl (fun acc word => acc ++ word ++ "?") "";
          reconstruction = normalize (s.length + 1) s.toList
  do
    sorry
```



## 2. minSubArraySum

Given an array of integers nums, find the minimum sum of any non-empty sub-array
of nums.

### Spec:

```
method minSubArraySum (nums: List Int) return (res: Int)
  require nums.length > 0
  ensures res ∈ nums.sublists
  ensures ∀ subarray ∈ nums.sublists, subarray.length > 0 → res ≤ subarray.sum
  ensures ∃ subarray ∈ nums.sublists, subarray.length > 0 ∧ res = subarray.sum
  do
```

### GPT5 complain:
-- ESCALATE:
-- The specification line `ensures res ∈ nums.sublists` is ill-typed in Lean:
-- `nums.sublists : List (List Int)` while `res : Int`, hence Lean needs an
-- instance `[Membership Int (List (List Int))]` to elaborate `res ∈ nums.sublists`,
-- which does not exist. Because we are instructed not to modify anything
-- above the `do`, we cannot introduce a suitable instance or change the spec.
-- This causes the entire method header to fail elaboration before the body
-- or any proof can be provided.
--
-- To proceed, the specification must be corrected semantically and
-- type-theoretically, for example to:
--   ensures ∃ subarray ∈ nums.sublists, subarray.length > 0 ∧ res = subarray.sum
--   ensures ∀ subarray ∈ nums.sublists, subarray.length > 0 → res ≤ subarray.sum
-- and dropping the ill-typed `res ∈ nums.sublists`. Alternatively, replace
-- it with `res ∈ (nums.sublists.map List.sum)` if the intent was to assert
-- that `res` is one of the sublist sums.
--
-- With the current header, Lean cannot synthesize the required typeclass
-- instance and the file will not compile. Once the spec is fixed, I can
-- provide a complete implementation and proof using Velvet and Loom.

### Updated spec:

1. Removed 2nd ensures which is ill-typed and redundant given the last ensures.

```
method minSubArraySum (nums: List Int) return (res: Int)
  require nums.length > 0
  ensures ∀ subarray ∈ nums.sublists, subarray.length > 0 → res ≤ subarray.sum
  ensures ∃ subarray ∈ nums.sublists, subarray.length > 0 ∧ res = subarray.sum
  do
    sorry
```

## Mantas review:

I agree with the removal of the ill-typed `ensures` clause. The original `ensures res ∈ nums.sublists` was indeed attempting to check membership of an integer in a list of lists, which is invalid. The remaining postconditions correctly specify the minimal subarray sum property.


## 3. match_parens

You are given a list of two strings, both strings consist of open
parentheses '(' or close parentheses ')' only.
Your job is to check if it is possible to concatenate the two strings in
some order, that the resulting string will be good.
A string S is considered to be good if and only if all parentheses in S
are balanced. For example: the string '(())()' is good, while the string
'())' is not.
Return 'Yes' if there's a way to make a good string, and return 'No' otherwise.


### Spec:

```
method match_parens (l: List String) return (result: String)
  require l.length = 2
  require l[0]!.all (fun c => c = '(' ∨ c = ')')
  require l[1]!.all (fun c => c = '(' ∨ c = ')')
  ensures let isBalanced (s : String) : Bool :=
    -- a string is not balanced if at any point the number of closing parens exceeds opening parens
    ∀ i < s.length, (s.take i).toList.foldl (fun acc c => if c = '(' then acc + 1 else acc - 1) (0 : Int) ≥ 0 ∧
      (s.toList.foldl (fun acc c => if c = '(' then acc + 1 else acc - 1) (0 : Int) = 0);
    (result = "Yes" ↔
      (isBalanced (l[0]! ++ l[1]!) ∨ isBalanced (l[1]! ++ l[0]!))) ∧
    (result = "No" ↔
      ¬ (isBalanced (l[0]! ++ l[1]!) ∧ isBalanced (l[1]! ++ l[0]!)))
  do
```

### GPT5 complain:

-- ESCALATE: The given specification is internally inconsistent.
-- It requires simultaneously:
--   (1) result = "Yes" ↔ (isBalanced (s0 ++ s1) ∨ isBalanced (s1 ++ s0))
--   (2) result = "No"  ↔ ¬(isBalanced (s0 ++ s1) ∧ isBalanced (s1 ++ s0))
-- For inputs such as l = ["(", ")"], we have:
--   isBalanced ("(" ++ ")") = True, isBalanced (")" ++ "(") = False.
-- Then (1) demands result = "Yes" (since the disjunction is True),
-- while (2) demands result = "No" (since ¬(True ∧ False) is True).
-- No function can satisfy both equivalences for all admissible inputs.
-- Consequently, the verification conditions are unsatisfiable,
-- and `loom_solve` cannot prove them. The implementation above matches
-- the intuitive intent (return "Yes" iff either concatenation is balanced),
-- but proving the provided ensures is impossible without changing them.

### Updated spec:

1. Postcondition fails if exactly one ordering is balances l[0] ++ l[1] or l[1] ++ l[0]. E.g., l = ["(" , ")"] -> l[0] ++ l[1] is ordered => result = "Yes" ↔ True AND result = "No" ↔ True (not (True and False) = not (False) = True), but result can't be both yes and no.
I updated the spec to use OR instead of AND for the "No" case

## Mantas review:

- I agree with the idea of the fix. Although replace AND with OR in the 'No' case condition correctly ensures that 'No' is returned only when neither concatenation is balanced, so let's go for it instead.

```
method match_parens (l: List String) return (result: String)
  require l.length = 2
  require l[0]!.all (fun c => c = '(' ∨ c = ')')
  require l[1]!.all (fun c => c = '(' ∨ c = ')')
  ensures let isBalanced (s : String) : Bool :=
    -- a string is not balanced if at any point the number of closing parens exceeds opening parens
    ∀ i < s.length, (s.take i).toList.foldl (fun acc c => if c = '(' then acc + 1 else acc - 1) (0 : Int) ≥ 0 ∧
      (s.toList.foldl (fun acc c => if c = '(' then acc + 1 else acc - 1) (0 : Int) = 0);
    (result = "Yes" ↔
      (isBalanced (l[0]! ++ l[1]!) ∨ isBalanced (l[1]! ++ l[0]!))) ∧
    (result = "No" ↔
      ¬ (isBalanced (l[0]! ++ l[1]!) ∨ isBalanced (l[1]! ++ l[0]!)))
  do
    sorry
```




## 4. minPath

Given a grid with N rows and N columns (N >= 2) and a positive integer k,
each cell of the grid contains a value. Every integer in the range [1, N * N]
inclusive appears exactly once on the cells of the grid.

You have to find the minimum path of length k in the grid. You can start
from any cell, and in each step you can move to any of the neighbor cells,
in other words, you can go to cells which share an edge with you current
cell.
Please note that a path of length k means visiting exactly k cells (not
necessarily distinct).
You CANNOT go off the grid.
A path A (of length k) is considered less than a path B (of length k) if
after making the ordered lists of the values on the cells that A and B go
through (let's call them lst_A and lst_B), lst_A is lexicographically less
than lst_B, in other words, there exist an integer index i (1 <= i <= k)
such that lst_A[i] < lst_B[i] and for any j (1 <= j < i) we have
lst_A[j] = lst_B[j].
It is guaranteed that the answer is unique.
Return an ordered list of the values on the cells that the minimum path go through.


### Spec:

```
def lexicographically_less (k: Nat) (a b: List Nat) : Prop :=
  a.length = b.length ∧ a.length = k ∧
  (∃ i, i < k ∧ a[i]! < b[i]! ∧
    (∀ j, j < i → a[j]! = b[j]!))

def is_valid_path (k': Nat) (path: List Nat) (grid: List (List Nat)) : Prop :=
  let n := grid.length;
  match k' with
  | 0 => if path.length = 0 then true else false
  | _ + 1 =>
    if path.length = k' then
    (∃ i j,
      (i < n ∧ j < n ∧ path[0]! = (grid[i]!)[j]!) ∧
      (1 < path.length →
        ( ∃ i' j', i' < n ∧ j' < n ∧
          (path[1]! = (grid[i']!)[j']!) ∧
          ((abs ((i: Int) - (i': Int)) = 1 ∧ j = j') ∨
          (abs ((j: Int) - (j': Int)) = 1 ∧ i = i'))) ∧
        (is_valid_path (k' - 1) (path.drop 1) grid))
    )
    else false

method minPath (grid: List (List Nat)) (k: Nat) return (res: List Nat)
  require n >= 2
  require k > 0
  require let n := grid.length; ∀ i, i < n → (grid.get! i).length = n
  require let n := grid.length; ∀ i j, i < n → j < n ↔ (1 ≤ (grid.get! i).get! j ∧ (grid.get! i).get! j ≤ n * n)
  require let n := grid.length; ∀ k, 1 ≤ k ∧ k ≤ n * n → ∃ i j, i < n ∧ j < n ∧ (grid.get! i).get! j = k
  ensures is_valid_path k res grid
  ensures ∀ path, path != res → is_valid_path k path grid → lexographically_less k res path
  do
```

### GPT5 complain:

-- The header above the `do` block contains three issues that make it impossible to provide
-- a verified implementation without modifying it:
-- 1) `require n >= 2` uses an unbound identifier `n`. It should be `let n := grid.length; n ≥ 2`.
-- 2) The last ensures uses `lexographically_less` (misspelled) while the definition provided is `lexicographically_less`.
-- 3) The last ensures uses `path != res`; Lean's inequality is `path ≠ res`. There is no built-in `!=`.
--
-- If the header is corrected to:
--   require let n := grid.length; n ≥ 2
--   ensures ∀ path, path ≠ res → is_valid_path k path grid → lexicographically_less k res path
-- then the following fully verified solution (greedy minimal-neighbor path) can be provided.
--
-- As requested, helper lemmas and solver hints would be placed here after the method definition.
--
-- Because the current header must not be modified, a full verification is not possible.
-- Consequently, we cannot provide a `prove_correct` block for `minPath` under this header.

### Updated spec:

1. Replaced `n` with `grid.length` as `n` isn't defined
2. Added another pre-condition to ensure the matrix is N X N with N >= 2
3. Fixed the spelling mistake in lexicographically_less
4. Replaced != with ≠

```
def lexicographically_less (k: Nat) (a b: List Nat) : Prop :=
  a.length = b.length ∧ a.length = k ∧
  (∃ i, i < k ∧ a[i]! < b[i]! ∧
    (∀ j, j < i → a[j]! = b[j]!))

## Mantas review:

Reviewed the minPath change and it LGTM.

def is_valid_path (k': Nat) (path: List Nat) (grid: List (List Nat)) : Prop :=
  let n := grid.length;
  match k' with
  | 0 => if path.length = 0 then true else false
  | _ + 1 =>
    if path.length = k' then
    (∃ i j,
      (i < n ∧ j < n ∧ path[0]! = (grid[i]!)[j]!) ∧
      (1 < path.length →
        ( ∃ i' j', i' < n ∧ j' < n ∧
          (path[1]! = (grid[i']!)[j']!) ∧
          ((abs ((i: Int) - (i': Int)) = 1 ∧ j = j') ∨
          (abs ((j: Int) - (j': Int)) = 1 ∧ i = i'))) ∧
        (is_valid_path (k' - 1) (path.drop 1) grid))
    )
    else false

method minPath (grid: List (List Nat)) (k: Nat) return (res: List Nat)
  require grid.length >= 2
  require let n := grid.length; ∀ i, i < n → (grid.get! i).length = n
  require k > 0
  require let n := grid.length; ∀ i j, i < n → j < n → (1 ≤ (grid.get! i).get! j ∧ (grid.get! i).get! j ≤ n * n)
  require let n := grid.length; ∀ k, 1 ≤ k ∧ k ≤ n * n → ∃ i j, i < n ∧ j < n ∧ (grid.get! i).get! j = k
  ensures is_valid_path k res grid
  ensures ∀ path, path ≠ res → is_valid_path k path grid → lexicographically_less k res path
  do
    sorry
```



## 5. is_sorted

Given a list of numbers, return whether or not they are sorted
in ascending order. If list has more than 1 duplicate of the same
number, return False. Assume no negative numbers and only integers.


### Spec:

```
method is_sorted (lst: List Int) return (res: Bool)
  requires ∀ x ∈ lst, x ≥ 0
  ensures res ↔ (lst.Sorted (· ≤ ·) ∧ ¬(∃ i, i ∈ lst ∧ 2 < (Multiset.ofList lst).count i))
  do
```

### GPT5 complain:

-- ESCALATE: The provided header uses the tokens `requires`/`ensures`.
-- In the Loom/Velvet version available here, the `method` macro expects `require`/`ensure`.
-- Because the header must remain exactly as given (string-checked), we cannot adjust it to the accepted syntax.
-- This causes Lean to report “unexpected identifier; expected 'do'” at the `requires` line.
-- If permitted to change the header to use `require`/`ensure`, the proof below succeeds with:
--   prove_correct is_sorted by
--     loom_solve <;>
--     by_cases h : (lst.Sorted (· ≤ ·) ∧ ¬(∃ i, i ∈ lst ∧ 2 < (Multiset.ofList lst).count i)) <;> simp [h]


### Updated spec:

1. Replaced only the requires with require. Ensures is correct!

## Mantas review:

I agree with the fix. Using `require` (singular) is the right syntax.

```
method is_sorted (lst: List Int) return (res: Bool)
  require ∀ x ∈ lst, x ≥ 0
  ensures res ↔ (lst.Sorted (· ≤ ·) ∧ ¬(∃ i, i ∈ lst ∧ 2 < (Multiset.ofList lst).count i))
  do
    sorry
```




## 6. fix_spaces

Given a string text, replace all spaces in it with underscores,
and if a string has more than 2 consecutive spaces,
then replace all consecutive spaces with -


### Spec:

```
def IsAllSpaces (cs : List Char) : Bool :=
  cs.all (· = ' ')

method fix_spaces (text: String) return (result: String)
  ensures ∃ (partition : List (List Char)),
      IsAlternatingPartition partition text
      ∧
      result = ⟨(partition.map ≈).flatten⟩
  do
    sorry
```

### GPT5 complain:

-- ESCALATE: The specification refers to constants
-- IsAlternatingPartition, transformChunk, and List.flatten.
-- In Lean, names used in the method header (ensures) and body must exist
-- before the method definition is elaborated. The instruction requires
-- not modifying any code above this 'do' block, but those constants are
-- not defined in the provided header and are also not part of the imported
-- modules in this environment. Defining them after the method causes Lean
-- to fail when elaborating the ensures clause (they must be in scope already).
--
-- Therefore, it is impossible to both keep the header exactly unchanged and
-- successfully compile/verify the method, because the header references
-- undeclared identifiers. In the previous working version, we defined
-- the necessary helper constants (IsAlternatingPartition, transformChunk,
-- alternatingPartition, and List.flatten) before the method, which made
-- the code compile and the proof succeed. Moving those definitions after
-- the method breaks elaboration of the ensures clause.
--
-- Summary of learnings:
-- - Velvet/Lean elaborates the method signature (including ensures) before
--   the body, so referenced constants must already be defined.
-- - The provided header references names that are not available from the
--   given imports; they must be introduced before the method.
-- - The constraint "do not modify code above do" conflicts with Lean's
--   requirement for name resolution, making the task unsatisfiable without
--   additional pre-defined library support.

### Updated spec:

1. Missing helper functions. Added definitions for missing helpers + adjusted the postcond

```
def IsAllSpaces (cs : List Char) : Bool :=
  cs.all (· = ' ')

def IsAllNonSpaces (cs : List Char) : Bool :=
  cs.all (· ≠ ' ')

def IsAlternatingPartition (parts : List (List Char)) : Prop :=
  (∀ chunk ∈ parts, chunk ≠ []) ∧
  (∀ chunk ∈ parts, IsAllSpaces chunk ∨ IsAllNonSpaces chunk) ∧
  (∀ i, i + 1 < parts.length →
      (IsAllSpaces (parts[i]!) ∧ IsAllNonSpaces (parts[i+1]!)) ∨
      (IsAllNonSpaces (parts[i]!) ∧ IsAllSpaces (parts[i+1]!)))

def TransformChunk (chunk : List Char) : List Char :=
  if IsAllSpaces chunk then
    if chunk.length ≤ 2 then
      List.replicate chunk.length '_'
    else
      ['-']
  else
    chunk

def joinLists {α : Type} (xss : List (List α)) : List α :=
  xss.foldl (fun acc xs => acc ++ xs) []

method fix_spaces (text : String) return (result : String)
  ensures ∃ (partition : List (List Char)),
      partition.join = text.data ∧
      IsAlternatingPartition partition ∧
      result.data = joinLists (List.map TransformChunk partition)
do
  sorry
```

## Mantas review: 
 - I checked the helpers with unit tests, they work as expected.
 - The `joinLists` helper initially had a bug where the arguments to `foldl` were swapped, causing the list to be reversed. This has been fixed to `xss.foldl (fun acc xs => acc ++ xs) []` which correctly concatenates in order.
 - The `IsAlternatingPartition` looks complex but valid Lean recursive-like Prop def.
 - Otherwise LGTM


## 7. sum_squares

This function will take a list of integers. For all entries in the list, the function shall square the integer entry if its index is a
multiple of 3 and will cube the integer entry if its index is a multiple of 4 and not a multiple of 3. The function will not
change the entries in the list whose indexes are not a multiple of 3 or 4. The function shall then return the sum of all entries.


### Spec:


```
method sum_squares (lst: List Int) return (res: Int)
  ensures
    let term := fun (i : Nat) =>
      if i % 3 = 0 then
        lst[i]! ^ 2
      else if i % 4 = 0 then
        lst[i]! ^ 3
      else
        lst[i]!;
    res = ((List.range lst.length).map term).sum
  do
    sorry
```

-- If you allow changing only the single line
--   res = (List.range lst.length).map term |>.sum
-- to
--   res = ((List.range lst.length).map term).sum
-- the method below (a standard prefix-sum loop with appropriate invariants)
-- can be verified automatically with `loom_solve`. Alternatively, providing
-- a global alias `def sum := List.sum` or a macro making `x |>.sum` rewrite
-- to `List.sum x` before the method would also fix elaboration without
-- changing the mathematical meaning.

### Updated spec:

1. Changed from pipe syntax to `.sum`. Not too sure about this one..

## Mantas review:
- The complaint claims `|>.sum` syntax causes elaboration issues in Loom specs. I tested `|>.sum` in standard Lean 4 and it works correctly, equivalent to `(term).sum`.
- Difference: `x |> f` applies `f` to `x`. `x |>.f` applies `f` to `x` (like method dot notation but at the end of a chain). Normal bracketing `f(x)` or `(x).f` is standard.
- The GPT complaint might be hallucinating an environment limitation, but to be safe and avoid potential toolchain-specific parsing issues, let's will switch to standard parens `((...).map term).sum`.


```
method sum_squares (lst: List Int) return (res: Int)
  ensures
    let term := fun (i : Nat) =>
      if i % 3 = 0 then
        lst[i]! ^ 2
      else if i % 4 = 0 then
        lst[i]! ^ 3
      else
        lst[i]!;
    res = ((List.range lst.length).map term).sum
  do
    sorry
```

## 8. words_in_sentence

You are given a string representing a sentence,
the sentence contains some words separated by a space,
and you have to return a string that contains the words from the original sentence,
whose lengths are prime numbers,
the order of the words in the new string should be the same as the original one.

### Spec:

```
method words_in_sentence (sentence: String) return (result: String)
  require 1 ≤ sentence.length
  require sentence.length ≤ 100
  require sentence.all (fun x => Char.isAlpha x ∨ x = ' ')
  ensures result = String.join ((sentence.splitOn).filter (fun w => Nat.Prime w.length))
  do
```

### GPT5 complain:

```
-- ESCALATE: The given specification's postcondition uses `String.join` with no separator,
-- which concatenates the filtered words without spaces (e.g., "go" ++ "for" = "gofor").
-- The failing test expects a space-separated output "go for", which contradicts the
-- specification. Since we were instructed not to modify the specification above `do`,
-- the method and proof are correct with respect to the spec, but the provided test case
-- does not match the spec's semantics.
```

### Updated spec:

1. Replace String.join with String.intercalate " "

```
method words_in_sentence (sentence: String) return (result: String)
  require 1 ≤ sentence.length
  require sentence.length ≤ 100
  require sentence.all (fun x => Char.isAlpha x ∨ x = ' ')
  ensures result = String.intercalate " " ((sentence.splitOn).filter (fun w => Nat.Prime w.length))
  do
    sorry
```

## Mantas review: 
 - Validated via unit tests that `String.intercalate " "` correctly joins words with spaces, e.g. `["go", "for"]` -> `"go for"`.
 - Validated that `String.join` concatenates without spaces (`"gofor"`), which contradicts the problem description "the sentence contains some words separated by a space".
 - The change to `String.intercalate " "` is necessary and correct.
 - LGTM


## 9. order_by_points

Write a function which sorts the given list of integers
in ascending order according to the sum of their digits.
Note: if there are several items with similar sum of their digits,
order them based on their index in original list.

### Spec:

```        
method order_by_points (nums: List Int) return (result: List Int)
  ensures List.Perm nums result
  ensures ∀ i j, i < j → j < result.length →
    let a := result[i]
    let b := result[j]
    let sum_a := digit_sum a
    let sum_b := digit_sum b
    sum_a < sum_b ∨ (sum_a = sum_b ∧ nums.indexOf a < nums.indexOf b)
  do
```

### GPT5 complain:

-- ESCALATE: The given specification requires, for all i < j, that either digit_sum(result[i]) < digit_sum(result[j])
-- or, in case of equal digit sums, nums.indexOf result[i] < nums.indexOf result[j].
-- With duplicate values in `nums`, `nums.indexOf` returns the first occurrence index for both duplicates,
-- making the strict inequality impossible to satisfy for later occurrences. Hence, the spec is unsatisfiable
-- for lists containing duplicates when equal digit sums occur. We implemented a stable insertion sort by the
-- intended key and provided `List.indexOf`, but a full universal proof cannot be completed under this specification.

### Updated spec:

1. Added digit_sum definition
2. Fixed the error with duplicates and the usage of invalid `indexOf` by using permutation of indices instead.

```
def digit_sum (n : Int) : Int :=
  let ds : List Nat :=
    (toString n.natAbs).toList.map (fun c => c.toNat - Char.toNat '0')
  match ds with
  | [] => 0
  | d :: ds' =>
      let tail : Nat := ds'.foldl (fun acc x => acc + x) 0
      if n < 0 then
        Int.ofNat tail - Int.ofNat d
      else
        Int.ofNat (d + tail)

method order_by_points (nums: List Int) return (result: List Int)
  ensures List.Perm nums result
  ensures
    ∃ perm : List Nat,
      perm.length = nums.length ∧
      List.Nodup perm ∧
      List.Perm perm (List.range nums.length) ∧
      (∀ k, k < result.length →
        result[k]! = nums[perm[k]!]!) ∧
      (∀ i j, i < j → j < result.length →
        let a := nums[perm[i]!]!
        let b := nums[perm[j]!]!
        let sa := digit_sum a
        let sb := digit_sum b
        sa < sb ∨ (sa = sb ∧ perm[i]! < perm[j]!))
  do
    sorry

## Mantas review:
- Validated that `digit_sum` correctly implements the problem logic, correctly handling negative numbers as per test cases (e.g. -12 sorts as value 1).
- The use of `perm` avoids the `indexOf` ambiguity for duplicates.
- Added `!` to list accesses (`result[k]!`, `nums[perm[k]!]!`) to ensure compilation



## 10. specialFilter
```


## 10. specialFilter

Write a function that takes an array of numbers as input and returns
the number of elements in the array that are greater than 10 and both
first and last digits of a number are odd (1, 3, 5, 7, 9).

### Spec:

```
def isSpecial (n: Int) : Prop :=
  let firstDigit := (toString n.natAbs).toList[0]!.toNat - '0'.toNat
  let lastDigit := n % 10
  n > 10 ∧ Odd firstDigit ∧ Odd lastDigit


method specialFilter (nums: List Int) return (count: Int)
  ensures count = (nums.filter (fun n => isSpecial n)).length
  do
    sorry
```

### GPT5 complain:

-- ESCALATE: The provided specification uses `List.filter` with a predicate of type `Prop`
-- (`isSpecial : Int → Prop`), but in Lean 4 `List.filter` expects a predicate of type `Int → Bool`.
-- Since we were asked not to modify any code above this `do` block, we cannot change
-- `isSpecial` to return a `Bool`, nor can we alter the `ensures` clause.
--
-- Because of this type mismatch, the term `(nums.filter (fun n => isSpecial n)).length`
-- appearing in `ensures` does not type-check in Lean 4. There is no standard coercion
-- from `Prop` to `Bool`, and redefining a global coercion (e.g., a `CoeeTC Prop Bool`)
-- is both unsafe and disallowed by the problem constraints.
--
-- The correct fix would be to define `isSpecial` as a `Bool`-valued predicate (or rewrite
-- the `ensures` clause to use `decide (isSpecial n)`), but that would modify the header,
-- which the instructions explicitly prohibit.
--
-- Therefore, under the constraint "DO NOT MODIFY the code above the do", this goal is
-- not solvable in Lean 4 as written. If you allow changing the header, I can provide
-- a fully verified solution immediately (with `isSpecial : Int → Bool`, and a proof that
-- the implementation meets the specification).
--
-- Returning a dummy value to keep the method syntactically complete; verification will fail
-- until the header is adjusted.

## Mantas review:
- Agreed, LGTM

### Updated spec:

1. Updated isSpecial to return Bool instead of Prop.

```
def isSpecial (n: Int) : Bool :=
  let firstDigit := (toString n.natAbs).toList[0]!.toNat - '0'.toNat
  let lastDigit := n % 10
  n > 10 && Odd firstDigit && Odd lastDigit

method specialFilter (nums: List Int) return (count: Int)
  ensures count = (nums.filter (fun n => isSpecial n)).length
  do
    sorry
```

## 11. get_max_triples

You are given a positive integer n. You have to create an integer array a of length n.
For each i (1 ≤ i ≤ n), the value of a[i] = i * i - i + 1.
Return the number of triples (a[i], a[j], a[k]) of a where i < j < k,
and a[i] + a[j] + a[k] is a multiple of 3.


### Spec:

```
method get_max_triples (n: ℕ) return (res: ℕ)
  ensures res = ({ (i, j, k) | 1 ≤ i ∧ i < j ∧ j < k ∧ k ≤ n ∧ ((i * i - i + 1) + (j * j - j + 1) + (k * k - k + 1)) % 3 = 0 } : Finset (ℕ × ℕ × ℕ)).card
  do
    sorry
```

### GPT5 complain:

-- ESCALATE: The ensures clause uses a Finset comprehension over the infinite type ℕ × ℕ × ℕ.
-- In Lean/Mathlib, the notation `{ x | P x } : Finset α` elaborates to `Finset.univ.filter P`,
-- which requires an instance `[Fintype α]`. There is no (and cannot be) a `Fintype` instance
-- for `ℕ × ℕ × ℕ` since ℕ is infinite. Consequently, the ensures clause does not typecheck
-- and the method body cannot be verified against it without modifying the specification.
--
-- As requested, we did not modify any code above the `do`. However, this specification
-- is ill-typed in Lean. The mathematically correct way to express this finite set of triples
-- is to build a Finset by restricting the domain to bounded indices (e.g., using
-- `Finset.range` products and filtering), or to use `Set` with `Finite` and `Nat.card`.
--
-- If the ensures clause were changed to:
--   ensures res = ((Finset.range (n+1)).product (Finset.range (n+1))).product (Finset.range (n+1))
--                  |>.filter (fun ⟨i, ⟨j, k⟩⟩ => 1 ≤ i ∧ i < j ∧ j < k ∧ k ≤ n ∧
--                    ((i*i - i + 1) + (j*j - j + 1) + (k*k - k + 1)) % 3 = 0).card
-- then the specification would typecheck and we could prove it.
--
-- Summary of attempted fix:
-- - We derived the arithmetic classification: for i mod 3,
--     a[i] = i^2 - i + 1 ≡ 0 (mod 3) iff i ≡ 2 (mod 3), else ≡ 1 (mod 3).
-- - Hence, triples with sum ≡ 0 (mod 3) are exactly:
--     * all-three indices ≡ 2 (mod 3), or
--     * all-three indices ≢ 2 (mod 3).
--   So res = C(count_{i ∈ [1..n], i ≡ 2 (mod 3)}, 3) + C(count_{i ∈ [1..n], i ≢ 2 (mod 3)}, 3).
-- - We can implement and verify this counting with a loop and invariants.
-- - But we cannot tie it to the current ensures clause because it is ill-typed.
--
-- Please allow changing the ensures clause to a Finset over bounded ranges, and I will
-- provide a complete, verified implementation and proof.
--
-- Placeholder (unreachable due to ill-typed ensures clause):

## Mantas review:
  - Very neat, looks great to me!

### Updated spec:

```
method get_max_triples (n : Nat) return (res : Nat)
  ensures
    res =
      (((Finset.range (n+1)).product (Finset.range (n+1))).product (Finset.range (n+1))
        |>.filter (fun p =>
          let i := p.1.1
          let j := p.1.2
          let k := p.2
          1 ≤ i ∧ i < j ∧ j < k ∧ k ≤ n ∧
          (((i*i - i + 1) + (j*j - j + 1) + (k*k - k + 1)) % 3 = 0)
        )).card
  do
    sorry
```

## 12. bf

There are eight planets in our solar system: the closest to the Sun
is Mercury, the next one is Venus, then Earth, Mars, Jupiter, Saturn,
Uranus, Neptune.
Write a function that takes two planet names as strings planet1 and planet2.
The function should return a tuple containing all planets whose orbits are
located between the orbit of planet1 and the orbit of planet2, sorted by
the proximity to the sun.
The function should return an empty tuple if planet1 or planet2
are not correct planet names.

### Spec:

```
method bf (planet1: String) (planet2: String) return (res: List String)
  ensures
    let planets := ["Mercury", "Venus", "Earth", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune"]
    if planet1 ∉ planets ∨ planet2 ∉ planets then
      res = []
    else
      let index1 := planets.indexOf planet1
      let index2 := planets.indexOf planet2
      let minIdx := min index1 index2
      let maxIdx := max index1 index2
      (∀ str ∈ res, str ∈ planets) ∧
      (∀ planet ∈ planets, planet ∈ res ↔ planets.indexOf planet < maxIdx ∧ minIdx < planets.indexOf planet) ∧
      res.Sorted (fun a b => planets.indexOf a < planets.indexOf b)
  do
```

### GPT5 complain:

-- ESCALATE:
-- The given specification uses `planets.indexOf` within the `ensures` block and in the method body,
-- but Lean's environment (with the provided imports) does not define `List.indexOf`.
-- The problem statement requested that any helper lemmas be defined AFTER the method definition,
-- but because the `ensures` clause (which cannot be modified) already references `List.indexOf`,
-- that function must exist BEFORE the method is elaborated; otherwise, Lean fails at parsing the method.
-- In the previous attempt, I defined `List.indexOf` after the method, which caused "Invalid field `indexOf`" errors.
-- Moving `List.indexOf` before the method would fix these errors, but it contradicts the instruction to place
-- helper definitions only after the method.
--
-- Additionally, proving `res.Sorted (fun a b => planets.indexOf a < planets.indexOf b)` generically requires
-- a lemma that filtering preserves `List.Sorted` for an arbitrary relation.
-- While such a lemma is straightforward, Mathlib's `List.Sorted` structure interacts with `Pairwise`, and
-- without using the built-in lemmas (e.g., `List.Sorted.sublist`) that do not appear in this environment,
-- a custom proof becomes intricate and led to type mismatches and timeouts.
--
-- Summary of learnings:
-- 1) The specification relies on `List.indexOf` being in scope during method parsing. Since it isn't provided
--    by imports here, it must be defined before the method.
-- 2) The constraint to place helper lemmas after the method conflicts with point (1).
-- 3) Discharging the Sorted postcondition is non-trivial without existing library lemmas and requires
--    a careful reconstruction of `List.Sorted` proofs, which is error-prone and can easily timeout.
--
-- To proceed successfully, I recommend allowing the definition of `List.indexOf` (or importing the appropriate
-- module that defines it) BEFORE the method, and permitting helper lemmas that establish filtering preserves
-- sortedness. With those adjustments, the proof can be completed using a combination of `loom_solve` and
-- small interactive steps.

## Mantas review:
 - LGTM

### Updated spec:

1. Rewrote the spec without indexOf which doesn't exist in Lean.

```
method bf (planet1 : String) (planet2 : String) return (res : List String)
  ensures
    let planets : List String :=
      ["Mercury","Venus","Earth","Mars","Jupiter","Saturn","Uranus","Neptune"]
    let orbitIdx : String → Option Nat :=
      fun p =>
        match p with
        | "Mercury" => some 0
        | "Venus"   => some 1
        | "Earth"   => some 2
        | "Mars"    => some 3
        | "Jupiter" => some 4
        | "Saturn"  => some 5
        | "Uranus"  => some 6
        | "Neptune" => some 7
        | _         => none
    match orbitIdx planet1, orbitIdx planet2 with
    | some i1, some i2 =>
        let lo := Nat.min i1 i2
        let hi := Nat.max i1 i2
        -- all planets strictly between them, already in sun order:
        res = (planets.drop (lo + 1)).take (hi - lo - 1)
    | _, _ =>
        res = []
  do
    sorry
```

## Mantas review:
- LGTM


## 13. sorted_list_sum

Write a function that accepts a list of strings as a parameter,
deletes the strings that have odd lengths from it,
and returns the resulted list with a sorted order,
The list is always a list of strings and never an array of numbers,
and it may contain duplicates.
The order of the list should be ascending by length of each word, and you
should return the list sorted by that rule.
If two words have the same length, sort the list alphabetically.
The function should return a list of strings in sorted order.
You may assume that all words will have the same length.

### Spec:

```
method sorted_list_sum (lst: List String) return (res: List String)
  ensures Multiset.ofList res = Multiset.ofList (lst.filter (fun s => Nat.Even s.length))
  ensures List.Sorted (fun s1 s2 => s1.length < s2.length ∨ (s1.length = s2.length ∧ s1 ≤ s2)) res
  do
    sorry
```

### GPT5 complain:

-- ESCALATE: The method specification uses the constant `Nat.Even`, but in this environment
-- it is not available before the method is elaborated (the header forbids adding any
-- helper definitions above the `do`). This causes the method to fail to parse, as seen in
-- the reported errors. Additionally, the library lemmas for `List.mergeSort` / `List.qsort`
-- have differing names across Lean/mathlib versions, so the hints used above do not resolve
-- automatically in this setup.
--
-- Learnings and next steps:
-- 1) To make the specification parsable, we need `Nat.Even` to be defined before the method,
--    e.g., by aliasing it to `Even` or `fun n => n % 2 = 0`. However, the user request
--    explicitly forbids modifying anything above the `do`, which includes adding such
--    helper definitions before the method. Without this alias, the ensures clause cannot
--    elaborate (Unknown constant `Nat.Even`).
-- 2) Sorting proof support in this environment depends on the exact lemma names provided
--    by the installed libraries. A robust solution would add helper lemmas (e.g., showing
--    that `qsort` preserves multisets and produces a `Sorted` list for our comparator)
--    and register them as `[solverHint]`, but these must be added after the method.
-- 3) If the restriction about not adding code before `do` can be relaxed to allow
--    defining `Nat.Even` (e.g., `namespace Nat; def Even (n : Nat) : Prop := n % 2 = 0; end`),
--    then the proof obligations can be discharged using `List.qsort` together with
--    suitable lemmas on `Sorted` and permutation, completing the verification with
--    `loom_solve`.

## Mantas review:
 - Change looks good, rest of escalation looks weird.

### Updated spec:

1. Changed Nat.Even

```
method sorted_list_sum (lst : List String) return (res : List String)
  ensures
    Multiset.ofList res =
      Multiset.ofList (lst.filter (fun s => s.length % 2 = 0))
  ensures
    List.Sorted
      (fun s1 s2 =>
        s1.length < s2.length ∨ (s1.length = s2.length ∧ s1 ≤ s2))
      res
  do
    sorry
```

## 14. x_or_y

A simple program which should return the value of x if n is
a prime number and should return the value of y otherwise.


### Spec:

```
method x_or_y (n: Int) (x: Int) (y: Int) return (res: Int)
  ensures res = x ↔ Nat.Prime n.toNat
  ensures res = y ↔ (¬ Nat.Prime n.toNat ∨ n ≤ 1)
  do
    sorry
```

### GPT5 complain:

-- ESCALATE:
-- The given specification is inconsistent for arbitrary inputs x and y.
-- In the branch where Nat.Prime n.toNat holds, the second postcondition reduces to:
--    res = y ↔ (¬ True ∨ n ≤ 1)  ↔  res = y ↔ n ≤ 1.
-- But prime implies n.toNat ≥ 2, hence n ≤ 1 is false. Therefore we must prove:
--    res = y ↔ False,
-- which is equivalent to res ≠ y. However res is defined to be x in this branch,
-- and there is no precondition that x ≠ y. If x = y, then res = y is true, while
-- the right-hand side is False, contradicting the equivalence. This shows the VCs
-- are unsatisfiable under the current specification for general x, y.
-- A consistent specification would be:
--   ensures res = x ↔ Nat.Prime n.toNat
--   ensures res = y ↔ ¬ Nat.Prime n.toNat
-- or alternatively adding a precondition x ≠ y.
-- Since we are not allowed to modify the header/spec, the proof cannot be completed.

## Mantas review: 
 - LGTM

### Updated spec:

1. ∨ n ≤ 1 not needed in the 2nd postcond
2. Added a precondition 

```
method x_or_y (n: Int) (x: Int) (y: Int) return (res: Int)
  require x ≠ y
  ensures res = x ↔ Nat.Prime n.toNat
  ensures res = y ↔ ¬ Nat.Prime n.toNat
  do
    sorry
```

## 15. even_odd_count

Given an integer. return a tuple that has the number of even and odd digits respectively.


### Spec:

```
method even_odd_count (num: Int) return (res: Int × Int)
  ensures res.1 = ((Nat.digits 10 |num|.toNat).filter (fun d => d % 2 = 0)).length.toInt
  ensures res.2 = ((Nat.digits 10 |num|.toNat).filter (fun d => d % 2 ≠ 0)).length.toInt
  do
```

### GPT5 complain:
-- ESCALATE: The specification above uses `.length.toInt`, which requires a definition `Nat.toInt`.
-- In this environment, `Nat.toInt` does not exist, causing elaboration failure at the ensures lines.
-- The prompt constraints forbid adding helper definitions BEFORE the `do`, but Lean needs `Nat.toInt`
-- to exist when elaborating the ensures. To proceed, we need to define `Nat.toInt := Int.ofNat`
-- before this method (or the header must be adjusted to avoid `.toInt`).
-- Without relaxing that constraint, verification cannot succeed.

## Mantas review:
 - LGTM
### Updated spec:

```
method even_odd_count (num: Int) return (res: Int × Int)
  ensures res.1 = Int.ofNat ((Nat.digits 10 |num|.toNat).filter (fun d => d % 2 = 0)).length
  ensures res.2 = Int.ofNat ((Nat.digits 10 |num|.toNat).filter (fun d => d % 2 ≠ 0)).length
  do
    sorry
```

## 16. int_to_mini_roman

Given a positive integer, obtain its roman numeral equivalent as a string,
and return it in lowercase.
Restrictions: 1 <= num <= 1000

### Spec:

```
method int_to_mini_roman (num: ℕ) return (result: String)
  require 1 ≤ num ∧ num ≤ 1000
  ensures result.data.all (fun c => c.isLower)
  ensures isValidRoman result ∧ romanToDecimal result = num
  do
```

### GPT5 complain:

-- ESCALATE: As explained in the method body, I cannot provide working solver hints
-- or helper lemmas without the actual generator or the internal semantics of
-- `isValidRoman` and `romanToDecimal`. Any guessed names (e.g., isValidRoman_decimalToRomanLower)
-- were not found in this environment.

## Mantas review:
- Verified the logic with unit tests. `romanToDecimal` and `isValidRoman` helpers work correctly for standard inputs and edge cases.
- LGTM.

### Updated spec:

1. Add helpers definitions

```
def dropN {α : Type} : List α → Nat → List α
| xs, 0 => xs
| [], _ => []
| (_ :: t), (k + 1) => dropN t k

/-- Map roman chars (lowercase) to values. Unknown chars map to 0. -/
def romanCharToValue : Char → Nat
| 'i' => 1
| 'v' => 5
| 'x' => 10
| 'l' => 50
| 'c' => 100
| 'd' => 500
| 'm' => 1000
| _   => 0

/-- Legal subtractive pairs. -/
def validSubtractivePairs : List (Char × Char) :=
[('i','v'), ('i','x'), ('x','l'), ('x','c'), ('c','d'), ('c','m')]

/-- Max allowed repetitions for each character. -/
def maxRepetitions : Char → Nat
| 'i' | 'x' | 'c' | 'm' => 3
| 'v' | 'l' | 'd'       => 1
| _                   => 0

/-- Count consecutive repetitions of `c`, given that the current run has length `n`. -/
def countRepetitions : List Char → Char → Nat → Nat
| [],        _, n => n
| (h :: t),  c, n => if h = c then countRepetitions t c (n + 1) else n

/-- Check whether (a,b) is one of the valid subtractive pairs (no `∈` needed). -/
def isValidSubPair : Char → Char → Bool
| a, b =>
  let rec go : List (Char × Char) → Bool
  | [] => false
  | ((x,y) :: ps) =>
      if (x = a ∧ y = b) then true else go ps
  go validSubtractivePairs

/-- Validate repetition rules. -/
partial def validRepetition : List Char → Bool
| [] => true
| c :: rest =>
  let mx  := maxRepetitions c
  let cnt := countRepetitions rest c 1
  -- `cnt ≤ mx` is a Prop; use `decide` to turn it into Bool if needed.
  -- If your Loom build treats `≤` as Bool already, you can drop `decide`.
  (decide (cnt ≤ mx)) && validRepetition (dropN rest (cnt - 1))

/-- Validate subtractive order rules. -/
partial def validSubtractiveOrder : List Char → Bool
| []        => true
| [_]       => true
| c1 :: c2 :: rest =>
  let v1 := romanCharToValue c1
  let v2 := romanCharToValue c2
  if decide (v1 < v2) then
    isValidSubPair c1 c2 && validSubtractiveOrder rest
  else if (v1 = 0 ∨ v2 = 0) then
    false
  else
    validSubtractiveOrder (c2 :: rest)

/-- Check whether a string is a valid lowercase roman numeral. -/
def isValidRoman (s : String) : Bool :=
  s.data.all (fun c => decide (romanCharToValue c ≠ 0)) &&
  validRepetition s.data &&
  validSubtractiveOrder s.data

/-- Convert roman chars to decimal (assumes valid roman structure). -/
partial def romanToDecimalAux : List Char → Nat
| [] => 0
| [c] => romanCharToValue c
| c1 :: c2 :: rest =>
  let val1 := romanCharToValue c1
  let val2 := romanCharToValue c2
  if decide (val1 < val2) then
    (val2 - val1) + romanToDecimalAux rest
  else
    val1 + romanToDecimalAux (c2 :: rest)

/-- Convert a valid lowercase roman numeral string to Nat. -/
def romanToDecimal (s : String) : Nat :=
  romanToDecimalAux s.data

method int_to_mini_roman (num: Nat) return (result: String)
  require 1 ≤ num ∧ num ≤ 1000
  ensures result.data.all (fun c => c.isLower)
  ensures isValidRoman result ∧ romanToDecimal result = num
  do
    sorry
```

## 17. do_algebra

Given two lists operator, and operand. The first list has basic algebra operations, and
the second list is a list of integers. Use the two given lists to build the algebric
expression and return the evaluation of this expression.

### Spec:

```
def mergeAlternately (operand : List Nat) (operator : List String) : (List Nat × List String) := (operand, operator)


method do_algebra (operator: List String) (operand: List Nat) return (res: Int)
  require operator.length = operand.length - 1
  require 0 < operator.length
  require operand.all (fun n => 0 ≤ n)
  ensures evalArith_precedence (mergeAlternately operand operator) res
  do
```

### GPT5 complain:
-- ESCALATE: The ensures clause refers to `evalArith_precedence` provided
-- by the testing framework. To prove the postcondition, we need a computable
-- function from the operator/operand lists whose value is provably equal to
-- the semantics encoded by `evalArith_precedence`. However, the framework
-- does not expose the corresponding evaluator function, and the problem
-- prohibits adding any helper definitions before this method (which is where
-- we would normally define and then call such a function).
--
-- In the previous attempts, defining our own evaluator above the method
-- violated the header constraint and caused name resolution issues; defining
-- it below the method makes it unavailable in the body due to Lean’s
-- forward reference restrictions. Without access to the library’s
-- evaluation function or the internal definition of `evalArith_precedence`,
-- we cannot connect a computed result to the required semantics.
--
-- If the framework provided a function like
--   evalArithPrecedenceEval : (List Nat × List String) → Int
-- together with the lemma
--   ∀ p, evalArith_precedence p (evalArithPrecedenceEval p),
-- then we could write:
--   let res := evalArithPrecedenceEval (mergeAlternately operand operator)
-- and discharge the postcondition automatically.
--
-- Given the current constraints, we leave a trivial placeholder value here.
-- A proper fix requires either:
--   1) the name of the evaluator function exposed by the framework, or
--   2) permission to add helper definitions before the method.

## Mantas review:
- Validated `mergeAlternately` and `applyOp` with unit tests.
- The inductive definitions correctly define standard arithmetic precedence.
- LGTM.

### Updated spec:

1. Added missing helpers

```
def mergeAlternately : List Nat → List String → List String
| [], [] => []
| [], y :: ys => y :: mergeAlternately [] ys
| x :: xs, [] => x.repr :: mergeAlternately xs []
| x :: xs, y :: ys => x.repr :: y :: mergeAlternately xs ys

def applyOp (x y : Int) : String → Option Int
| "+"  => some (x + y)
| "-"  => some (x - y)
| "*"  => some (x * y)
| "//" => if y == 0 then none else some (x / y)
| "**" =>
  if x < 0 then
    none
  else
    some (Int.ofNat ((Int.toNat x) ^ (Int.toNat y)))
| _    => none

inductive evalArith_pass : List String → Int → Prop
| num {s : String} {n : Nat} (h : s.toNat! = n) :
    evalArith_pass [s] (Int.ofNat n)
| binOp {ts1 ts2 : List String} {op : String} {r1 r2 r : Int}
    (h1 : evalArith_pass ts1 r1)
    (h2 : evalArith_pass ts2 r2)
    (hop : applyOp r1 r2 op = some r) :
    evalArith_pass (ts1 ++ op :: ts2) r

inductive evalArith_exp : List String → Int → Prop
| of_pass {ts : List String} {r : Int} (h : evalArith_pass ts r) :
    evalArith_exp ts r
| step {ts1 ts2 : List String} {r1 r2 r : Int}
    (h1 : evalArith_exp ts1 r1)
    (h2 : evalArith_exp ts2 r2)
    (hop : applyOp r1 r2 "**" = some r) :
    evalArith_exp (ts1 ++ "**" :: ts2) r

inductive evalArith_mul : List String → Int → Prop
| of_exp {ts : List String} {r : Int} (h : evalArith_exp ts r) :
    evalArith_mul ts r
| step {ts1 ts2 : List String} {r1 r2 r : Int}
    (h1 : evalArith_mul ts1 r1)
    (h2 : evalArith_mul ts2 r2)
    (hop : applyOp r1 r2 "*" = some r ∨ applyOp r1 r2 "//" = some r) :
    evalArith_mul (ts1 ++ "*" :: ts2) r

inductive evalArith_add : List String → Int → Prop
| of_mul {ts : List String} {r : Int} (h : evalArith_mul ts r) :
    evalArith_add ts r
| step {ts1 ts2 : List String} {r1 r2 r : Int}
    (h1 : evalArith_add ts1 r1)
    (h2 : evalArith_add ts2 r2)
    (hop : applyOp r1 r2 "+" = some r ∨ applyOp r1 r2 "-" = some r) :
    evalArith_add (ts1 ++ "+" :: ts2) r

def evalArith_precedence (ts : List String) (r : Int) : Prop :=
  evalArith_add ts r

method do_algebra (operator: List String) (operand: List Nat) return (res: Int)
  require operator.length = operand.length - 1
  require 0 < operator.length
  require operand.all (fun n => 0 ≤ n)
  ensures evalArith_precedence (mergeAlternately operand operator) res
  do
    sorry
```

## 18. how_many_times

Find how many times a given substring can be found in the original string. Count overlaping cases.

### Spec:

```
method how_many_times (string: String) (substring: String) return (res: ℕ)
  ensures string.length < substring.length → res = 0
  ensures string.length = substring.length → (if string = substring then res = 1 else res = 0)
  ensures substring.length < string.length →
    res =
      let subtring_start_idx := {i: Nat | i ≤ string.length - substring.length};
      let substring_occurrences := {i ∈ subtring_start_idx | (string.take (i + substring.length)).drop i = substring };
      substring_occurrences.toFinset.card
  do
```

### GPT5 complain:

-- ESCALATE: The given specification (third ensures clause) counts occurrences over
-- all start indices i ≤ string.length - substring.length. When substring = "",
-- this set includes both i = 0 and i = string.length, so its cardinal is string.length + 1.
-- External tests expecting `how_many_times "a" "" = 1` contradict the specification,
-- which requires returning 2 in that case. The method and proof above strictly follow
-- the provided specification text and verify successfully against it.

## Mantas review:
 - LGTM
### Updated spec:

1. Handle the case when substring is = "" by adding a condition on `substring.length`

```
method how_many_times (string : String) (substring : String) return (res : Nat)
  ensures substring.length = 0 → res = 1
  ensures substring.length > 0 ∧ string.length < substring.length → res = 0
  ensures substring.length > 0 ∧ string.length = substring.length → (if string = substring then res = 1 else res = 0)
  ensures substring.length > 0 ∧ substring.length < string.length →
  res =
      let subtring_start_idx := {i: Nat | i ≤ string.length - substring.length};
      let substring_occurrences := {i ∈ subtring_start_idx | (string.take (i + substring.length)).drop i = substring };
      substring_occurrences.toFinset.card
  do
    sorry
```


## 19. largest_divisor

For a given number n, find the largest number that divides n evenly, smaller than n

### Spec:

```
method largest_divisor (n: ℕ) return (res: ℕ)
  require 0 < n
  ensures 0 < res
  ensures res ∣ n
  ensures res < n
  ensures ∀ x, x ∣ n → x ≠ n → x ≤ res
  do
```
### GPT5 complain:

-- ESCALATE: The given specification is unsatisfiable for n = 1.
-- Explanation:
--  - The precondition allows n = 1 (since it only requires 0 < n).
--  - The postconditions require a positive res such that res ∣ n and res < n.
--    For n = 1, there is no positive natural number strictly less than 1 that divides 1.
--    Hence, the postconditions cannot be met for n = 1.
-- Because the method must prove its postconditions for all n satisfying 0 < n,
-- this makes the specification inconsistent. The proof obligations include a subgoal `1 < n`
-- when initializing `res := 1`, which is not derivable from `0 < n`.
-- To make the problem solvable, the precondition should be strengthened to `1 < n`.
-- Below, we still provide the intended algorithm for n ≥ 2, but the overall
-- proof cannot be completed under the current precondition.

## Mantas review:
 - Nice catch, LGTM

### Updated spec:

1. Updated precond to n > 1

```
method largest_divisor (n: ℕ) return (res: ℕ)
  require 1 < n
  ensures 0 < res
  ensures res ∣ n
  ensures res < n
  ensures ∀ x, x ∣ n → x ≠ n → x ≤ res
  do
    sorry
```

## 20. sort_third

This function takes a list l and returns a list l' such that
l' is identical to l in the indicies that are not divisible by three, while its values at the indices that are divisible by three are equal
to the values of the corresponding indicies of l, but sorted.

### Spec:

```
method sort_third (l: List Int) return (result: List Int)
  ensures l.length = result.length
  ensures ∀ i, i < l.length → i % 3 ≠ 0 → l[i]! = result[i]!
  ensures
    let every_third_idx := (List.range l.length).filter (fun i => i % 3 = 0)
    let every_third_val_in_result := every_third_idx.map (fun i => result[i]!)
    List.Sorted (· ≤ ·) every_third_val_in_result
  ensures
    let every_third_idx := (List.range l.length).filter (fun i => i % 3 = 0)
    let every_third_val_in_result := every_third_idx.map (fun i => result[i]!)
    let every_third_val := every_third_idx.map (fun i => l[i]!)
    toMultiset every_third_val = toMultiset every_third_val_in_result
  do
```

### GPT5 complain:

-- ESCALATE: The provided specification uses `toMultiset` as a bare identifier
-- (outside any namespace) and requires nontrivial reasoning about
-- prefix counts of filtered ranges, sortedness of selected subsequences,
-- and multiset equality after reconstruction. In this Loom/Velvet setting,
-- the spec block cannot be modified, but its use of `toMultiset` does not
-- resolve to any available symbol in Mathlib or the CaseStudies setup.
-- 
-- I attempted multiple designs:
-- 1) Build `result` by mapping over `List.range n` and index into a sorted
--    list of every-third values using the count of previous divisible-by-3 indices.
--    This ran into missing lemmas like `List.length_filter`, `List.sublist_range`,
--    and solver limitations proving `j < length`.
-- 2) Define helper lemmas for `Multiset.sort`, lengths, and conversions.
--    This hit API mismatches (e.g., `Multiset.sort` requires a relation argument)
--    and the spec's use of `toMultiset` clashed with Mathlib's `List.toMultiset`.
-- 3) Reconstruct `result` via a recursive function consuming the sorted thirds.
--    This would need substantial invariants and proofs for the ensures,
--    but Loom’s SMT automation struggled with these quantified properties.
--
-- The blocking issue is the unresolved `toMultiset` in the ensures:
-- it is required verbatim by the spec string, but not defined/imported here.
-- Without changing the spec header (forbidden), there is no symbol
-- `toMultiset` available to use or reference in proofs.
--
-- Because of this obstacle and the amount of bespoke library facts
-- needed to complete the proof obligations, I cannot provide a
-- fully verified implementation under the current constraints.
--
-- I recommend either:
-- - Adjusting the spec to use `List.toMultiset` (from Mathlib), or
-- - Allow defining `toMultiset` after the method (as an alias to
--   `List.toMultiset` or `Multiset.ofList`) so the ensures can be
--   interpreted by Lean.
--
-- With that change, I can complete the program and proof using
-- `List.sort (· ≤ ·)` on the extracted thirds and reconstructing the list,
-- with helper lemmas and invariants suitable for Loom.

## Mantas review:
  - Comes up for the 2nd time, LGTM
### Updated spec:

1. Change toMultiset to List.toMultiset

```
method sort_third (l: List Int) return (result: List Int)
  ensures l.length = result.length
  ensures ∀ i, i < l.length → i % 3 ≠ 0 → l[i]! = result[i]!
  ensures
    let every_third_idx := (List.range l.length).filter (fun i => i % 3 = 0)
    let every_third_val_in_result := every_third_idx.map (fun i => result[i]!)
    List.Sorted (· ≤ ·) every_third_val_in_result
  ensures
    let every_third_idx := (List.range l.length).filter (fun i => i % 3 = 0)
    let every_third_val_in_result := every_third_idx.map (fun i => result[i]!)
    let every_third_val := every_third_idx.map (fun i => l[i]!)
    Multiset.ofList every_third_val = Multiset.ofList every_third_val_in_result
  do
    sorry
```

## 21. encode_shift

returns encoded string by shifting every character by 5 in the alphabet.

### Spec:

```
method encode_shift (s: String) return (res: String)
  require ∀ i, i < s.length → (let c := s.get! ⟨i⟩; ('a'.toNat ≤ c.toNat ∧ c.toNat ≤ 'z'.toNat) ∨ ('A'.toNat ≤ c.toNat ∧ c.toNat ≤ 'Z'.toNat))
  ensures res.length = s.length
  ensures ∀ i, i < res.length → (let c := res.get! ⟨i⟩; ('a'.toNat ≤ c.toNat ∧ c.toNat ≤ 'z'.toNat) ∨ ('A'.toNat ≤ c.toNat ∧ c.toNat ≤ 'Z'.toNat))
  ensures ∀ i : Nat, i < s.length → ((s.get! ⟨i⟩).toNat + 5) % 26 = (res.get! ⟨i⟩).toNat
  do

```

### GPT5 complain:

-- ESCALATE: The provided specification is internally inconsistent.
-- The second ensures requires each output character to be in 'A'..'Z' or 'a'..'z'
-- (i.e., codepoints 65..90 or 97..122), while the third ensures requires each output
-- character's `toNat` to be equal to `((input.toNat + 5) % 26)`, which is always in 0..25.
-- These constraints cannot be simultaneously satisfied for non-empty strings in Lean's
-- Char/String model. The implementation above performs the intended Caesar shift and
-- returns the correct strings (e.g., "abc" ↦ "fgh"), but the third ensures cannot be
-- proven without altering the specification to normalize characters by subtracting 'A'
-- or 'a' before applying modulo and then adding the base back.

## Mantas review:
- LGTM but perhaps too complicated to state...
### Updated spec:


```
method encode_shift (s: String) return (res: String)
  require ∀ i, i < s.length → (let c := s.get! ⟨i⟩; ('a'.toNat ≤ c.toNat ∧ c.toNat ≤ 'z'.toNat) ∨ ('A'.toNat ≤ c.toNat ∧ c.toNat ≤ 'Z'.toNat))
  ensures res.length = s.length
  ensures ∀ i, i < res.length → (let c := res.get! ⟨i⟩; ('a'.toNat ≤ c.toNat ∧ c.toNat ≤ 'z'.toNat) ∨ ('A'.toNat ≤ c.toNat ∧ c.toNat ≤ 'Z'.toNat))
  ensures ∀ i : Nat, i < s.length →
    let cin := s.get! ⟨i⟩
    let cout := res.get! ⟨i⟩
    ( ('a'.toNat ≤ cin.toNat ∧ cin.toNat ≤ 'z'.toNat) →
        ( 'a'.toNat ≤ cout.toNat ∧ cout.toNat ≤ 'z'.toNat ∧
          cout.toNat =
            (((cin.toNat - 'a'.toNat + 5) % 26) + 'a'.toNat) ) )
    ∧
    ( ('A'.toNat ≤ cin.toNat ∧ cin.toNat ≤ 'Z'.toNat) →
        ( 'A'.toNat ≤ cout.toNat ∧ cout.toNat ≤ 'Z'.toNat ∧
          cout.toNat =
            (((cin.toNat - 'A'.toNat + 5) % 26) + 'A'.toNat) ) )
  do
    sorry
```

## 22. remove_vowels

remove_vowels is a function that takes string and returns string without vowels.

### Spec:

```
def is_consonant (c: Char): Bool :=
  let vowels := "aeiouAEIOU"
  not (vowels.contains c)

method remove_vowels (string: String) return (result: String)
  ensures result.all (λ c => is_consonant c)
  ensures result.length ≤ string.length
  ensures ∀ c, result.contains c → string.contains c
  ensures ∀ c, string.contains c ∧ is_consonant c → result.contains c
  ensures result = string.filter is_consonant
  do

```

### GPT5 complain:

-- ESCALATE: The given specification uses `String.filter`, which is not
-- provided by Lean's core `String` API in this environment. To satisfy the
-- spec exactly, we need a definition of `String.filter` that matches the
-- intended behavior (keeping exactly the characters satisfying the
-- predicate), and then prove properties connecting `String.filter` to
-- `String.all`, `String.length`, and `String.contains`. However, the problem
-- statement restricts helper definitions and lemmas to occur AFTER the
-- method definition, while Lean requires `String.filter` to be defined
-- BEFORE it is referenced in the method's `ensures` block. Moreover,
-- establishing the necessary properties of `String.contains` and
-- `String.all` for strings in Lean requires unfolding their internal
-- definitions (which involve folds over UTF-8 code units / characters),
-- and proving list-to-string correspondence lemmas that are not readily
-- available here.
--
-- I attempted to define `String.filter` and prove the needed lemmas, but
-- due to the constraints (no modification of code above `do`, and the fact
-- that the `ensures` line references `string.filter` before any helper can
-- be introduced), the verification cannot be completed in this setting.
--
-- With the spec fixed to use existing String APIs (or allowing the
-- definition of `String.filter` before the method), the method body would
-- simply be:
--   return string.filter is_consonant
--
-- and the proof would proceed by lemmas about `String.filter`, `String.all`,
-- `String.contains`, and `String.length`.
--
-- As we cannot define `String.filter` prior to its use in the `ensures`,
-- we conservatively return the input to keep the code syntactically valid,
-- though the proof obligations cannot be discharged under the current
-- constraints.

## Mantas review:
 - Nice, LGTM!

### Updated spec:

1. Modified the last postcondition to compare a list of chars instead of strings. string.data.filter works.

```
def is_consonant (c: Char): Bool :=
  let vowels := "aeiouAEIOU"
  not (vowels.contains c)

method remove_vowels (string : String) return (result : String)
  ensures result.all (λ c => is_consonant c)
  ensures result.length ≤ string.length
  ensures ∀ c, result.contains c → string.contains c
  ensures ∀ c, string.contains c ∧ is_consonant c → result.contains c
  ensures result.data = (string.data.filter is_consonant)
  do
    sorry
```

## 23. vowels_count

Write a function vowels_count which takes a string representing
a word as input and returns the number of vowels in the string.
Vowels in this case are 'a', 'e', 'i', 'o', 'u'. Here, 'y' is also a
vowel, but only when it is at the end of the given word.

### Spec:

```
method vowels_count (string: String) return (res: ℕ)
  require string.data.all (fun c => c.isAlpha)
  ensures res = (string.data.foldl (fun acc c => acc + if "aeiouAEIOU".contains c then 1 else 0) 0) +
                (if string.length > 0 ∧ (string.data.back = 'y' ∨ string.data.back = 'Y') then 1 else 0)
  do
```

### GPT5 complain:

-- ESCALATE: The given specification uses `string.data.back`, but Lean's standard library
-- does not provide `List.back` by default in this environment. To typecheck the spec, we
-- must define `List.back`. However, the instructions require not modifying any code above
-- the `do`, which prevents us from introducing this necessary definition before the method.
-- If allowed, placing the following definition before the method resolves the errors:
--   namespace List
--   @[simp] def back {α} [Inhabited α] (xs : List α) : α :=
--     match xs.reverse with
--     | []     => default
--     | x :: _ => x
--   end List
-- With that in place, the proof below (loom_solve) succeeds.

## Mantas review:
 - LGTM
### Updated spec:

1. Modified the 2nd postcond: sum of vowels + 1 if last character is Y or y (else + 0)

```
method vowels_count (string : String) return (res : Nat)
  require string.data.all (fun c => c.isAlpha)
  ensures
    res =
      (string.data.foldl
        (fun acc c => acc + (if "aeiouAEIOU".contains c then 1 else 0))
        0)
      +
      (match string.data.reverse with
       | [] => 0
       | last :: _ =>
           if last = 'y' ∨ last = 'Y' then 1 else 0)
  do
    sorry
```

## 24. fruit_distribution

In this task, you will be given a string that represents a number of apples and oranges
that are distributed in a basket of fruit this basket contains
apples, oranges, and mango fruits. Given the string that represents the total number of
the oranges and apples and an integer that represent the total number of the fruits
in the basket return the number of the mango fruits in the basket.

### Spec:

```
method fruit_distribution (string: String) (n: ℕ) return (res: ℕ)
  ensures ∃ x y : ℕ, x + y = n - res ∧ (String.join [x.repr, " apples and ", y.repr, " oranges"] = string)
  do
```

### GPT5 complain:

-- ESCALATE: The given postcondition requires that for every input `string : String`,
-- there exist naturals `x y` such that `string = x.repr ++ " apples and " ++ y.repr ++ " oranges"`.
-- This is generally false for arbitrary strings (e.g., strings with non-numeric prefixes,
-- different wording, or leading zeros in numbers). Therefore, without a precondition
-- constraining `string` to exactly that canonical format, the existential
-- in the `ensures` clause cannot be proved in Lean for all inputs.
-- 
-- The implementation above parses the string when it matches the expected format,
-- and returns the mathematically correct number of mangoes `n - (x + y)`. This
-- will pass the functional tests when the input is well-formed (as in the examples),
-- but the universal postcondition proof remains unprovable in general without
-- an appropriate precondition, or an additional axiom equating arbitrary strings
-- to the specified format, which is not allowed by the verification policy.

## Mantas review:
 - LGTM
### Updated spec:

1. The description doesn't say that input is in the format {x} apples and {y} oranges, but the tests assume this. To make this more clear, I added a precondition

```
method fruit_distribution (string : String) (n : Nat) return (res : Nat)
  require ∃ x y : Nat,
    string = String.join [x.repr, " apples and ", y.repr, " oranges"] ∧
    x + y ≤ n

  ensures ∃ x y : Nat,
    string = String.join [x.repr, " apples and ", y.repr, " oranges"] ∧
    x + y ≤ n ∧
    res = n - (x + y)
  do
    sorry
```

## 25. hex_key

You have been tasked to write a function that receives
a hexadecimal number as a string and counts the number of hexadecimal
digits that are primes (prime number, or a prime, is a natural number
greater than 1 that is not a product of two smaller natural numbers).
Hexadecimal digits are 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, A, B, C, D, E, F.
Prime numbers are 2, 3, 5, 7, 11, 13, 17,...
So you have to determine a number of the following digits: 2, 3, 5, 7,
B (=decimal 11), D (=decimal 13).
Note: you may assume the input is always correct or empty string,
and symbols A,B,C,D,E,F are always uppercase.


### Spec:

```
method hex_key (num: String) return (res: Int)
  require 0 < num.length
  ensures res = (num.toList.map (fun c =>
    let val : Nat :=
      if c.isDigit then (c.toNat - '0'.toNat)
      else if c.isUpper then ((c.toNat - 'A'.toNat) + 10)
      else 0;
    if Nat.Prime val then (val : Int) else 0
  )).sum
  do
```
 
### GPT5 complain:

-- ESCALATE: The external tests expect the function to return the COUNT of prime hex digits,
-- e.g., "AB" -> 1, while the required ensures specification mandates the SUM of the numeric
-- values of prime digits (e.g., "AB" -> 11 since B=11). These are incompatible requirements.
-- Additionally, the tests call hex_key "" despite the method's precondition `0 < num.length`.
-- The implementation above strictly satisfies the given ensures specification and verifies
-- with Loom, but cannot make the provided guards pass due to the mismatch between the spec
-- and the tests.

## Mantas review:
 - Nice catch, LGTM

### Updated spec:

1. Updated postcond to count the hexadigits which are prime rather than summing those prime digits.

```
method hex_key (num : String) return (res : Int)
  ensures
    res =
      (num.toList.map (fun c =>
        let val : Nat :=
          if c.isDigit then (c.toNat - '0'.toNat)
          else ((c.toNat - 'A'.toNat) + 10)
        if Nat.Prime val then (1 : Int) else 0
      )).sum
  do
    sorry
```


## 26. sort_array

Given an array of non-negative integers, return a copy of the given array after sorting, you will sort the given array in ascending order if the sum( first index value, last index value) is odd, or sort it in descending order if the sum( first index value, last index value) is even.

### Spec:
 
```
 method sort_array (lst: List ℕ) return (res: List ℕ)
  require lst.length > 0
  ensures res.length = lst.length
  ensures toMultiset res = toMultiset lst
  ensures (lst.head! + lst.getLast!) % 2 = 1 → res.Sorted (· ≤ ·)
  ensures (lst.head! + lst.getLast!) % 2 = 0 → res.Sorted (· ≥ ·)

```

### GPT5 complain:

-- ESCALATE: The given specification line `ensures toMultiset res = toMultiset lst`
-- uses an unqualified identifier `toMultiset`. Within the Loom/Velvet macro
-- expansion, this free identifier is captured as an uninterpreted local variable
-- (see the error logs where `toMultiset : x✝` appears), which makes it impossible
-- to prove any semantic properties about it. We are required not to modify the
-- method header (above `do`), so we cannot qualify this as `List.toMultiset`
-- or define a proper `toMultiset` before the method.
-- Defining `toMultiset` after the method does not help, since the method's
-- generated correctness theorem already binds `toMultiset` as a local constant.
-- Consequently, the obligation `toMultiset res = toMultiset lst` cannot be
-- discharged unless we return `res = lst` (which conflicts with the sorting
-- postconditions), or the identifier is resolved to a proper function before
-- macro expansion.
-- Additionally, the earlier attempt to use `List.mergeSort` failed due to the
-- function's autoParam comparator convention in Mathlib, and several lemma
-- names like `List.perm_mergeSort` / `List.Perm.toMultiset` are not available
-- under these imports. Switching to `List.qsort` provides sortedness but still
-- does not resolve the `toMultiset` identifier issue in the spec.
-- To proceed, the spec must qualify or define `toMultiset` prior to the method
-- (e.g., `def toMultiset (xs : List ℕ) : Multiset ℕ := ...`), or change the
-- spec to use a known identifier (e.g., `res.toMultiset = lst.toMultiset`).
-- Without altering the header, the proof cannot be completed.

## Mantas review:  
 - LGTM

### Updated spec:

1. Change toMultiset to `Multiset.ofList`

```
method sort_array (lst: List ℕ) return (res: List ℕ)
  require lst.length > 0
  ensures res.length = lst.length
  ensures Multiset.ofList res = Multiset.ofList lst
  ensures (lst.head! + lst.getLast!) % 2 = 1 → res.Sorted (· ≤ ·)
  ensures (lst.head! + lst.getLast!) % 2 = 0 → res.Sorted (· ≥ ·)
  do
    sorry
```

## 27. encrypt

Create a function encrypt that takes a string as an argument and
returns a string encrypted with the alphabet being rotated.
The alphabet should be rotated in a manner such that the letters
shift down by two multiplied to two places.

### Spec:

```
method encrypt (str: String) return (result: String)
  ensures result.data.all (fun c => c.isLower) → result.length = str.length
  ensures result.data.all (fun c => c.isLower) →
    ∀ (i : Nat), i < str.length →
      ((result.data[i]!.toNat - 97) + 4) % 26 = (str.data[i]!.toNat - 97)
  do
```
 
### GPT5 complain:

-- ESCALATE: The given specification requires the encrypted result to satisfy
-- ((result[i]-97)+4) % 26 = (str[i]-97), which corresponds to rotating characters
-- backward by 4 positions. However, the external tests provided in the error logs
-- expect a forward rotation by 4 positions (e.g., "hi" ↦ "lm"). These are logically
-- incompatible: for lowercase letters, forward-4 and backward-4 cannot be both satisfied.
-- I implemented and proved the rotation consistent with the provided specification text.
-- If the goal is to match the forward-rotation tests, the postcondition must be updated
-- accordingly (e.g., require (result[i]-97) = (str[i]-97 + 4) % 26). Without changing
-- the postcondition string (as requested), we cannot satisfy both the spec and those tests.

## Mantas review:
 - LGTM

### Updated spec:

1. Updated 2nd postcond to check that result = forward rotation by 4 

```
method encrypt (str: String) return (result: String)
  ensures result.data.all (fun c => c.isLower) → result.length = str.length
  ensures result.data.all (fun c => c.isLower) →
    ∀ (i : Nat), i < str.length →
      (result.data[i]!.toNat - 97) = ((str.data[i]!.toNat - 97) + 4) % 26
  do
    sorry
```

## 28. multiply

Complete the function that takes two integers and returns
the product of their unit digits.
Assume the input is always valid.

### Spec:

```
method multiply (a: Int) (b: Int) return (res: Int)
  ensures res % 10 = (a * b) % 10 ∧
  ((b%10) ≠ 0 → (res % (b%10) = 0 ∧ (res/ (b%10)) % 100 = (a%10))) ∧
  ((a%10) ≠ 0 → (res % (a%10) = 0 ∧ (res/ (a%10)) % 100 = (b%10))) ∧
  ((a%10 = 0) ∨ (b%10 = 0) → result = 0)
  ensures res <= 81
  do
```

### GPT5 complain:

```
-- ESCALATE: The provided specification contains a postcondition referring to `result`
-- instead of the declared return variable `res`:
--   ((a%10 = 0) ∨ (b%10 = 0) → result = 0)
-- In Velvet/Lean, this introduces a fresh, unconstrained variable `result : Nat`
-- in the generated verification conditions, making the goal generally unprovable.
-- All other postconditions are correctly discharged automatically by the SMT solver
-- for the implementation `res = (a % 10) * (b % 10)`.
-- To complete the proof, the specification must use `res` (the actual return value)
-- instead of `result`. Since we are instructed not to modify the header, we stop here.
```

### Updated spec:

1. result -> res change

## Mantas review: 
- Typo, LGTM

```
method multiply (a: Int) (b: Int) return (res: Int)
    ensures res % 10 = (a * b) % 10 ∧
    ((b%10) ≠ 0 → (res % (b%10) = 0 ∧ (res/ (b%10)) % 100 = (a%10))) ∧
    ((a%10) ≠ 0 → (res % (a%10) = 0 ∧ (res/ (a%10)) % 100 = (b%10))) ∧
    ((a%10 = 0) ∨ (b%10 = 0) → res = 0)
    ensures res <= 81
    do
      sorry
```

## 29. count_upper

Given a string s, count the number of uppercase vowels in even indices.

### Spec:

```
method count_upper (s: String) return (res: Int)
  ensures (res = 0 ↔ ∀ i, i < s.toList.length → s.toList[i]! ∉ ['A', 'E', 'I', 'O', 'U'])
  ensures res =
    let uppercase_vowels : List Char := ['A', 'E', 'I', 'O', 'U']
    let count := s.toList.foldrIdx  (fun i c acc =>
      if i % 2 = 0 ∧ c ∈ uppercase_vowels then acc + 1 else acc) 0
    (count : Int)
  do
```

### GPT5 complain:

-- ESCALATE: The specification above is inconsistent and cannot be satisfied by any implementation.
-- Explanation:
--  - The second 'ensures' states that 'res' is exactly the count of uppercase vowels occurring at even indices.
--  - The first 'ensures' states that 'res = 0' if and only if there are no uppercase vowels anywhere in the string
--    (at any index).
--  - These two are contradictory: consider a string with an uppercase vowel at an odd index (e.g., "aE").
--    The count of uppercase vowels at even indices is 0, so the second 'ensures' demands res = 0.
--    However, the first 'ensures' would be false, since there exists an uppercase vowel (at an odd index),
--    violating the equivalence 'res = 0 ↔ ...'.
-- Consequently, the verification conditions generated for the first 'ensures' cannot be proven.
-- If the intent is to count uppercase vowels at even indices, the first 'ensures' should also quantify only over even indices:
--   ensures (res = 0 ↔ ∀ i, i < s.toList.length → i % 2 = 0 → s.toList[i]! ∉ ['A', 'E', 'I', 'O', 'U'])
-- Please provide a corrected specification; then the proof can be completed with 'loom_solve'.

### Updated spec:

1. Change first postcond to check that res = 0 iff there's no upper vowels at EVEN indices (previously it was checking both Odd & Even)

## Mantas review:
 - Nice catch, LGTM

```
method count_upper (s: String) return (res: Int)
  ensures (res = 0 ↔ ∀ i, i < s.toList.length → i % 2 = 0 → s.toList[i]! ∉ ['A', 'E', 'I', 'O', 'U'])
  ensures res =
    let uppercase_vowels : List Char := ['A', 'E', 'I', 'O', 'U']
    let count := s.toList.foldrIdx  (fun i c acc =>
      if i % 2 = 0 ∧ c ∈ uppercase_vowels then acc + 1 else acc) 0
    (count : Int)
  do
    sorry
```

## 30. is_bored

You'll be given a string of words, and your task is to count the number
of boredoms. A boredom is a sentence that starts with the word "I".
Sentences are delimited by '.', '?' or '!'.


### Spec:

```
method is_bored (s: String) return (res: Nat)
  ensures
    let is_sentence_is_boredom (s': String) : Bool :=
      (s'.startsWith "I " ∨ s'.startsWith " I") ∧ '.' ∉ s'.data ∧ '?' ∉ s'.data ∧ '!' ∉ s'.data;
    let split_sentences (s : String) : List String :=
      let isSep (c : Char) : Bool := (c == '.') || (c == '?') || (c == '!')
      let rec go (cs : List Char) (acc : List Char) (out : List (List Char)) : List (List Char) :=
        match cs with
        | [] => (List.reverse acc :: out).reverse
        | c :: cs' =>
          if isSep c then
            let sentence := List.reverse (c :: acc)
            go cs' [] (sentence :: out)
          else
            go cs' (c :: acc) out
      (go s.data [] []).map String.mk
    res = (split_sentences s).foldl (fun acc sentence =>
      if is_sentence_is_boredom sentence then acc + 1 else acc) 0
  do
    sorry
```
 
### GPT5 complain:
-- ESCALATE: The specification includes a local `let rec go` inside the `ensures` block.
-- Loom's weakest-precondition generation turns that recursive `let` into a metavariable
-- witness (`?m._`) and introduces `sorryAx` internally for that witness, which is disallowed
-- by the checker. Because we must keep the exact ensures text (including the local `let rec`),
-- the proof obligations cannot be discharged without the forbidden axiom. The body returns
-- exactly the postcondition expression (textually identical), but the WP comparison still
-- fails since the ensures-side `go` is represented as a meta and not definitionally equal to
-- the body-side `go`. Without modifying the ensures, this appears infeasible to verify under
-- the current Loom/Velvet constraints.

## Mantas review:
- Removed the annoying "Top-level helper" comments
- Otherwise LGTM

### Updated spec:

```
def isSentenceSep (c : Char) : Bool := c == '.' || c == '?' || c == '!'

def splitSentencesGo (cs : List Char) (acc : List Char) (out : List (List Char)) : List (List Char) :=
  match cs with
  | [] => (List.reverse acc :: out).reverse
  | c :: cs' =>
    if isSentenceSep c then
      let sentence := List.reverse (c :: acc)
      splitSentencesGo cs' [] (sentence :: out)
    else
      splitSentencesGo cs' (c :: acc) out

def splitSentences (s : String) : List String :=
  (splitSentencesGo s.data [] []).map String.mk

def isSentenceBoredom (s' : String) : Bool :=
  s'.startsWith "I " ∨ s'.startsWith " I"

def countBoredoms (sentences : List String) : Nat :=
  sentences.foldl (fun acc sentence =>
    if isSentenceBoredom sentence then acc + 1 else acc) 0


method is_bored (s: String) return (res: Nat)
  ensures res = countBoredoms (splitSentences s)
  do
    sorry
```

## 31. triangle_area

Given the lengths of the three sides of a triangle. Return the area of the triangle rounded to 2 decimal points
if the three sides form a valid triangle. Otherwise return -1. Three sides make a valid triangle when the sum of
any two sides is greater than the third side.

### Spec:

```
method triangle_area (a: Rat) (b: Rat) (c: Rat) return (res: Rat)
  ensures ((a + b > c) ∧ (a + c > b) ∧ (b + c > a)) →
    (let s := (a + b + c) / 2;
     abs (res^2 - (s * (s-a) * (s-b) * (s-c))) ≤ (1 : Rat) / 10000)
  ensures (¬((a + b > c) ∧ (a + c > b) ∧ (b + c > a))) →
    res = -1
  do
    sorry
```

### GPT5 complain:

-- ESCALATE:
-- The given specification requires, for all valid triangles, that
--   abs(res^2 - s*(s-a)*(s-b)*(s-c)) ≤ 1/10000.
-- If res is the area rounded to two decimals (res ≈ sqrt(P)), then
--   |res^2 - P| = |(round(A, 2)^2 - A^2)| = |(round(A,2) - A) * (round(A,2) + A)|.
-- Since |round(A,2) - A| ≤ 0.005, the bound becomes approximately ≤ 0.005 * (2A),
-- which grows with A and is not uniformly bounded by 0.0001 for large triangles.
-- Therefore, the specification (uniform 1/10000 bound on the squared error)
-- appears incompatible with the intended "rounded to 2 decimals" behavior.
-- I implemented a Rat-only rounding procedure that picks m/100 nearest to sqrt(P),
-- but proving the stated bound for all inputs is mathematically false in general.
-- As a consequence, a complete proof under the exact spec cannot be discharged.
-- The code below eliminates prior Real-related compilation errors and uses only Rat/Nat,
-- but the 'ensures' VC for the valid branch cannot be proven because it is not true.

### Updated spec:

```
method triangle_area (a: Rat) (b: Rat) (c: Rat) return (res: Rat)
  ensures ((a + b > c) ∧ (a + c > b) ∧ (b + c > a)) →
    (let s := (a + b + c) / 2;
      let A := s * (s-a) * (s-b) * (s-c);
      (∃ n : ℤ, res * 100 = n) ∧
      res ≥ 0 ∧
      A ≤ (res + 1/200) ^ 2 ∧
      (res > 0 → (res - 1/200) ^ 2 ≤ A))
  ensures (¬((a + b > c) ∧ (a + c > b) ∧ (b + c > a))) →
    res = -1
  do
    sorry
```

## Mantas review: 
 - The proposed update misses the corner case for very small valid triangles where `res = 0`. 
   For `res = 0`, `(0 - 0.005)^2 ≤ A` forces `A ≥ 0.000025`. However, a valid triangle can have area `A < 0.000025`, 
   for which the correct result is `0.00`.
 - I updated the lower bound condition to `(res > 0 → (res - 1/200) ^ 2 ≤ A)`, which correctly handles `res = 0` (where `0 ≤ A` is implied).
 - The rest of the spec matches the requirement (rounded to 2 decimal places).


---

## Other changes:
'
1. Changed method name 'compare' to 'compareListRat' in the dataset. Using 'compare' results in some naming ambiguity
2. Tests for right_angle_triangle in lean are wrong. Translated manually the ones from json to Loom.
3. Change method name 'derivative' to 'polynomialDerivative' in the dataset. Using 'derivative' results in some naming ambiguity
4. Fixed a wrong test for `search` from `#guard ((search [1, 2, 2, 3, 3, 4, 4, 4]).extract) = 3` to `#guard ((search [1, 2, 2, 3, 3, 4, 4, 4]).extract) = 2`.

---

Methods updated: 

bf
count_upper
do_algebra
encode_shift
encrypt
even_odd_count
fix_spaces
fruit_distribution
get_max_triples
hex_key
how_many_times
int_to_mini_roman
is_bored
is_sorted
largest_divisor
match_parens
minPath
minSubArraySum
multiply
order_by_points
remove_vowels
sort_array
sort_third
sorted_list_sum
specialFilter
sum_squares
vowels_count
words_in_sentence
x_or_y



# Problems which are still failing:

## 1. do_algebra

### ISSUE:

  -- ESCALATE: The given specification requires proving that for any lists
  -- of operators (containing "+", "-", "*", "//", "**") and operands (Nat),
  -- the token list built by mergeAlternately has an evaluation under the
  -- inductive semantics evalArith_precedence. However, applyOp for "//" and "**"
  -- is partial: it returns none on division by zero and on exponent with
  -- a negative base, respectively. The preconditions provided (operators/operands
  -- length relation, non-emptiness of operators, and non-negativity of operands)
  -- are insufficient to prevent these undefined cases. Consequently, the postcondition
  -- can be false for valid inputs (e.g., operator contains "//" and the corresponding
  -- operand is 0; or operator contains "**" after a preceding subtraction that makes
  -- the left subexpression negative), making the method unrealizable.
  --
  -- I attempted to construct a verified fold along the list and to build a proof
  -- in the evalArith_pass/add hierarchy, but the proof obligations necessarily
  -- require applyOp to succeed at each step corresponding to the concrete operator
  -- token, which cannot be guaranteed from the given requires.
  --
  -- To proceed, either:
  --  - Strengthen requires to exclude division by zero and ensure exponent base
  --    is non-negative at each "**" occurrence (e.g., by restricting operators or
  --    by adding semantic preconditions), or
  --  - Relax ensures to express partial evaluation (e.g., using an Option-typed
  --    result and a relation linking successful evaluation).
  --
  -- As-is, no total implementation can satisfy the ensures for all inputs
  -- admitted by the requires. I therefore return a dummy value here.
