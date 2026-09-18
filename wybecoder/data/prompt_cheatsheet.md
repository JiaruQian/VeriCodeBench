# Lean 4 `List`, `Array`, `String` Theorem Cheat-Sheet

This cheat-sheet summarizes the `List`, `Array`, and `String`/`Char` APIs with a section on `get` variations and cross-type conversion theorems.

## 💡 Key: Understanding `get` Variations (for `List` and `Array`)

These functions provide different ways to access elements. For verification, `getElem` (`[]`) and `get?` (`[i]?`) are the most important. Let `xs` be a `List` or `Array` and `n` be `xs.length` or `xs.size`.

* **`getElem` (`xs[i]`)**: The proof-carrying version.
    * **Signature**: `(i : Nat) → (h : i < n) → α`
    * **Use**: This is the standard, safe way to access an element *inside a proof* or when you have a proof `h` that the index is in bounds.

* **`get` (`xs.get i`)**: The `Fin` version (for `List`).
    * **Signature**: `(i : Fin n) → α`
    * **Use**: The bound proof `i < n` is packaged inside the `Fin n` type. It's semantically equivalent to `xs[i.val]`.

* **`get?` (`xs[i]?`)**: The `Option` version.
    * **Signature**: `(i : Nat) → Option α`
    * **Use**: This is the most common way to *start* a proof about an element. You can case-split on its result.

* **`getD` (`xs.getD i d`)**: The default value version.
    * **Signature**: `(i : Nat) → (default : α) → α`
    * **Use**: Returns `default` if `i` is out of bounds.

* **`get!` (`xs[i]!`)**: The unsafe, panicking version.
    * **Signature**: `(i : Nat) → α`
    * **Use**: This panics at runtime if `i` is out of bounds, can be used in Loom/Velvet methods.

### Key `get` Relationships

* **`get?` and `getElem`**:
    * **`Array.getElem?_eq_some_iff`**: `xs[i]? = some x ↔ ∃ h : i < xs.size, xs[i] = x`
    * **`Array.getElem?_eq_none_iff`**: `xs[i]? = none ↔ xs.size ≤ i`
    * **`List.getElem?_eq_some_iff`**: `l[i]? = some a ↔ ∃ h : i < l.length, l[i] = a`
    * **`List.getElem?_eq_none_iff`**: `l[i]? = none ↔ l.length ≤ i`
* **`get?` and `getD`**:
    * **`Array.getD_getElem?`**: `xs[i]?.getD d = if p : i < xs.size then xs[i]'p else d`
    * **`List.getD`** (This is the definition): `as.getD i fallback = as[i]?.getD fallback`
* **`get?` and `mem`**:
    * **`Array.mem_iff_getElem?`**: `a ∈ xs ↔ ∃ i, xs[i]? = some a`
    * **`List.mem_iff_getElem?`**: `a ∈ l ↔ ∃ i, l[i]? = some a`
    * **`Array.mem_of_getElem?`**: `xs[i]? = some a → a ∈ xs`
    * **`List.mem_of_getElem?`**: `l[i]? = some a → a ∈ l`
* **Rewriting `getElem`**:
    * **`List.getElem_of_eq`**: `h : l = l' → l[i] = l'[i]'(h ▸ w)` (Useful for rewrites)

---

## 1. `List`

**Core Principle:** The foundational inductive type for sequence verification.

### 1.1. Core Structure & Induction

* **Constructors**: `[]` (or `List.nil`) and `hd :: tl` (or `List.cons hd tl`).
* **`List.length_append`**: `(l₁ ++ l₂).length = l₁.length + l₂.length`
* **`List.append_assoc`**: `(l₁ ++ l₂) ++ l₃ = l₁ ++ (l₂ ++ l₃)`
* **`List.length_eq_zero_iff`**: `l.length = 0 ↔ l = []`
* **`List.ne_nil_iff_exists_cons`**: `l ≠ [] ↔ ∃ h t, l = h :: t`
* **`List.length_pos_iff_exists_mem`**: `0 < l.length ↔ ∃ a, a ∈ l`
* **`List.cons_eq_cons`**: `a :: l = b :: l' ↔ a = b ∧ l = l'`
* **`List.append_eq_nil_iff`**: `l₁ ++ l₂ = [] ↔ l₁ = [] ∧ l₂ = []`
* **`List.append_cancel_left`**: `l ++ l₁ = l ++ l₂ ↔ l₁ = l₂`
* **`List.append_cancel_right`**: `l₁ ++ l = l₂ ++ l ↔ l₁ = l₂`

