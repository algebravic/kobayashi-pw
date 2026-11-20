# DSL milestone 1: implementation plan (written before the code)

This plan implements `doc/dsl_design.md` §8 for vertex separation and cutwidth. Treewidth is covered in eager mode only.

## Files

| file | content |
|---|---|
| `src/kobayashi_pw/dsl/ir.py` | hash-consed typed IR nodes, symbolic wrappers (`SetE`, `IntE`, `BoolE`, `VertE`, `SeqE`) with operator overloading, the pretty-printer |
| `src/kobayashi_pw/dsl/problem.py` | `Problem` with clauses `cost_f` / `cost_w`, `closure`, `choose`, `symmetry`, `key`, `components`, `impl`; `solve`, `check`, `report`, `pretty` |
| `src/kobayashi_pw/dsl/lemma.py` | lemma tags; syntactic hypothesis checks on the IR; runtime checks (cover, twin-closure) |
| `src/kobayashi_pw/dsl/eager.py` | IR evaluator on Python ints; engine E in Python; brute force; obligation checker |
| `src/kobayashi_pw/dsl/rewrite.py` | rewrites used to derive arc costs: `bigunion(S+x, F) → bigunion(S, F) ∪ F(x)`, `cut(S+x) → cut(S) + deg x − 2\|N(x) ∩ S\|` (with x ∉ S) |
| `src/kobayashi_pw/dsl/codegen.py` | lowering of the IR to C: word-wise set expressions, popcounts, bit loops, materialised temporaries, closure (sweep or neighbour worklist), maintained sets |
| `src/kobayashi_pw/dsl/jit.py` | cache key, compile with lock + atomic rename, `ctypes` loading, solve in a worker thread with a stop flag (Ctrl-C), W buckets {1, 2, 4, 8, 16} |
| `src/kobayashi_pw/dsl/specs.py` | `vertex_separation(greedy2=False)`, `cutwidth(cover=True, twins=True)`, `treewidth()` (eager only) |
| `src/C/dsl_engine.h` | engine E: hash table, stack, buckets with windowed or full rescan, limits, replay, the `solve` entry point |
| `tests/test_dsl.py` | eager and compiled results vs brute force; parity with kpw/kcw on small instances; obligation checker |

## Decisions and simplifications in this milestone, each a D-layer choice

- **Labels.** A move's label is x alone. Everything else, such as kcw's i, is a deterministic function of (S, x) and is recomputed on replay (O4).
- **Maintained quantities.** Only set-valued, state-level quantities, such as kpw's nb = ⋃ N_in(S), are maintained. Children are copies (W words each), so no undo log is needed.
  - Quantities indexed by vertex, such as kcw's a[v] = |N(v) ∩ S|, are evaluated directly as W-word popcounts.
  - This is optimal for W ≤ 4. For larger W it is slower than kcw's O(deg) updates; this is measured below, not assumed away.
- **Keys** are stored unpacked, as W words. The packed |C|-bit key is milestone 2.
- **Closure.** Closure is a sweep to the fixpoint by default. It uses `trigger="neighbours"`, a worklist over the neighbours of newly added vertices, when the lemma checker confirms that S occurs in the predicate only inside N(v) ∩ S.
  - Closure predicates must be monotone in S. The checker tests this on random sets.
  - Under monotonicity the closure set does not depend on the order of additions.
- **Arc cost.** It is derived as f(S + x), rewritten as above, unless a closed form is given. A spec with a prefix must give a closed form in compiled mode; check() verifies it in eager mode.
- **Compiled-mode restriction.** Compiled mode requires every closure rule to carry the `greedy` lemma, so that closure steps never raise the cost and the cost is known before the move is applied.
  - Treewidth's `simplicial` closure can raise the cost, so treewidth is eager-only.
  - In eager mode the derived cost is the exact running maximum over the whole block.
- **Rescan.** `window` is used when the key is the identity, as in kpw, and `full` otherwise. Probing before closure is allowed only with the identity key.
- **Components** are split in Python (`lemma.components`: the width of a disjoint union is the maximum). This is valid for vertex separation and cutwidth.
- **Engine location.** `src/C/dsl_engine.h` is found relative to the package source tree (an editable/uv install). `KPW_ENGINE` overrides this.

## Acceptance

- Widths agree with brute force (n ≤ 10) in both modes, for random graphs and digraphs.
- Widths agree with kpw/kcw on `data/` and on Coudert's small graphs and grids.
- Times are compared with kpw/kcw and reported, including where the 1.3× target is missed.

## As built (2026-11-20)

How the implementation differs from the plan above:

- **Window rescan in every mode.** The validity condition (moves of cost ≤ lo were offered at the previous scan) holds whatever the key, so the identity-key restriction was unnecessary.
- **Counter families were added.** They are needed for parity at large W. The D layer accepts `maintain=[lambda S, v: card(N(v) & S)]`:
  - The generator reads |F(e) ∩ S|, for any vertex expression e, from `mt->c[e]`.
  - It applies moves in place, with `st_add` / `st_del`, and undoes them from the recorded block.
  - This is the `maintain … incremental … undo-log` annotation of the design.
- **Prefix collection.** The prefix is collected on the unmodified state before any vertex is added, so it is correct in both modes.
- **Canonical bound variables.** Bound variables of comprehensions are named β<k>, so that alpha-equivalent traces are the same hash-consed node. Without this, kcw's Y would have been computed four times.
- **The root block's cost** is included in eager mode. It is 0 for greedy closures; treewidth's simplicial closure needs it.

### Results (2-core container, both sides single-threaded, run back to back)

**Correctness.**
- `check()` passes for all spec variants, against brute force with n ≤ 10 (over 2,000 random graphs and digraphs in development runs). Every eager arc satisfies O1, O3 and O4, and the closure hypotheses hold on random sets.
- `tests/test_dsl.py` (10 tests) runs a smaller version of this, plus parity checks against kpw and kcw.

**Vertex separation vs kpw**, on 61 benchmark graphs:
- All widths agree.
- Total time is 11.9 s against 17.1 s for kpw.
- With `greedy2`, the total is 7.3 s against kpw -g's 6.1 s (worst single instance 1.45×). The rule-2 closure is evaluated by full sweeps; kpw scans only nb ∖ S.

**Cutwidth vs kcw**, on the 156 graphs of `doc/cutwidth_comparison.md`:
- All widths agree.
- On the 14 graphs where kcw needs more than 0.3 s, the time ratio is 0.20–0.92 (0.85 on fs_680_1, n = 680; 0.90 on Grid12x27).
- State counts are identical on grids, square-sum graphs and Harwell–Boeing instances. On a few random graphs they differ slightly (319 vs 341 states); the tie-break that causes this has not been identified.

**Treewidth** runs in eager mode with no engine changes. Compiled mode correctly refuses it, because its closure is justified by `simplicial`, not `greedy`.

### Left for milestone 2

- A closure worklist for predicates that depend on S other than through N(v) ∩ S. This is kpw's rule 2.
- Packed keys (|C| bits).
- DAG output (`-c`), label-only parents (`-x`), threads (`-t`).
- The `bound` clause (A\*).
- Printing named subexpressions (`let`), so that `pretty()` shows Y and i instead of inlining them.
