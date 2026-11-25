# kobayashi-pw

This program computes the exact pathwidth (vertex separation number) of undirected graphs and digraphs, together with an optimal ordering. It is based on Kobayashi's relevant-set DP (Kobayashi, *IPL* 115 (2015) 310–312), driven by a bucketed bottleneck search, so no bound k has to be supplied.

## Usage

```
uv run kobayashi-pw data/g1.txt --stats          # edge list (see "Input" below)
uv run kobayashi-pw graphs.g6                     # one graph6 (or digraph6, '&' prefix) per line
uv run kobayashi-pw arcs.txt --directed           # "u v" = arc u -> v
uv run kobayashi-pw data/g1.txt --upper 10        # decision mode: stops once pw > 10 is known
uv run kobayashi-pw data/g1.txt --alg1 11         # the paper's Algorithm 1 run literally, for cross-checks
uv run kobayashi-pw data/sq63.txt --greedy2       # second greedy rule (Coudert et al. 2014): same pw, fewer sets
uv run kobayashi-pw data/sq63.txt --reverse       # print the ordering in the frontier-DP convention
make -C src/C                                     # optional: the programs are compiled on first use (see "Building")
src/C/kpw2 -q -t 0 data/sq75.txt                  # n up to 128, all cores
src/C/kpw2 -q -x data/sq75.txt                    # compact table: store only the arc label
src/C/kpw -c -o sq63.dag data/sq63.txt            # complete mode: DAG of all relevant pw-optimal orderings
uv run kobayashi-pw-orders data/sq63.txt          # exact V7 optimum over that DAG (frontier-DP order)
src/C/kopt -m v7 sq63.dag                         # the same optimum in C (also -m v2, -m loglin -B ...)
uv run kobayashi-pw-orders data/sq63.txt --cost v2 --k 5 --sample 10
uv run pytest -q
```

### Input

All programs (`kobayashi-pw`, `kobayashi-pw-orders`, `kpw`, `kpw2`) read edge lists in the networkx style: one edge per line, "u v [data...]", whitespace separated. Anything after the first two tokens, such as `{}` or a weight, is ignored. A line with one token declares an isolated vertex, and `#` starts a comment. Vertex names are arbitrary strings, and orderings are printed with those names.

Internally, vertices are numbered 0..n−1:
- if every name is an integer (`-?[0-9]+`) and the values are distinct, by increasing value;
- otherwise by order of first appearance.

The C programs (`src/C/edgelist.h`) and the Python reader (`kobayashi_pw.io.number_names`) use the same rule, so they search identically. The square-sum files labelled 1..n therefore give n vertices, with no phantom vertex 0.

### Building

**No build step is needed.** The C programs (kpw, kpw2, kopt, kcw, bab, fullcount) are compiled on first use by `kobayashi_pw.native`, which works the same for a source tree, an editable install and an installed wheel.

- **Sources.** The wheel ships the sources as `kobayashi_pw/_csrc`. In the repository they stay in `src/C`, and `pyproject.toml` (hatchling) maps them into the wheel.
- **Compilation** uses `cc -O3 -march=native` (`$CC` overrides the compiler). The binary goes to `~/.cache/kobayashi_pw/bin/<key>/` (`$KPW_CACHE` overrides the location).
- **The cache key** covers the source, the headers, the flags, the compiler version and the machine type, so an edited source is rebuilt on the next call.
- **Word count.** kpw2 and kopt are built with the word count W that n requires (n ≤ 64·W, with W ∈ {1, 2, 3, 4, 8, 16}), so there is no fixed n ≤ 128 limit.
- **Concurrency.** Concurrent processes compile once, under a file lock.

```
uv run kobayashi-pw-build                  # optional: compile everything now (e.g. before a batch job)
uv run kobayashi-pw-build --n 200 kpw2     # kpw2 for n <= 256
KPW_BIN_KPW2=/path/to/kpw2 ...             # use a hand-built binary instead
```

From Python, `kobayashi_pw.native.program(name, n)` returns the path; `try_program` returns `None` when no compiler is available. `kobayashi-pw-orders` uses kpw for n ≤ 64 and kpw2 beyond that, and falls back to Python if neither can be compiled. Pass `--threads N` to give kpw2 N threads.

`make -C src/C` still builds the programs in place, for development and benchmarks.

### Embedded DSL (`src/kobayashi_pw/dsl/`): specifications compiled to C on demand