### 1.2. Membership (`∈`)

* **Definition**: `a ∈ [] ↔ False` and `a ∈ hd :: tl ↔ a = hd ∨ a ∈ tl`
* **`List.mem_append`**: `a ∈ l₁ ++ l₂ ↔ a ∈ l₁ ∨ a ∈ l₂`
* **`List.mem_map`**: `b ∈ l.map f ↔ ∃ a, a ∈ l ∧ f a = b`
* **`List.mem_filter`**: `a ∈ l.filter p ↔ a ∈ l ∧ p a = true`
* **`List.mem_filterMap`**: `b ∈ l.filterMap f ↔ ∃ a, a ∈ l ∧ f a = some b`
* **`List.mem_flatMap`**: `b ∈ l.flatMap f ↔ ∃ a, a ∈ l ∧ b ∈ f a`
* **`List.mem_reverse`**: `a ∈ l.reverse ↔ a ∈ l`
* **`List.mem_replicate`**: `a ∈ replicate n b ↔ n ≠ 0 ∧ a = b`
* **`List.mem_iff_getElem?`**: `a ∈ l ↔ ∃ i, l[i]? = some a`
* **`List.mem_iff_getElem`**: `a ∈ l ↔ ∃ i h, l[i] = a`
* **`List.mem_of_getElem?`**: `l[i]? = some a → a ∈ l`
* **`List.forall_mem_cons`**: `(∀ x ∈ a :: l, p x) ↔ p a ∧ (∀ x ∈ l, p x)`
* **`List.forall_mem_append`**: `(∀ x ∈ l₁ ++ l₂, p x) ↔ (∀ x ∈ l₁, p x) ∧ (∀ x ∈ l₂, p x)`
* **`List.contains_iff_mem`** (LawfulBEq): `l.contains a = true ↔ a ∈ l`

### 1.3. Accessors (`getElem?`, `head?`, `getLast?`)

* **`List.getElem?_cons`**: `(a :: l)[i]? = if i = 0 then some a else l[i - 1]?`
* **`List.getElem?_append`**: `(l₁ ++ l₂)[i]? = if i < l₁.length then l₁[i]? else l₂[i - l₁.length]?`
* **`List.getElem_append`**: `(l₁ ++ l₂)[i] = if h' : i < l₁.length then l₁[i] else l₂[i - l₁.length]`
* **`List.getElem?_map`**: `(l.map f)[i]? = l[i]?.map f`
* **`List.getElem?_set`**: `(l.set i a)[j]? = if i = j then (if i < l.length then some a else none) else l[j]?`
* **`List.getElem_set_ne`**: `i ≠ j → (l.set i a)[j] = l[j]`
* **`List.getElem_set_self`**: `i < (l.set i a).length → (l.set i a)[i] = a`
* **`List.head?_eq_getElem?`**: `l.head? = l[0]?`
* **`List.head?_eq_none_iff`**: `l.head? = none ↔ l = []`
* **`List.head?_eq_some_iff`**: `l.head? = some a ↔ ∃ t, l = a :: t`
* **`List.getLast?_eq_getElem?`**: `l.getLast? = l[l.length - 1]?`
* **`List.getLast?_eq_none_iff`**: `l.getLast? = none ↔ l = []`
* **`List.getLast?_eq_some_iff`**: `l.getLast? = some a ↔ ∃ t, l = t ++ [a]`
* **`List.getLast?_append`**: `(l₁ ++ l₂).getLast? = l₂.getLast?.or l₁.getLast?`
* **`List.ext_getElem?`**: `(∀ i, l₁[i]? = l₂[i]?) → l₁ = l₂`

### 1.4. Iteration (`map`, `foldl`, `foldr`)

