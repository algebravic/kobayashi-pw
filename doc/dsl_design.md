# A specification language for set-determined layout searches (design, before implementation)

## 0. Why the algorithms are one algorithm

kpw (pathwidth), kcw (cutwidth) and the treewidth prototype all solve a problem of the same form. Let V be a finite set and let w : 2^V × V → ℕ be a **step cost**. The problem is

> width(V, w) = min over orderings π of V of max_i w({π₁, …, π_{i−1}}, π_i).

| problem | w(S, v) |
|---|---|
| vertex separation (= pathwidth) | f(S + v) with f(S) = \|N⁻(S) ∖ S\|, where N⁻(S) = ⋃_{u∈S} N_in(u) |
| cutwidth | f(S + v) with f(S) = \|E(S, V∖S)\| |
| treewidth (elimination orderings) | \|Q(S, v)\|, the vertices outside S + v reachable from v through S |

Bandwidth is not of this form: its cost depends on positions, not only on the set.

Because the cost depends only on (S, v), width(V, w) is a minimum-bottleneck path from ∅ to V in the subset lattice. All our programs share one engine, a bucketed bottleneck search with parent pointers. What differs between them is a short list of **value-preserving reductions** (closure rules, move restrictions, symmetry, state quotients) and the **data structures**.

The DSL makes that split explicit:

1. **Layer P (problem).** P is a mathematical description: the cost, and the reductions, each tied to a named lemma that justifies it. It fixes *what* is computed and *why it is correct*.
2. **Layer D (data).** D holds annotations that choose representations, which quantities are maintained incrementally, the table, the frontier policy and parallelism. Each annotation is a *refinement* of P. It may change running time and memory, never the result.
3. **The engine E.** E is fixed and written once. Its correctness is proved once, against an abstract interface that every P must implement.

The goal is that kpw is about 20 lines of P plus about 10 of D, and kcw about 30 plus 10 (§4, §5), with every correctness claim reduced to a lemma about P.

## 1. The abstract model (what a spec denotes)

A spec denotes a **move system** 𝓜 = (V, Σ, s₀, moves, apply, key, decode), where:

- **Σ ⊆ 2^V** is the set of *normal states* (prefix sets in normal form).
- **s₀ ∈ Σ** is the initial normal state: the closure of ∅.
- **moves(s)** is a finite set of *moves*. A move m has a **label** (for example x, or (x, i)) and a **vertex sequence** seq(s, m) = (u₁, …, u_k) of vertices not in s.
- **apply(s, m)** = s ∪ seq(s, m) ∪ (closure additions) ∈ Σ. It is deterministic: it also returns the full vertex sequence that was added, closure included.
- **cost(s, m) ∈ ℕ** is the arc cost.
- **key : Σ → K** is injective on Σ, and **decode : K → Σ** is its inverse.

The value of 𝓜 is the minimum over paths s₀ → V in the move graph of the largest arc cost on the path.

### 1.1 Proof obligations of a spec

| | obligation | meaning |
|---|---|---|
| **O1** | **exact arc cost** | Let t = apply(s, m), with full added sequence (u₁, …, u_r). Then cost(s, m) = max_j w(s ∪ {u₁..u_{j−1}}, u_j). A cost "≥ this maximum with equality on the moves used by some optimal ordering" is also acceptable. |
| **O2** | **completeness** | width(V, w) ≤ B ⇒ the move graph has a path s₀ → V with every arc cost ≤ B. |
| **O3** | **quotient** | key is injective on Σ, and decode ∘ key = id. |
| **O4** | **replay** | apply is a deterministic function of (s, label). |

O1 gives soundness: every path spells an ordering whose width is at most the path's bottleneck. O2 gives optimality. Together they give value(𝓜) = width(V, w).

The interesting content is O2. It is discharged by composing the lemmas attached to the reductions (§2.2).

### 1.2 The engine E and its theorem

