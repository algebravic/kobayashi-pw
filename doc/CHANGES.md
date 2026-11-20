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