* **`List.length_map`**: `(l.map f).length = l.length`
* **`List.map_append`**: `(l₁ ++ l₂).map f = l₁.map f ++ l₂.map f`
* **`List.map_map`**: `(l.map f).map g = l.map (g ∘ f)`
* **`List.map_id`**: `l.map id = l`
* **`List.map_eq_nil_iff`**: `l.map f = [] ↔ l = []`
* **`List.foldl_append`**: `(l₁ ++ l₂).foldl f init = l₂.foldl f (l₁.foldl f init)`
* **`List.foldr_append`**: `(l₁ ++ l₂).foldr f init = l₁.foldr f (l₂.foldr f init)`
* **`List.foldl_reverse`**: `l.reverse.foldl f init = l.foldr (fun x y => f y x) init`
* **`List.foldr_reverse`**: `l.reverse.foldr f init = l.foldl (fun x y => f y x) init`
* **`List.map_eq_flatMap`**: `l.map f = l.flatMap (fun x => [f x])`

### 1.5. Counting (`countP`, `count`)

* **`List.countP_cons`**: `(a :: l).countP p = l.countP p + if p a then 1 else 0`
* **`List.count_eq_countP`**: `l.count a = l.countP (· == a)`
* **`List.countP_append`**: `(l₁ ++ l₂).countP p = l₁.countP p + l₂.countP p`
* **`List.count_append`**: `(l₁ ++ l₂).count a = l₁.count a + l₂.count a`
* **`List.countP_map`**: `(l.map f).countP p = l.countP (p ∘ f)`
* **`List.countP_filter`**: `(l.filter q).countP p = l.countP (fun a => p a && q a)`
* **`List.countP_eq_zero`**: `l.countP p = 0 ↔ ∀ a ∈ l, ¬p a`
* **`List.countP_eq_length`**: `l.countP p = l.length ↔ ∀ a ∈ l, p a`
* **`List.countP_eq_length_filter`**: `l.countP p = (l.filter p).length`
* **`List.count_eq_zero`** (LawfulBEq): `l.count a = 0 ↔ a ∉ l`
* **`List.count_pos_iff`** (LawfulBEq): `0 < l.count a ↔ a ∈ l`
* **`List.perm_iff_count`** (LawfulBEq): `l₁ ~ l₂ ↔ ∀ a, l₁.count a = l₂.count a`
* **`List.Nodup.count`** (LawfulBEq): `h : l.Nodup → l.count a = if a ∈ l then 1 else 0`

### 1.6. Permutation (`Perm` `~`)

* **Constructors**: `Perm.nil`, `Perm.cons`, `Perm.swap`, `Perm.trans`
* **`List.Perm.symm`**: `l₁ ~ l₂ → l₂ ~ l₁`
* **`List.perm_iff_count`** (LawfulBEq): `l₁ ~ l₂ ↔ ∀ a, l₁.count a = l₂.count a`
* **`List.Perm.mem_iff`**: `l₁ ~ l₂ → (a ∈ l₁ ↔ a ∈ l₂)`
* **`List.Perm.length_eq`**: `l₁ ~ l₂ → l₁.length = l₂.length`
* **`List.Perm.isEmpty_eq`**: `l₁ ~ l₂ → l₁.isEmpty = l₂.isEmpty`
* **`List.Perm.append`**: `l₁ ~ l₂ → r₁ ~ r₂ → l₁ ++ r₁ ~ l₂ ++ r₂`
* **`List.perm_append_comm`**: `l₁ ++ l₂ ~ l₂ ++ l₁`
* **`List.perm_middle`**: `l₁ ++ a :: l₂ ~ a :: (l₁ ++ l₂)`
* **`List.Perm.map`**: `l₁ ~ l₂ → l₁.map f ~ l₂.map f`
* **`List.Perm.filter`**: `l₁ ~ l₂ → l₁.filter p ~ l₂.filter p`
* **`List.reverse_perm`**: `l.reverse ~ l`
* **`List.Perm.nodup_iff`**: `l₁ ~ l₂ → l₁.Nodup ↔ l₂.Nodup`
* **`List.perm_cons_erase`** (LawfulBEq): `a ∈ l → l ~ a :: l.erase a`