```
E(𝓜, B₀):                                  -- B₀ any certified lower bound (default 0)
  T ← {key s₀ ↦ ⊥};  B ← B₀;  stack ← [s₀];  bucket[·] ← ∅
  if s₀ = V: return (0, s₀)
  loop
    while stack ≠ ∅
      s ← pop;  next ← ∞
      for m ∈ moves(s):
        c ← cost(s, m)
        if c > B: next ← min(next, c); continue
        t ← apply(s, m)
        if key t ∉ T: T[key t] ← (key s, label m)
                      if t = V: return (B, T)
                      push t
      if next < ∞: bucket[next] ∪= {s}
    B ← min{b > B : bucket[b] ≠ ∅}                  -- exists while V is unreached
    stack ← bucket[B]                               -- rescan
```

**Theorem E.** Assume O1–O4.

1. When level B has been processed completely, T contains exactly the keys of the states reachable from s₀ with bottleneck ≤ B.
2. E returns B = value(𝓜) = width(V, w).
3. Replaying the labels from V back to s₀ yields an ordering of width B.
4. If E is stopped while processing level B, then width ≥ B.

Proof sketch: item 1 by induction on B. A state's moves of cost ≤ B are generated when the state is first expanded at a level ≤ B, or when it is rescanned from bucket[b] with b ≤ B. Items 2 and 3 follow from O1, O2 and O4. Item 4 holds because every level below B is complete.

This is the theorem we have been relying on informally for kpw, kpw2 and kcw. In the DSL it is proved once.

## 2. Layer P: syntax

### 2.1 Core forms

```
problem NAME(G : Graph | Digraph) {
  ground   V = …
  let      name(args) = expr                    -- definitions (pure, set-builder notation)
  cost     w(S, v) = expr                       -- the step cost; or:
  cost     f(S) = expr  [submodular by LEMMA]   -- shorthand for w(S,v) = f(S+v)
  closure  P(S, v)  by LEMMA                    -- free additions, iterated to a fixpoint
  choose   x ∈ SET(S)  by LEMMA                 -- which vertices may be chosen voluntarily
    [prefix  SEQ(S, x)  by LEMMA]               -- vertices placed just before x (macro move)
    [label   (x, extra…)]                       -- label stored for replay
  symmetry GROUP  by LEMMA                      -- orbit canonicalisation of choices
  key      expr(S)  by LEMMA                    -- state quotient + decode
  [bound   lb(S) by LEMMA]                      -- optional completion lower bound (A*), see §7
}
```

- **Expressions** are ordinary finite set theory over V: ∪, ∩, ∖, |·|, N(v), N_in(v), deg v, comprehension {u ∈ A : φ}, min, max, ⌊·⌋, and integer arithmetic.
- **Derived arc cost.** The arc cost is never written by hand. It is *derived* by the compiler as the maximum of w along prefix · x · closure, which is O1 by construction. Writing it by hand is allowed only with an explicit `cost-of-move … by LEMMA`, as for kcw's closed form.
- **Closure** is applied to a fixpoint after every move, in a deterministic order: queue order, starting from the neighbours of the newly added vertices.

### 2.2 Lemma library (the reusable part of the rigour)

Each `by LEMMA` refers to an entry with a precise hypothesis, which the compiler checks syntactically when it can. Otherwise the hypothesis becomes a stated assumption in the generated report.