```python
from kobayashi_pw import read_edge_list
from kobayashi_pw.dsl import cutwidth, vertex_separation, treewidth
P = cutwidth()                      # about 20 lines in dsl/specs.py
print(P.pretty()); print(P.report())        # the spec, and the lemma behind each clause
s = P.solve(read_edge_list("data/sq61.txt"))  # generates C, compiles, caches (~/.cache/kobayashi_pw)
s.width, s.order, s.stats
P.check(n_max=9, trials=200)                # obligations O1–O4 and widths vs brute force
treewidth().solve(small_graph, mode="eager")  # IR interpreter (the reference semantics)
```

The design is in `doc/dsl_design.md`, and the plan and results of the first milestone are in `doc/dsl_milestone1.md`. The generated vertex separation and cutwidth programs reproduce kpw and kcw: the same widths, and the same state counts on structured graphs. They run at 0.2–0.9× the hand-written programs' time, except for kpw's `-g`, where they take up to 1.45×.

**Secondary costs** (`doc/dsl_secondary_design.md`). A spec can also declare `P.secondary(step, name, by=lemma.pareto_monotone | lemma.additive)`, where `step(T, v)` returns (a, e, k) for one step of the frontier-DP ordering. `solve(..., output="pareto", secondary=name, params=...)` then minimises that cost exactly over every optimal ordering of the move graph (engine E2, `src/C/dsl_dagopt.h`).
- **IR.** It gains reals (`real`, `rexp`, `rlog`, `rpow`, `rmin`, `rmax`), constant tables, runtime parameters (`param`; refits need no recompilation), `width()`, `nverts()` and `comp_sum` over connected components.
- **The hampath costs** V2, V7 and the log-linear work model are in `dsl/hampath.py`. They give the same orderings as `orders.optimize` and `kopt` (`tests/test_dsl_secondary.py`). `check_secondary()` compares E2 with brute-force enumeration of all paths on random graphs.
- **Speed** relative to kopt is recorded in `doc/dsl_codegen_perf.md`.

### Lean formalisation (`lean/`)

`lake exe cache get && lake build` in `lean/` checks machine proofs of:
- the move-system value theorem;
- the engine's level-by-level correctness;
- the greedy lemma;
- the correctness of kpw (with or without `-g`) and of the cutwidth search with the rank closure.

What is and is not covered is listed in `lean/README.md`.

### kcw (`src/C/kcw.c`): exact cutwidth

```
src/C/kcw data/sq63.txt                      # n=63 ... cw=25 (about 30 s); then the ordering
src/C/kcw -q -T 60 -M 50000000 g.txt    # stop after 60 s or 5e7 states; reports a certified lb=B
```

kcw runs the same one-pass bottleneck search as kpw, applied to cutwidth. It uses three reductions:
- the rank closure;
- the Cygan et al. vertex-cover normal form, so that states are subsets of the cover;
- twin symmetry breaking.

Each can be turned off: `-C` turns off the cover restriction and `-W` turns off twins. The design is in `doc/kcw_design.md`. `doc/cutwidth_comparison.md` compares kcw, on the same machine, with Coudert's BB+ and BB3+ on his benchmark collections.

### bab (`src/C/bab.c`): Coudert–Mazauric–Nisse branch and bound

A C translation of SageMath's `vertex_separation_BAB` (Cython, by David Coudert), kept for comparison. It makes the same branching and pruning decisions as Sage: on 463 test cases it gives the same width, the same sequence of improved upper bounds, the same stored-prefix count and the same ordering (`bench/bab_parity.py`, needs Sage). Any n is accepted. Flags: `-d` directed, `-k CUT_OFF`, `-u UPPER_BOUND`, `-l MAX_PREFIX_LENGTH` (default 20), `-m MAX_PREFIX_NUMBER` (default 10^6), `-r`, `-q`, `-v`. Its boundary uses out-neighbours (Sage's convention); it has the same width as kpw's in-neighbour boundary. Timings are in `doc/bab_port.md`.

**Licence:** `bab.c` is derived from GPL-2+ Sage code and is itself GPL-2-or-later; see its header.

### kopt (`src/C/kopt.c`): exact secondary-cost optimisation in C

`kopt -m MODEL [-b C] [-a A] [-B b0,...,b10] [-L max_labels] [-q] DAGFILE` reads a DAG written by `kpw -c -o` or `kpw2 -c -o` and runs the same Pareto-label DP as `orders.optimize`:
- the arcs are recomputed with the same expansion order, so the blocks are the same;
- the step features are those of `orders.tau_block_features`;
- ties break as in Python's stable sort.