### 1.7. `Pairwise` & `Nodup` (Uniqueness)

* **`List.pairwise_cons`**: `(a :: l).Pairwise R ↔ (∀ a' ∈ l, R a a') ∧ l.Pairwise R`
* **`List.pairwise_nil`**: `[].Pairwise R` (is true)
* **`List.nodup_iff_pairwise_ne`**: `l.Nodup ↔ l.Pairwise (· ≠ ·)`
* **`List.nodup_cons`**: `(a :: l).Nodup ↔ a ∉ l ∧ l.Nodup`
* **`List.pairwise_append`**: `(l₁ ++ l₂).Pairwise R ↔ l₁.Pairwise R ∧ l₂.Pairwise R ∧ (∀ a ∈ l₁, ∀ b ∈ l₂, R a b)`
* **`List.nodup_append`**: `(l₁ ++ l₂).Nodup ↔ l₁.Nodup ∧ l₂.Nodup ∧ (∀ a ∈ l₁, a ∉ l₂)`
* **`List.pairwise_map`**: `(l.map f).Pairwise R ↔ l.Pairwise (fun a b => R (f a) (f b))`
* **`List.pairwise_filter`**: `(l.filter p).Pairwise R ↔ l.Pairwise (fun x y => p x → p y → R x y)`
* **`List.pairwise_reverse`**: `l.reverse.Pairwise R ↔ l.Pairwise (fun a b => R b a)`
* **`List.Pairwise.sublist`**: `l₁ <+ l₂ → l₂.Pairwise R → l₁.Pairwise R`
* **`List.Nodup.sublist`**: `l₁ <+ l₂ → l₂.Nodup → l₁.Nodup`
* **`List.pairwise_iff_getElem`**: `l.Pairwise R ↔ ∀ i j, i < l.length → j < l.length → i < j → R l[i] l[j]`
* **`List.nodup_replicate`**: `(replicate n a).Nodup ↔ n ≤ 1`
* **`List.Nodup.erase`** (LawfulBEq): `l.Nodup → (l.erase a).Nodup`

### 1.8. Sublist Operations (`take`, `drop`, `Sublist`)

* **`List.take_append_drop`**: `l.take n ++ l.drop n = l`
* **`List.length_take`**: `(l.take n).length = min n l.length`
* **`List.length_drop`**: `(l.drop n).length = l.length - n`
* **`List.take_append`**: `(l₁ ++ l₂).take n = l₁.take n ++ (l₂.take (n - l₁.length))`
* **`List.drop_append`**: `(l₁ ++ l₂).drop n = l₁.drop n ++ (l₂.drop (n - l₁.length))`
* **`List.take_append_of_le_length`**: `n ≤ l₁.length → (l₁ ++ l₂).take n = l₁.take n`
* **`List.drop_length_add_append`**: `(l₁ ++ l₂).drop (l₁.length + n) = l₂.drop n`
* **`List.map_take`**: `(l.take n).map f = (l.map f).take n`
* **`List.map_drop`**: `(l.drop n).map f = (l.map f).drop n`
* **`List.take_take`**: `(l.take n).take m = l.take (min n m)`
* **`List.drop_drop`**: `(l.drop n).drop m = l.drop (n + m)`
* **`List.drop_eq_nil_iff`**: `l.drop n = [] ↔ l.length ≤ n`
* **`List.take_eq_nil_iff`**: `l.take n = [] ↔ n = 0 ∨ l = []`
* **`List.takeWhile_append_dropWhile`**: `l.takeWhile p ++ l.dropWhile p = l`
* **`List.Sublist.length_le`**: `l₁ <+ l₂ → l₁.length ≤ l₂.length`
* **`List.Sublist.subset`**: `l₁ <+ l₂ → l₁ ⊆ l₂`
* **`List.IsPrefix.getElem`**: `xs <+: ys → i < xs.length → xs[i] = ys[i]`
* **`List.prefix_iff_eq_take`**: `l₁ <+: l₂ ↔ l₁ = l₂.take l₁.length`
* **`List.suffix_iff_eq_drop`**: `l₁ <:+ l₂ ↔ l₁ = l₂.drop (l₂.length - l₁.length)`

