# Changes (8): Lean formalisation; codegen closure push-down

- **`lean/`** (new): a Lean 4.36 / Mathlib v4.36 formalisation with no `sorry`; the axiom audit shows only `propext`, `Classical.choice` and `Quot.sound`. It proves:
  - the move-system value theorem (`value_iff`);
  - the facts behind engine E (`width_eq_of_first`, `width_ge_of_interrupted`, `closed_eq_reach`, `skip_levels`);
  - the greedy lemma and the completeness of greedy-closure systems (`greedySystem_value`);
  - **kpw is correct**, with rule 1 or rules 1 + 2 (`kpw_value`);
  - **the cutwidth search with the rank closure is correct** (`kcw_closure_value`).

  The cover normal form and twins are not yet formalised. See `lean/README.md`.
- **`dsl/codegen.py`**: guard push-down. A closure rule `v ∈ A(S) ∧ …` now scans only A(S) ∖ T, and rules are swept one at a time to the fixpoint. With `-g`, DSL vertex separation goes from 7.3 s to 3.5 s on the benchmark set, against kpw -g's 5.3 s. See `doc/dsl_codegen_perf.md`.
- **`impl(carry=…)`**: maintained sets can be stored with each state instead of recomputed on decode. The default is off, because measurement showed no gain.

# Changes (7): the embedded DSL, milestone 1

- **`src/kobayashi_pw/dsl/`** (new): an embedded DSL for set-determined layout searches.
  - `ir.py`: a hash-consed typed IR built by symbolic tracing.
  - `problem.py`: the `Problem` clauses (cost, closure, choose, symmetry, key, components) and `impl` (Layer D).
  - `lemma.py`: the lemma library, with syntactic and run-time hypothesis checks.
  - `eager.py`: the reference interpreter, engine E, brute force, and the obligation checker.
  - `rewrite.py`: derivation of arc costs.
  - `codegen.py`: lowering to C (word-wise sets, popcounts, bit loops, worklist closure, maintained sets, counter families with in-place apply/undo).
  - `jit.py`: compile on demand with a SHA-256-keyed cache, ctypes, Ctrl-C.
  - `specs.py`: vertex_separation, cutwidth, treewidth.
- **`src/C/dsl_rt.h`, `src/C/dsl_engine.h`** (new): the hand-written engine that the generated ops plug into.
- **`doc/dsl_design.md`** (design) and **`doc/dsl_milestone1.md`** (plan, as built, results).
- **`tests/test_dsl.py`** (10 tests; 46 in total).

# Changes (6): exact cutwidth in C (kcw); comparison with Coudert's cutwidth B&B

- **`src/C/kcw.c`** (new): exact cutwidth for any n.
  - The search is the bucketed bottleneck search, with:
    - the rank closure;
    - the vertex-cover normal form of Cygan et al.: an exact König cover on bipartite graphs, a greedy cover otherwise, with hash keys = S ∩ C;
    - twin symmetry breaking, which is new;
    - connected components solved separately.
  - `-T` and `-M` limits; an interrupted run reports a certified lower bound.
  - Every ordering it prints is re-checked.
  - Design: `doc/kcw_design.md`.
- **`doc/cutwidth_comparison.md`** (new): kcw against Coudert's BB+ and BB3+, compiled here from his Cython, on the same machine.
  - Over 156 graphs with a 300 s limit: kcw solves all of them, and BB+/BB3+ solve 147.
  - Where both solve and either needs more than 0.1 s, kcw is 2.5–2,200× faster, with a median of 37×.
  - kcw also gives Grid15x15, 15x18 and 15x21, which are open in his runs, and exact values for 50 GPW2024 instances.
- **`bench/cutwidth/`** (new): drivers and the build for his code. **`data/cutwidth/`** (new): his instances and recorded results, and our runs.
- **`tests/test_kcw.py`** (5 tests; 36 in total).

# Changes (5): C translation of Coudert et al.'s BAB