Models:
- `v2`;
- `v7`, with `-b` expand_base and `-a` density_alpha;
- `loglin`, the predicted-work model `make_model_loglin`: a = 0, e = 2^nb, k = exp(β·x)/2^nb, with x = `WORK_FEATURES` and the 11 coefficients given by `-B`.

`-L` keeps at most that many labels per node; the output then reports `exact=0`. The ordering is printed in the frontier-DP direction, with the file's vertex names.

From Python, call `orders.optimize_file(path, cost, beta=..., ...)`. kopt is compiled on first use with the word count the DAG needs (see "Building").

Agreement with `optimize` is tested (`tests/test_kopt.py`): the same cost to 1e-9, and equality with brute-force path enumeration on random graphs, with and without `-g`. On the square-sum graphs the orderings are identical to Python's.

Timings and memory (2-core container):

| n | nodes | arcs | v7 | loglin (labels; peak RSS) |
|---|---|---|---|---|
| 57 | 13 762 | 86 555 | 0.11 s | 0.30 s (0.70 M labels; 19 MB) |
| 61 | 263 672 | 2.17 M | 3.3 s | 14.1 s (23.0 M labels; 616 MB) |
| 75 | 132 400 | 1.08 M | 1.7 s | 8.4 s (14.4 M labels; 411 MB) |

The Python `optimize` takes 15.5 s at n = 57 for `loglin`, and several minutes at n = 59–61. A label takes 24 bytes. All fronts are kept for the traceback, so memory grows with the total number of labels.

### kpw2 (`src/C/kpw2.c`)

kpw2 takes the same flags as kpw, plus three extensions:
- **More than 64 vertices.** Sets are W-word bitsets, set at compile time with `-DW=k` for n ≤ 64k.
- **`-x`.** Stores (set, arc label, parent size) instead of the parent set, which makes the table 40% smaller. Each predecessor is recovered by one table scan per extraction step.
- **`-t N`.** Runs N threads (`0` = all cores), sharing each level through work stealing.

Two other changes are internal. Rule-1 expansion is a worklist over the out-neighbours of newly closed vertices. The stack holds one item per set with a mask of the labels still to try. With `-t 1` the counts are identical to kpw.

Design and measurements are in `doc/kpw2_design.md`.

### Other widths

`doc/other_widths.md` investigates cutwidth, treewidth and bandwidth. `src/kobayashi_pw/widths.py` is a Python prototype of the same one-pass search for vertex separation, cutwidth (exact, using an optional vertex cover) and treewidth (elimination orderings).

### The DAG file (`-c -o FILE`)

Both programs write format `KPWDAG3`: the header, the in-neighbour sets, the stored relevant sets, and the vertex names. `doc/dag_format.md` defines the layout and what the file means: which sets are stored, how the arcs are recomputed, how a path becomes an ordering, and the older formats `KPWDAG1`/`KPWDAG2`, which `OrderDAG.load` still reads.

### Orientation of the printed orderings

`kobayashi-pw` and `kpw` print orderings in Kobayashi's convention, where the width is max |N(S_i)| over prefixes S_i and N(S) is the set of vertices outside S adjacent to S. A left-to-right frontier DP counts the *placed* vertices that still have an unplaced neighbour. For undirected graphs that is the reverse ordering, so use `--reverse` (or `kpw -r`). `kobayashi-pw-orders` always prints frontier-DP orderings.

The CLI checks every ordering it prints with `ordering_width`, which recomputes the width directly from the order and does not use the search.

## Design

The notation follows the paper. N(U) is the set of in-neighbours of U lying outside U. A vertex x is subsumed by U if N⁻(x) ⊆ U ∪ N(U). U\* is the expansion of U, and U is relevant if U\* = U. The cost of a step is w(U,x) = |N(U∪{x})|.

1. **The cost of a step does not depend on k.** If x is subsumed by U, then N(U∪{x}) ⊆ N(U). So every edge U → (U∪{x})\* has the single cost w(U,x). The vertex separation number equals the minimum bottleneck (the max edge cost along a path) from ∅\* to V in the DAG of relevant sets. Lemma 2 of the paper, applied at k = pw, shows that this minimum is attained.
2. **Bucketed Dijkstra.** The search works through levels c = 0, 1, 2, …. A set first reached at level c has optimal bottleneck exactly c, because every lower level was exhausted first. Therefore the first time V is reached, c = pw. Every set expanded has bottleneck ≤ pw, so the search does no more expansion work than one run of Algorithm 1 at k = pw. It is usually less, because it stops as soon as V appears at level pw (see the `per_level` statistics).
3. **Memory.** Each discovered set S is stored once, in the bucket of its smallest step cost above the current level, instead of storing one entry per rejected pair (S, x). When the search reaches that level, S is rescanned and rescheduled.
4. **Ordering extraction.** Each set keeps a pointer (parent P, vertex x). The ordering is the concatenation, from ∅\* forward, of the segments [x] + (expansion order of P∪{x}). Expansion vertices are recomputed one at a time, each one subsumed by the set as it stands at that moment. **That order matters**, because a vertex may become subsumed only after other expansion vertices have been added. The parent recorded at first discovery is optimal.