### 1.9. Finding (`find?`, `findIdx?`)

* **`List.find?_eq_none_iff`**: `l.find? p = none ↔ ∀ x ∈ l, ¬ p x`
* **`List.find?_eq_some_iff_append`**: `l.find? p = some b ↔ p b ∧ ∃ as bs, l = as ++ b :: bs ∧ ∀ a ∈ as, !p a`
* **`List.find?_append`**: `(l₁ ++ l₂).find? p = (l₁.find? p).or (l₂.find? p)`
* **`List.find?_map`**: `(l.map f).find? p = (l.find? (p ∘ f)).map f`
* **`List.mem_of_find?_eq_some`**: `l.find? p = some a → a ∈ l`
* **`List.findIdx?_eq_some_iff_getElem`**: `l.findIdx? p = some i ↔ ∃ h : i < l.length, p l[i] ∧ ∀ j (hji : j < i), ¬p l[j]`
* **`List.findIdx?_eq_none_iff_findIdx_eq`**: `l.findIdx? p = none ↔ l.findIdx p = l.length`
* **`List.not_of_lt_findIdx`**: `i < l.findIdx p → p l[i] = false`
* **`List.findIdx_lt_length_of_exists`**: `(∃ x ∈ l, p x) → l.findIdx p < l.length`
* **`List.findIdx?_append`**: `(l₁ ++ l₂).findIdx? p = (l₁.findIdx? p).or ((l₂.findIdx? p).map (· + l₁.length))`
* **`List.idxOf_lt_length_iff`** (LawfulBEq): `l.idxOf a < l.length ↔ a ∈ l`

### 1.10. `attach` & `pmap` (For Termination Proofs)

* **`List.unattach_attach`**: `l.attach.unattach = l`
* **`List.unattach_attachWith`**: `(l.attachWith p H).unattach = l`
* **`List.foldl_attach`**: `l.attach.foldl (fun acc t => f acc t.1) b = l.foldl f b`
* **`List.foldr_attach`**: `l.attach.foldr (fun t acc => f t.1 acc) b = l.foldr f b`
* **`List.map_subtype`**: `(hf : ∀ x h, f ⟨x, h⟩ = g x) → l.map f = l.unattach.map g`
* **`List.pmap_eq_map`**: `List.pmap (fun a _ => f a) l H = l.map f`
* **`List.pmap_eq_map_attach`**: `l.pmap f H = l.attach.map (fun x => f x.1 (H _ x.2))`
* **`List.attach_map_val`**: `l.attach.map (f ∘ Subtype.val) = l.map f`

### 1.11. Generation (`replicate`, `range`)

* **`List.length_replicate`**: `(replicate n a).length = n`
* **`List.mem_replicate`**: `b ∈ replicate n a ↔ n ≠ 0 ∧ b = a`
* **`List.getElem?_replicate`**: `(replicate n a)[i]? = if i < n then some a else none`
* **`List.getElem_replicate`**: `i < n → (replicate n a)[i] = a`
* **`List.replicate_append_replicate`**: `replicate n a ++ replicate m a = replicate (n + m) a`
* **`List.map_replicate`**: `(replicate n a).map f = replicate n (f a)`
* **`List.filter_replicate`**: `(replicate n a).filter p = if p a then replicate n a else []`
* **`List.length_range`**: `(range n).length = n`
* **`List.mem_range`**: `m ∈ range n ↔ m < n`
* **`List.getElem?_range`**: `i < n → (range n)[i]? = some i`
* **`List.getElem_range`**: `j < n → (range n)[j] = j`
* **`List.range_succ`**: `range (n + 1) = range n ++ [n]`
* **`List.range_add`**: `range (n + m) = range n ++ (range m).map (n + ·)`
* **`List.nodup_range`**: `(range n).Nodup`

---

## 2. `Array`

**Core Principle:** `Array` is a wrapper for `List`. Proofs use `xs.toList` and `l.toArray`.

### 2.1. Core Equalities & Extensionality