- **`src/C/bab.c`** (new, GPL-2+): a C translation of Sage's `vertex_separation_BAB` / `vertex_separation_BAB_C`, for arbitrary n.
  - Prefix storage is a hash set of bitsets, in place of a Python set of frozensets.
  - It uses the same branching order and tie-breaks, the same bounds, and the same prefix-storage limits as Sage.
- **`bench/bab_parity.py`** (new, needs Sage): compares with Sage step for step. Over 463 cases there were 0 differences.
- **`doc/bab_port.md`** (new): timings of Sage, C bab and kpw.
- **`src/C/edgelist.h`**: its functions are now `static inline`, which avoids unused-function warnings.
- **`tests/test_bab.py`** (3 tests; 31 in total).

# Changes (4): other widths (investigation)

- **`doc/other_widths.md`** (new): whether the kpw ideas carry over to cutwidth, treewidth and bandwidth.
  - A general greedy lemma for submodular prefix costs, which contains Kobayashi's rule and Coudert–Mazauric–Nisse's rule 2 as its two cases.
  - Exact cutwidth via the same search, with Cygan et al.'s vertex-cover normal form.
  - Measurements on G_n: cw(G₆₀) = 22.
- **`src/kobayashi_pw/widths.py`** (new prototype): a heap-based bottleneck engine, with plug-ins `vertex_separation`, `cutwidth` and `treewidth`, brute-force references, and width checkers.
- **`tests/test_widths.py`** (4 tests; 28 in total).

# Changes (3): named vertices; DAG format documented

- **Edge lists with arbitrary vertex names** in `kpw` and `kpw2`, through a new shared parser `src/C/edgelist.h`:
  - networkx style: "u v [data...]", where extra fields such as `{}` are ignored, a lone token is an isolated vertex, and `#` starts a comment;
  - vertices are numbered 0..n−1 internally, by increasing value if all names are distinct integers and by first appearance otherwise;
  - orderings are printed with the input names, and `-r` still reverses them.
  - The square-sum files labelled 1..n now give n vertices, with no phantom vertex 0. For sq63 that is n = 63, and the counts are unchanged.
- **The Python reader uses the same rule** (`kobayashi_pw.io.number_names`). It used to merge names with equal integer value, such as `07` and `7`, and to accept `--5` as an integer.
- **DAG format 3 (`KPWDAG3`)**, written by both programs, adds the vertex names. `OrderDAG.load` reads formats 1–3; with format 3 the labels are the names.
- **`doc/dag_format.md`** (new) defines the layout and what the file means.
- **`tests/test_edgelist.py`** (5 tests; 24 in total).

# Changes (2): kpw2 — more than 64 vertices, restricted expansion, compact parents, threads

- **`src/C/kpw2.c`** (new; design and measurements in `doc/kpw2_design.md`):
  - **W-word sets** (`-DW`, default 2: n ≤ 128).
  - **Worklist rule-1 expansion** over the out-neighbours of newly closed vertices. It produces the same sets and counts as kpw.
  - **One stack item per set,** holding a label mask. Same order as kpw, with about a third of the memory.
  - **`-x`**: compact table with predecessor recovery by table scan.
  - **`-t N`**: pthreads with work stealing and a sharded spin-locked table.
  - **`KPWDAG2`** dump format.
- **`OrderDAG.load`** reads both formats. `kobayashi-pw-orders` picks kpw2 for n > 64 and has a new `--threads` option.
- **`tests/test_kpw2.py`** (7 tests; 19 in total).
- **`data/sq61.txt`, `data/sq65.txt` … `data/sq75.txt`.**
- **Results:**
  - pw(G₆₅, G₆₇, G₆₉, G₇₁, G₇₃) = 14 and pw(G₇₅) = 15, each in under a second (`-g`). G₆₅, G₆₇ and G₇₅ were checked against Python.
  - Four threads give about 2–2.5×.

# Changes: complete DAG, secondary-cost optimisation, second greedy rule, BAB comparison

## C program (`src/C/kpw.c`; build with `make`)