| lemma | hypothesis | conclusion (form needed for O2) |
|---|---|---|
| `greedy` | w(S, v) = f(S+v), f submodular; P(S, v) ⇒ f(S+v) ≤ f(S) | If some completion from S has bottleneck ≤ B, so does some completion from S+v. Proof: move v to the front; for prefixes A ⊇ S before v, f(A+v) ≤ f(A) + f(S+v) − f(S) ≤ f(A). |
| `submod-coverage` | f(S) = \|⋃_{u∈S} X_u ∪ S\| − \|S\| | f is submodular (a coverage function minus a modular one). Discharges `submodular` for vertex separation. |
| `submod-cut` | f(S) = \|E(S, V∖S)\| | f is symmetric submodular. |
| `subset-rule` | P ⇒ P′ and `greedy` holds for P′ | `greedy` holds for P. Kobayashi's rule 1 and CMN's rule 2 are sub-rules of Δ ≤ 0. |
| `cover-normal-form` | cutwidth; C a vertex cover; every vertex outside C chosen only by closure or the Y-prefix | some optimal ordering is in this normal form (Cygan, Lokshtanov, Pilipczuk, Pilipczuk, Saurabh 2014; our version with the prefix of size i = min(\|Y\|, ⌊Δ/2⌋)) |
| `normal-key` | every s ∈ Σ is the closure of (s ∩ K) under a rule that is a function of s ∩ K | key s = s ∩ K is injective, and decode is that closure |
| `automorphism` | GROUP ≤ Aut(G, w), and GROUP preserves every set mentioned in `choose`/`prefix` (e.g. C) | restricting each choice to orbit representatives (e.g. the smallest unplaced twin) preserves O2 |
| `twins` | u, v with N[u] = N[v] or N(u) = N(v) | the transposition (u v) is in Aut(G, w) for every w defined from G |
| `simplicial` | treewidth; v simplicial in the elimination graph G_S | eliminating v next is safe; the cost of the block is the maximum over the block |

New problems usually reuse these. A genuinely new reduction adds one row to this table, and that row is the only new mathematics.

## 3. Layer D: syntax

```
impl NAME {
  repr     SET : bitset(W)          | bitset(dyn) | sorted-list          -- representation of subsets of V
  repr     KEY : same | bitset(|K|) packed                               -- what the table stores
  maintain q(S) : TYPE  [carried | decoded] [incremental Δ-rule] [undo-log]
  table    open-addressing(load=1/2, hash=H) value (parent: key | id32, label)
           | label-only (recover parent by scan)                         -- kpw2 -x
  frontier dfs-stack, buckets[cost]; rescan = full | window(lo, B]
  probe    before-closure                                                -- look up s+x before closing it
  parallel work-stealing(threads, shards=K, lock=spin)                   -- kpw2 -t
  limits   time, states  → report lb
  output   order | dag(complete, prune=co-reachable) | pareto(secondary) | k-best
}
```

Every D annotation comes with a **refinement condition**, which the compiler checks or which is a lemma of the data layer:

- **`maintain q`** must be a function of S. Under `carried`, q travels on the stack with S, as kpw's nb = ⋃ N_in(S) does. Under `decoded`, it is recomputed from the key, as kcw's a[v] = \|N(v) ∩ S\| is.
- **`incremental Δ-rule`** supplies q(S+u) from q(S) and u. The compiler can test the rule against direct recomputation in a debug build.
- **`rescan = window(lo, B]`** is valid only if the moves with cost ≤ lo were pushed when the state was last scanned at level lo. kpw meets this condition. kcw uses `full`, which is always valid.
- **`probe before-closure`** is valid because normal states are fixpoints: if s + x is already a stored state, then its closure is s + x itself. kpw uses this.
- **`label-only`** is valid if the parent is recoverable as the stored state s with apply(s, label) = t. kpw2 finds it by a table scan over \|s\| = \|t\| − (length of the added sequence).
- **`parallel`** is valid by Theorem E applied level by level: the order of expansion within a level does not matter, provided each level is joined before B rises.

## 4. kpw in the DSL

```
problem vertex_separation(D : Digraph) {
  ground   V = vertices(D)
  let      Nin⁻(S) = ⋃_{u∈S} N_in(u)
  cost     f(S) = |Nin⁻(S) ∖ S|   submodular by submod-coverage
  closure  N_in(v) ⊆ S ∪ Nin⁻(S)                          by subset-rule(greedy)   -- Kobayashi rule 1
  closure? [flag -g] v ∈ Nin⁻(S) ∧ |N_in(v) ∖ (S ∪ Nin⁻(S))| = 1
                                                         by subset-rule(greedy)   -- CMN Lemma 6, mirrored
  choose   x ∈ V ∖ S                                     by trivial
  key      S                                             by trivial
}

impl vertex_separation as kpw {
  repr     SET : bitset(1)                               -- n ≤ 64;  kpw2: bitset(W), W = 2 default
  maintain nb(S) = ⋃_{u∈S} N_in(u) : SET  carried  incremental nb ∪= N_in(u)
  table    open-addressing(load=1/2) value (parent: key, label: x)
  frontier dfs-stack of (S, nb, x) pairs;  rescan = window(lo, B]
  probe    before-closure
  output   order | dag(complete) [flag -c]
}
impl vertex_separation as kpw2 extends kpw {
  repr     SET : bitset(W)
  table    … | label-only [flag -x]
  parallel work-stealing [flag -t]
}
```