* **`Array.ext'`**: `xs.toList = ys.toList → xs = ys`
* **`Array.toList_inj`**: `xs.toList = ys.toList ↔ xs = ys`
* **`List.toList_toArray`**: `l.toArray.toList = l` (This is the main bridge)
* **`Array.size_eq_length_toList`**: `xs.size = xs.toList.length`
* **`Array.size_eq_zero_iff`**: `xs.size = 0 ↔ xs = #[]`

### 2.2. Membership (`∈`)

* **`Array.mem_def`**: `a ∈ xs ↔ a ∈ xs.toList`
* **`Array.mem_iff_getElem`**: `a ∈ xs ↔ ∃ (i : Nat) (h : i < xs.size), xs[i] = a`
* **`Array.mem_push`**: `x ∈ xs.push y ↔ x ∈ xs ∨ x = y`
* **`Array.mem_append`**: `a ∈ xs ++ ys ↔ a ∈ xs ∨ a ∈ ys`
* **`Array.mem_map`**: `b ∈ xs.map f ↔ ∃ a, a ∈ xs ∧ f a = b`
* **`Array.mem_filter`**: `a ∈ xs.filter p ↔ a ∈ xs ∧ p a = true`
* **`Array.mem_filterMap`**: `b ∈ xs.filterMap f ↔ ∃ a, a ∈ xs ∧ f a = some b`
* **`Array.mem_flatMap`**: `b ∈ xs.flatMap f ↔ ∃ a, a ∈ xs ∧ b ∈ f a`
* **`Array.contains_iff`** (LawfulBEq): `xs.contains a = true ↔ a ∈ xs`

### 2.3. Element Access (`get` / `getElem`)

* **`Array.getElem_push`**: `(xs.push x)[i]` is `xs[i]` if `i < xs.size` and `x` if `i = xs.size`.
* **`Array.getElem?_push`**: `(xs.push x)[i]? = if i = xs.size then some x else xs[i]?`
* **`Array.getElem_set`**: `(xs.set i v)[j]` is `v` if `i = j` and `xs[j]` otherwise.
* **`Array.getElem?_set`**: `(xs.set i v)[j]? = if i = j then some v else xs[j]?`
* **`Array.getElem_map`**: `(xs.map f)[i] = f xs[i]`.
* **`Array.getElem?_map`**: `(xs.map f)[i]? = xs[i]?.map f`.
* **`Array.getElem_append`**: If `i < (xs ++ ys).size`:
    * If `i < xs.size`, it's `xs[i]`.
    * If `i ≥ xs.size`, it's `ys[i - xs.size]`.
* **`Array.getElem_extract`**: `(xs.extract start stop)[i] = xs[start + i]`.
* **`Array.back?_eq_getElem?`**: `xs.back? = xs[xs.size - 1]?`

### 2.4. Modification (`push`, `set`, `append`)

* **`Array.toList_push`**: `(xs.push x).toList = xs.toList ++ [x]`
* **`Array.size_push`**: `(xs.push x).size = xs.size + 1`
* **`Array.toList_pop`**: `xs.pop.toList = xs.toList.dropLast`
* **`Array.pop_push`**: `(xs.push x).pop = xs`
* **`Array.toList_setIfInBounds`**: `(xs.setIfInBounds i v).toList = xs.toList.set i v`
* **`Array.toList_append`**: `(xs ++ ys).toList = xs.toList ++ ys.toList`
* **`Array.size_append`**: `(xs ++ ys).size = xs.size + ys.size`
* **`Array.toList_extract`**: `(xs.extract start stop).toList = xs.toList.extract start stop`
* **`Array.size_extract`**: `(xs.extract start stop).size = min stop xs.size - start`
* **`Array.eraseIdx_eq_take_drop_succ`**: `xs.eraseIdx i h = xs.take i ++ xs.drop (i + 1)`

### 2.5. Iteration (`map`, `foldl`)

* **`Array.toList_map`**: `(xs.map f).toList = xs.toList.map f`
* **`Array.size_map`**: `(xs.map f).size = xs.size`
* **`Array.map_append`**: `(xs ++ ys).map f = xs.map f ++ ys.map f`
* **`Array.map_map`**: `(xs.map f).map g = xs.map (g ∘ f)`
* **`Array.foldl_toList`**: `xs.foldl f init = xs.toList.foldl f init`
* **`Array.foldr_toList`**: `xs.foldr f init = xs.toList.foldr f init`
* **`Array.foldl_push`**: `(xs.push a).foldl f init = f (xs.foldl f init) a`
* **`Array.foldl_append`**: `(xs ++ ys).foldl f b = ys.foldl f (xs.foldl f b)`