| flag | effect |
|---|---|
| `-g` | Second greedy rule of Coudert–Mazauric–Nisse (2014, Lemma 6(ii)), mirrored to in-neighbours: add v ∈ N(U) when exactly one in-neighbour of v lies outside U ∪ N(U). pw and the guarantees are unchanged; stores 2–6× fewer sets. |
| `-c` | Complete mode: finish level pw instead of stopping at V, then a backward pass keeps the sets from which V is reachable through arcs of cost ≤ pw. Prints `dag=<nodes>`. |
| `-o F` | With `-c`: write the DAG (format in the source; arcs are recomputed, not stored). |
| `-r` | Print the ordering reversed (frontier-DP / Kinnersley convention). |
| `-q` | Do not print the ordering. |

Other changes:
- Labels outside 0..63 are rejected.
- n = 64 is handled: V is never stored in the hash table.

## Python

- **`core.expand` / `core.pathwidth(..., greedy2=False)`**: the same second rule. Python and C report identical counts of sets, pairs and rescans.
- **`orders.py`** (new):
  - `OrderDAG.build(g, greedy2=False)`, `OrderDAG.load(dump)`, `.num_orderings()`, `.sample(rng, k)`: uniform sampling of optimal orderings, frontier-DP direction by default.
  - `tau_block_features` / `tau_features`: per-step features in the frontier direction (fw, n_back, n_elim, e_bag, component sizes, step), with the same definitions as `hamiltonian/claude/ham_ordering._dp_cost`. In particular n_back counts only back-edges into vertices still in the frontier, and n_elim does not count a vertex whose neighbours all precede it, unless it is isolated.
  - Models: `model_v2` (additive), `make_model_v7(expand_base, density_alpha)` (proxy; equals `_dp_cost` to 1e-9). A model is any function `(features, pw) -> (a, e, k)`, applied as `cost += a + p·e; p ← max(p·e·k, 1)`.
  - `optimize(dag, model)`: exact, using Pareto labels (cost, p). `k_best(dag, model, k)`: exact for additive models. `optimize_all(g, model)`: optimum over *all* pw-optimal orderings (small graphs only).
- **`kobayashi-pw-orders`** (new command): builds the DAG with `src/C/kpw` if present, remapping labels to 0..n−1 for it and back; otherwise builds it in Python. Then prints the V7 (or V2) optimum, k best, or uniform samples, all as frontier-DP orderings.
- **`kobayashi-pw`**: new options `--greedy2` and `--reverse`.

## Tests

- 12 tests, all passing:
  - brute force for `greedy2` on graphs and digraphs;
  - every DAG path optimal in the frontier convention;
  - `optimize` and `k_best` equal full path enumeration for V2 and V7;
  - the DAG optimum ≥ `optimize_all`;
  - the C dump equals the Python DAG.
- **Separate C checks:** 6000 runs (4 modes × 1500 random graphs and digraphs) against brute force.
- **Cross-check against the hampath code:** frontier widths and `_dp_cost` match on sampled orderings of G_25–G_45 and on the optima for G_57–G_61.

## Benchmarks (`bench/`)

- **`bench_bab.py`**: kpw (`U*`, `-g`) against Sage's `vertex_separation_BAB` (passagemath-graphs; needs a Python with Sage). Results are in `data/bench/results.tsv`.
- **`bab_hard.py`**: reruns the BAB timeouts with a longer cap, using default and raised prefix limits.

## Known limitations

- The DAG contains only the orderings that take subsumed vertices eagerly. On G_20–G_28, its V2/V7 optima are within 1.5% of the optimum over all optimal orderings; this is empirical. With `greedy2` the DAG is much smaller and noticeably worse, so it is off by default for orderings.
- Python loading and optimisation take about 1 min at n = 61, against about 3 s in C for building the DAG. A C optimiser for the built-in models would be the next step if this matters.
- ConvMLP-type costs, with windows over consecutive steps, are not step-local. Use `k_best` or `sample` with reranking, or start your simulated annealing from the DAG optimum.