Derived pieces:
- **Arc cost.** The derived arc cost is f(S + x). O1 holds because closure steps have Δ ≤ 0, so the maximum along the move is attained at x.
- **Correctness.** O2 = trivial `choose` ∘ `greedy` (twice); O3 is trivial.
- **The DAG output** (`-c`, KPWDAG3) is an engine option. It is the move graph restricted to arcs of cost ≤ pw that are co-reachable to V.

## 5. kcw in the DSL

```
problem cutwidth(G : Graph) {
  ground   V = vertices(G)
  cost     f(S) = |E(S, V ∖ S)|  submodular by submod-cut
  let      Δ(S, v) = deg v − 2 |N(v) ∩ S|                  -- = f(S+v) − f(S)
  let      C = vertex_cover(G) twin-closed                 -- any cover; quality affects only speed
  closure  Δ(S, v) ≤ 0                                     by greedy
  choose   x ∈ C ∖ S                                       by cover-normal-form
    prefix Y(S, x)[: i]  where
           Y(S, x) = ⟨u ∈ N(x) ∖ C ∖ S : deg u odd, Δ(S, u) = 1⟩     -- adjacency order
           i       = min(|Y(S, x)|, max(0, ⌊Δ(S, x)/2⌋))
                                                           by cover-normal-form
    label  (x, i)
    cost-of-move f(S) + max(i, Δ(S, x) − i)                by cover-normal-form   -- closed form of O1
  symmetry ⟨(u v) : u, v twins⟩                            by automorphism, twins  -- C twin-closed
  key      S ∩ C                                           by normal-key
           -- decode: S = K ∪ {u ∉ C : Δ(K, u) ≤ 0}   (u ∉ C are independent, so one pass suffices)
}

impl cutwidth as kcw {
  repr     SET : bitset(dyn);   KEY : bitset(|C|) packed
  maintain a(v) = |N(v) ∩ S| : int[n]   decoded   incremental a[N(u)] += 1   undo-log
  table    open-addressing(load=1/2) value (parent: id32, label: (x, i))
  frontier dfs-stack of ids;  rescan = full
  limits   time, states → lb
  output   order
  components separately, width = max
  cover    bipartite ⇒ König(max matching) ; else greedy-max-degree + drop-redundant
}
```

Derived pieces:
- **O1.** O1 follows from the closed form. The prefix raises the cut by 1 per vertex, x then changes it by Δ − 2i, and the closure never raises it.
- **O2** is the composition greedy ∘ cover-normal-form ∘ automorphism. The `automorphism` lemma needs C to be twin-closed, which is why `twin-closed` appears in the definition of C. This is exactly the condition that was implemented by hand in kcw.c.
- **O3** is `normal-key`.

## 6. Treewidth, as a check on generality

```
problem treewidth(G : Graph) {
  ground   V = vertices(G)
  let      Q(S, v) = {u ∉ S + v : u reachable from v by a path with interior in S}
  cost     w(S, v) = |Q(S, v)|                          -- not of the form f(S+v)
  closure  v simplicial in G_S                          by simplicial
  choose   x ∈ V ∖ S                                    by trivial
  key      S                                            by trivial
}
```

This example exposes the one place where the framework has to be careful. For vertex separation and cutwidth, the closure never raises the cost (Δ ≤ 0), so the arc cost is the cost of the chosen step. Here, eliminating a simplicial vertex v costs |Q(S, v)|, which may exceed the cost of the step that made v simplicial. Two consequences follow:

- **The arc cost comes out right automatically.** The derived arc cost (§2.1) is the maximum of w over the whole block, x followed by its closure, so O1 holds with no hand-written cost.
- **O2 still holds, by a separate lemma.** With S fixed, the best completion's bottleneck equals tw(G_S), the treewidth of the elimination graph. If v is simplicial in G_S, then tw(G_S) = max(deg_{G_S} v, tw(G_S − v)), so eliminating v first loses nothing. That is the `simplicial` lemma.

So no level-dependent closure is needed, and E stays fixed. The general rule a closure must satisfy is the one in `greedy` and `simplicial`: if a completion from S has bottleneck ≤ B, then so does some completion that begins with the closure block. The block's own cost counts towards that bottleneck. Every closure lemma in the library is checked against this form.

## 7. What the DSL buys, and what it does not

**What it buys.**
- **Correctness argument in one place.** kpw2 is about 600 lines of C, and its correctness argument is scattered through comments. In the DSL it is: Theorem E + `greedy` + `submod-coverage` + the refinement conditions of the D layer.
- **New problems are cheap.** Cutwidth with a different cover, or a weighted cut, changes a few lines of P. Using pathwidth with a vertex cover is a one-line `choose` change that needs a new lemma, and the DSL forces that lemma to be stated.
- **A testable contract.** The reference interpreter (§8) checks O1, O3 and O4 at run time on random graphs, and O2 against the 2ⁿ brute force. Our ad hoc test files already do this, separately for each program.
- **A natural place for future work.** The `bound` clause (§2.1) is where A\* goes. It turns E into "expand s only if max(d, lb(s)) ≤ B". Its proof obligation is admissibility: lb(s) ≤ the bottleneck of the best completion from s. This is how Coudert's C\* bound would enter kcw.

**What it does not buy.**
- **Rigour.** The DSL does not prove the lemmas. It makes their hypotheses explicit and checks them where that can be done syntactically: whether f is a cut function, a coverage function, or a set used in `choose` that is twin-closed. A further step is to state Theorem E and the library lemmas in Lean. The interface is small enough for that to be realistic (§9, Q4).
- **Speed.** Good C still depends on decisions that the D layer names but does not invent: the Item-mask trick in kpw2, the sharded table, the closed-form arc cost. The generator emits the engine skeleton and calls per-problem inline functions. Those are generated from P where it is mechanical (set-builder expressions over bitsets), and written by hand where it is not, with a debug-mode equivalence check against the P semantics.
- **Generality.** Bandwidth, and anything whose cost is not a function of (S, v), is out of scope by design (§0).

## 8. Implementation: embedded in Python, compiled to C on demand

The model is PyTorch's `torch.compile`. The user writes ordinary Python that builds the spec symbolically. When the spec is first solved, it is lowered to C, compiled to a shared library, cached on disk, and called through `ctypes`. An *eager* mode interprets the same IR in Python. Eager mode is the reference semantics and the obligation checker.

### 8.1 What the user writes

```python
from kobayashi_pw.dsl import Problem, card, N, deg, odd, lemma, vertex_cover

def cutwidth(G):
    P = Problem("cutwidth", G)                     # S: the state (a symbolic Set), v: a symbolic vertex
    f = P.cost_f(lambda S: card(P.cut(S)), by=lemma.submod_cut)
    D = P.let(lambda S, v: deg(v) - 2 * card(N(v) & S))           # Δ(S, v)
    C = P.const(vertex_cover(G, twin_closed=True))                 # graph data, not code
    P.closure(lambda S, v: D(S, v) <= 0, by=lemma.greedy)
    Y = lambda S, x: P.seq(u for u in N(x) - C - S if odd(deg(u)) and D(S, u) == 1)
    i = lambda S, x: P.min(card(Y(S, x)), P.max(0, D(S, x) // 2))
    P.choose(over=lambda S: C - S, prefix=lambda S, x: Y(S, x)[: i(S, x)],
             label=lambda S, x: (x, i(S, x)),
             cost=lambda S, x: f(S) + P.max(i(S, x), D(S, x) - i(S, x)),   # closed form, needs its lemma
             by=lemma.cover_normal_form)
    P.symmetry(lemma.twins, preserves=[C])
    P.key(lambda S: S & C, by=lemma.normal_key)
    return P

spec = cutwidth(G)
spec.impl(set_repr="bitset", key_repr="packed",
          maintain={"a": "decoded incremental undo"}, rescan="full")
res = spec.solve(time_limit=60, max_states=5e7)      # compiles on first call, cached afterwards
res.width, res.order, res.lower_bound, res.stats
spec.solve(mode="eager")                              # same IR, interpreted (small n)
spec.check(n_max=11, trials=500)                      # obligations O1–O4 vs brute force
print(spec.pretty())                                  # the textual form of §5
```