### 2.6. `count` & Predicates (`any`, `all`)

* **`Array.countP_toList`**: `xs.countP p = xs.toList.countP p`
* **`Array.countP_push`**: `(xs.push a).countP p = xs.countP p + if p a then 1 else 0`
* **`Array.countP_append`**: `(xs ++ ys).countP p = xs.countP p + ys.countP p`
* **`Array.count_eq_zero`** (LawfulBEq): `xs.count a = 0 ↔ a ∉ xs`
* **`Array.count_pos_iff`** (LawfulBEq): `0 < xs.count a ↔ a ∈ xs`
* **`Array.any_toList`**: `xs.any p = xs.toList.any p`
* **`Array.all_toList`**: `xs.all p = xs.toList.all p`
* **`Array.any_eq_true'`**: `xs.any p = true ↔ ∃ x, x ∈ xs ∧ p x`
* **`Array.all_eq_true'`**: `xs.all p = true ↔ ∀ x, x ∈ xs → p x`
* **`Array.any_push`**: `(xs.push a).any p = (xs.any p || p a)`
* **`Array.all_push`**: `(xs.push a).all p = (xs.all p && p a)`

### 2.7. `Perm` & `attach`

* **`Array.perm_iff_toList_perm`**: `xs ~ ys ↔ xs.toList ~ ys.toList` (Use this!)
* **`Array.Perm.size_eq`**: `xs ~ ys → xs.size = ys.size`
* **`Array.Perm.mem_iff`**: `xs ~ ys → (a ∈ xs ↔ a ∈ ys)`
* **`Array.swap_perm`**: `xs.swap i j ~ xs`
* **`Array.unattach_attach`**: `xs.attach.unattach = xs`
* **`Array.foldl_attach`**: `xs.attach.foldl (fun acc t => f acc t.1) b = xs.foldl f b`
* **`Array.map_subtype`**: `(h : ∀ x h, f ⟨x, h⟩ = g x) → (xs : Array {x // p x}).map f = xs.unattach.map g`

---

## 3. `String` & `Char`

**Core Principle:** `String` verification is `List Char` verification via `s.data` or `s.toList`.

### 3.1. `Char`

* **`Char.ext`**: `a.val = b.val → a = b`
* **`Char.val_eq_of_eq`**: `c = d → c.val = d.val`
* **`Char.le_def`**: `a ≤ b ↔ a.val ≤ b.val`
* **`Char.lt_iff_val_lt_val`**: `a < b ↔ a.val < b.val`
* **`Char.ofNat_toNat`**: `Char.ofNat c.toNat = c`

### 3.2. `String` (Core)

* **`String.ext_iff`**: `s₁ = s₂ ↔ s₁.data = s₂.data`
* **`String.toList`**: `s.toList = s.data`
* **`String.append` (`++`)**: `(s₁ ++ s₂).data = s₁.data ++ s₂.data`
* **`String.append_assoc`**: `(s₁ ++ s₂) ++ s₃ = s₁ ++ (s₂ ++ s₃)`
* **`String.push`**: `(s.push c).data = s.data ++ [c]`
* **`String.length`**: `s.length = s.data.length`
* **`String.isEmpty`**: `s.isEmpty ↔ s.data = []`
* **`String.singleton_eq`**: `String.singleton c = ⟨[c]⟩`

### 3.3. `String.Pos` (Byte Position)

* **Note**: `String.Pos` is *not* a character index. Proofs involving `Pos` are complex.
* **`String.Pos.ext_iff`**: `i₁ = i₂ ↔ i₁.byteIdx = i₂.byteIdx`
* **`String.Pos.le_iff`**: `i₁ ≤ i₂ ↔ i₁.byteIdx ≤ i₂.byteIdx`
* **`String.Pos.lt_iff`**: `i₁ < i₂ ↔ i₁.byteIdx < i₂.byteIdx`
* **`String.Pos.addChar_eq`**: `p + c = ⟨p.byteIdx + c.utf8Size⟩`
* **`String.Pos.addString_eq`**: `p + s = ⟨p.byteIdx + s.utf8ByteSize⟩`