5. **Second greedy rule (`--greedy2`, `kpw -g`).** Coudert, Mazauric and Nisse (2014, Lemma 6) prove two greedy steps for their branch and bound. Their first is exactly Kobayashi's subsumption, with arcs mirrored. Their second adds v ∈ N(U) when exactly one in-neighbour of v lies outside U ∪ N(U); this keeps |N| unchanged and preserves strong k-feasibility. Applying both rules in the expansion leaves pw and the search's correctness unchanged, and reduces the number of sets 2–6× on square-sum graphs. The resulting DAG contains far fewer orderings, so it is off by default for `kobayashi-pw-orders`.
6. **Complete mode and many orderings (`kpw -c`, `OrderDAG`).** Level pw is finished instead of stopping at V, which gives all relevant sets of bottleneck ≤ pw. One backward pass then keeps the sets from which V is reachable through arcs of cost ≤ pw. Every path from ∅\* to V is a pw-optimal ordering. The arcs are not stored: from S they are the x with |N(S∪{x})| ≤ pw. `OrderDAG.sample` draws orderings uniformly from the paths.
7. **Exact secondary-cost optimisation (`orders.optimize`).** All step features used by the hampath cost models (frontier size, back-edges into the frontier, frontier edges, components of G[frontier], eliminations, step index) are functions of (prefix, next vertex). A model returns (a, e, k) per step, applied as `cost += a + p·e; p ← max(p·e·k, 1)`.
   - Additive costs (V2) use e = 0, and the problem is a shortest path; `k_best` gives the k best orderings exactly.
   - Proxy costs (V5–V7) are handled exactly by keeping, per node, the Pareto front of (cost, p). This is exact because the cost-to-go is nondecreasing in p.
   - `optimize_all` does the same over *all* pw-optimal orderings, for validation on small graphs.

`src/C/kpw.c` is a direct port with n ≤ 64 and `uint64_t` masks, written to measure the speedup. On the test graphs it reports the same numbers of sets, pairs and rescans as the Python version. Build it with `cc -O3 -march=native -o kpw src/C/kpw.c`.

## Verification (empirical)

- `tests/test_orders.py`:
  - every DAG path is pw-optimal in the frontier convention;
  - `optimize` and `k_best` equal brute-force enumeration of all DAG paths (V2 and V7);
  - the DAG optimum is never below `optimize_all`;
  - the C dump equals the Python DAG;
  - `--greedy2` agrees with brute force.
- **Agreement with the hampath code**, checked separately: `tau_features(...).fw` equals `ham_ordering.frontier_width`, and `evaluate(..., model_v7)` equals `ham_ordering._dp_cost` to 1e-9 on sampled orderings of G_25–G_45 and on the optima for G_57–G_61.

`tests/` compares against a brute-force 2ⁿ subset DP on 3000 random graphs and digraphs with n ≤ 10. It checks the returned width, the width of the extracted ordering, decision mode at pw − 1, and the literal Algorithm 1 at pw and pw − 1. It also checks known values: paths, cycles, K₇, stars, the 3×3 grid, acyclic digraphs (pw 0) and the Petersen graph (pw 5).

## Timings (one machine, random G(n,p) in data/)

| graph | n | pw | relevant sets | Python | C | ratio |
|---|---|---|---|---|---|---|
| g1 | 40 | 11 | 4 022 | 0.22 s | 0.009 s | ~24× (C time is mostly startup) |
| g3 | 45 | 15 | 19 608 | 1.45 s | 0.026 s | ~56× |
| g2 | 60 | 11 | 732 821 | 66–70 s | 1.13 s | ~60× |

Peak memory on g2 was 854 MB for Python and 288 MB for C.

The literal Algorithm 1 at a loose bound shows the cost of overshooting k:

| graph | k = pw | pw + 2 | pw + 4 |
|---|---|---|---|
| g1 | 0.62 s | 4.7 s | 28.6 s |
| g3 | 3.7 s | 24.0 s | — |

The bucketed search took 0.22 s on g1 and 1.45 s on g3.