Each lambda is called once, at definition time, with *symbolic* arguments. The operators on `Set`, `Int` and `Vertex` objects record IR nodes; no graph is touched. This is torch.fx-style tracing. Python control flow inside a lambda is evaluated at trace time and must not depend on symbolic values; data-dependent choices must use `P.min`, `P.where` and so on. The tracer raises an error if a symbolic value is converted to bool, the same rule PyTorch's tracer applies.

### 8.2 IR

The IR is a typed expression DAG with hash-consing:

- **Types:** `Set` (a subset of V), `Int`, `Bool`, `Vertex`, `Seq[Vertex]`.
- **Leaves:** `S`; bound vertices (`v`, `x`, and comprehension variables); graph constants (`N(·)`, `N_in(·)`, `deg(·)`, constant sets such as C).
- **Operations:**
  - set algebra: ∪, ∩, ∖, complement;
  - `card`, membership, `bigunion(A, N_in)`;
  - comprehensions `{u ∈ A : φ}` and ordered sequences `⟨u ∈ N(x) : φ⟩` (adjacency order, so that replay is deterministic);
  - `sum` and `max` over sets;
  - integer arithmetic, `min`, `max`, `where`, and slicing a sequence.

A spec is the IR plus the clause structure (cost, closures, choose, symmetry, key) plus the lemma tags, each with its checked hypotheses. The lemma checks run on the IR:
- `submod_cut` requires the cost IR to match `card(cut(S))`.
- `greedy` requires that the closure predicate implies `f(S+v) − f(S) ≤ 0`. The checker tries to prove this symbolically for the patterns in the library, such as Δ ≤ 0 or N_in(v) ⊆ S ∪ N⁻(S). Otherwise it falls back to a stated assumption plus randomized testing.
- `automorphism` requires every set named in `choose` to be in `preserves`.

### 8.3 Lowering to C

- **Sets** become `uint64_t[W]` for a compile-time W (specialisation, §8.4), or dynamic words when n is large.
  - ∪, ∩ and ∖ become word loops, and `card` becomes a popcount loop.
  - A comprehension over A becomes a bit loop over A that evaluates φ.
  - `N(v)` becomes an adjacency bitset row when the set is used whole, or a CSR walk when the expression only iterates over it. The choice is a cost-model decision recorded in the generated code.
- **Maintained quantities** (D layer) are matched structurally. Any IR subtree equal to a maintained q(S), such as `bigunion(S, N_in)` (kpw's nb) or `card(N(v) & S)` (kcw's a[v]), is replaced by a read of the maintained variable. The update rule is generated from the IR's derivative where the library knows it:
  - for `bigunion` the update is `∪= N_in(u)`;
  - for `card(N(v) & S)` it is `+= [u ∈ N(v)]`, which becomes a CSR walk over N(u).

  Otherwise the user supplies the rule. In debug builds every maintained value is re-checked against recomputation.