### 3.4. `String` Order (Lexicographical)

* **`String.lt_iff`**: `s < t ↔ s.data < t.data` (Reduces to `List.lt`)
* **`String.le_trans`**: `a ≤ b → b ≤ c → a ≤ c`
* **`String.le_total`**: `a ≤ b ∨ b ≤ a`
* **`String.le_antisymm`**: `a ≤ b → b ≤ a → a = b`

---

## 4. 🔄 Interface & Conversion Theorems

### 4.1. `List <-> Array`

* **`List.toList_toArray`**: `l.toArray.toList = l`
* **`Array.ext'`** (Extensionality): `xs.toList = ys.toList → xs = ys`
* **`List.toArray_inj`**: `as.toArray = bs.toArray → as = bs`
* **`List.toArray_eq_iff`**: `as.toArray = bs ↔ as = bs.toList`
* **`List.perm_iff_toArray_perm`**: `l₁ ~ l₂ ↔ l₁.toArray ~ l₂.toArray`
* **`List.map_toArray`**: `l.toArray.map f = (l.map f).toArray`
* **`List.filter_toArray`**: `l.toArray.filter p = (l.filter p).toArray`
* **`List.append_toArray`**: `l₁.toArray ++ l₂.toArray = (l₁ ++ l₂).toArray`
* **`List.foldl_toArray`**: `l.toArray.foldl f init = l.foldl f init`
* **`List.foldr_toArray`**: `l.toArray.foldr f init = l.foldr f init`
* **`List.countP_toArray`**: `l.toArray.countP p = l.countP p`
* **`List.any_toArray`**: `l.toArray.any p = l.any p`
* **`List.all_toArray`**: `l.toArray.all p = l.all p`
* **`List.find?_toArray`**: `l.toArray.find? f = l.find? f`
* **`List.findIdx?_toArray`**: `l.toArray.findIdx? p = l.findIdx? p`
* **`List.idxOf?_toArray`**: `l.toArray.idxOf? a = l.idxOf? a`
* **`List.zip_toArray`**: `Array.zip as.toArray bs.toArray = (List.zip as bs).toArray`

### 4.2. `String <-> List Char`

This interface is mostly by definition. `s.data` is the same as `s.toList`.

* **`String.ext_iff`**: `s₁ = s₂ ↔ s₁.data = s₂.data`
* **`String.length`**: `s.length = s.data.length`
* **`String.append`**: `(s₁ ++ s₂).data = s₁.data ++ s₂.data`
* **`String.push`**: `(s.push c).data = s.data ++ [c]`
* **`String.map`**: `(s.map f).data = s.data.map f`
* **`String.foldl`**: `s.foldl f init = s.data.foldl f init` (and `foldr`)
* **`String.any`**: `s.any p = s.data.any p`
* **`String.all`**: `s.all p = s.data.all p`
* **`String.contains`**: `s.contains c = s.data.contains c`
* **`String.lt_iff`**: `s < t ↔ s.data < t.data`
* **`List.asString`**: `(l : List Char).asString.data = l`

### 4.3. `String <-> ByteArray` (UTF-8)

This interface is for I/O and byte-level manipulation.

* **`String.validateUTF8 a`**: `ByteArray → Bool`
* **`String.fromUTF8? a`**: `ByteArray → Option String`
* **`String.toUTF8 s`**: `String → ByteArray`
* **Roundtrip (String -> Bytes -> String)**: `String.fromUTF8? (s.toUTF8) = some s`
* **Roundtrip (Bytes -> String -> Bytes)**: `(String.fromUTF8? a).map String.toUTF8 = if String.validateUTF8 a then some a else none`
* **`String.fromUTF8! a`**: Panicking version of `fromUTF8?`.
* **`String.fromUTF8 a h`**: Proof-carrying version, requires `h : String.validateUTF8 a`.