- **Derived arc cost.** The cost is computed as a running maximum of w as `apply` adds the prefix, then x, then the closure. If a closed form is given, the debug build asserts it against the running maximum (obligation O1).
- **The engine** is a fixed, hand-written `engine.h`: table, buckets, DFS stack, rescan policy, limits, replay, and later the DAG output and work stealing from kpw2. The generated `ops.h` supplies `decode`, `for_each_move(s, B, emit)`, `apply`/`undo`, `key` and `is_goal` as `static inline` functions, so the C compiler inlines them into the engine loop. No function pointers are used in the hot path.
- **ABI.** The library has one entry point: `int solve(const graph_t*, const consts_t*, const params_t*, result_t*)`. Graph data (adjacency rows, CSR, deg) and spec constants (the bitset C, twin classes) are passed at run time. The generated code is therefore independent of the particular graph and is reused across graphs.

### 8.4 Compilation and caching

- **Cache key:** SHA-256 of
  - the canonical serialisation of the IR and clause structure,
  - the D annotations,
  - the specialisation parameters (W, flags),
  - the engine version,
  - the compiler's identity and flags (`cc --version`, `-O3 -march=native`).
- **Location:** `~/.cache/kobayashi_pw/<key>/` (overridable with `KPW_CACHE`). It holds `gen.c`, `lib.so`, the compiler log, and `meta.json`.
- **Concurrency:** compilation takes a file lock; it is atomic (compile to a temporary file, then rename) and safe with several processes.
- **Specialisation and guards,** as in torch.compile: W = ⌈n/64⌉ is rounded up to {1, 2, 4, 8} or to "dyn". A new n reuses an existing library when it falls in the same bucket; otherwise one more library is compiled.
- **Fallback:** if no C compiler is available, `solve` falls back to eager mode with a warning. `mode="c"` forces compilation and errors out instead.
- **Debug builds:** `spec.solve(debug=True)` compiles with `-O1 -g -fsanitize=address,undefined` and with all O1/O3/maintenance assertions enabled.
- **Interrupts:** the call releases the GIL. Ctrl-C sets a flag that the engine polls with the limits, so an interrupted run still returns its certified `lower_bound`.

### 8.5 Testing and acceptance

- `spec.check()` runs eager and compiled modes against each other, and against the 2ⁿ brute force, on random graphs (n ≤ 11). It tests every arc generated for O1, O3 and O4.
- The specs `vertex_separation` and `cutwidth` must reproduce the hand-written programs on `data/` and on Coudert's benchmark sets:
  - the same widths;
  - the same state counts, given the same move order;
  - orderings of the same width;
  - time within about 1.3× of kpw/kcw.

  kpw.c and kcw.c stay in the repo as references.
- `treewidth` is the generality test: it must run with no engine changes.

### 8.6 Risks

- **Matching hand-tuned code.** Matching kpw/kcw speed depends on the lowering recognising a few idioms: maintained unions, popcounts of masked rows, and closure by worklist over the neighbours of added vertices. For anything the library doesn't recognise, the escape hatch is `P.native("c code", reads=…, writes=…)` with a debug-mode equivalence check against an IR definition.
- **Packed keys.** The quotient key S ∩ C needs an index map C → [0, τ). This is a spec constant, lowered as a gather of bits, or as a word-level compress where `pext` is available.
- **Proof-carrying lemmas.** The lemma hypotheses are checked only to the extent the IR pattern-matcher can check them. Anything beyond that appears in `spec.report()` as an explicit assumption.

## 9. Decisions

- **Q1 / Q2: settled by §8.** The DSL is embedded in Python and traced to an IR. C is generated, compiled on demand and cached. The generated part is `ops.h`, against a fixed hand-written `engine.h`.
- **Q3. Scope of the first milestone.** I propose:
  - the tracer, IR, eager engine and `check`;
  - C lowering, `engine.h` and the cache;
  - the specs `vertex_separation` and `cutwidth`, reaching kpw/kcw parity;
  - `treewidth`, in eager mode only.

  The DAG output, `label-only`, `parallel` and the `bound`/A\* clause would come in a second milestone.
- **Q4. Machine-checked proofs?** Formalising Theorem E plus `greedy` and `submod-*` in Lean is a contained project. `cover-normal-form` is the expensive one. Do you want that track, or is "lemma with reference plus randomized obligation checks" rigorous enough for now?
