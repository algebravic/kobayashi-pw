# kobayashi-pw

This program computes the exact pathwidth (vertex separation number) of undirected graphs and digraphs, together with an optimal ordering. It is based on Kobayashi's relevant-set DP (Kobayashi, *IPL* 115 (2015) 310–312), driven by a bucketed bottleneck search, so no bound k has to be supplied.

## Usage

```
uv run kobayashi-pw data/g1.txt --stats          # edge list: "u v" per line, lone token = isolated vertex
uv run kobayashi-pw graphs.g6                     # one graph6 (or digraph6, '&' prefix) per line
uv run kobayashi-pw arcs.txt --directed           # "u v" = arc u -> v
uv run kobayashi-pw data/g1.txt --upper 10        # decision mode: stops once pw > 10 is known
uv run kobayashi-pw data/g1.txt --alg1 11         # the paper's Algorithm 1 run literally, for cross-checks
uv run pytest -q
```

The CLI checks every ordering it prints with `ordering_width`, which recomputes the width directly from the order and does not use the search.

## Design

The notation follows the paper. N(U) is the set of in-neighbours of U lying outside U. A vertex x is subsumed by U if N⁻(x) ⊆ U ∪ N(U). U\* is the expansion of U, and U is relevant if U\* = U. The cost of a step is w(U,x) = |N(U∪{x})|.

1. **The cost of a step does not depend on k.** If x is subsumed by U, then N(U∪{x}) ⊆ N(U). So every edge U → (U∪{x})\* has the single cost w(U,x). The vertex separation number equals the minimum bottleneck (the max edge cost along a path) from ∅\* to V in the DAG of relevant sets. Lemma 2 of the paper, applied at k = pw, shows that this minimum is attained.
2. **Bucketed Dijkstra.** The search works through levels c = 0, 1, 2, …. A set first reached at level c has optimal bottleneck exactly c, because every lower level was exhausted first. Therefore the first time V is reached, c = pw. Every set expanded has bottleneck ≤ pw, so the search does no more expansion work than one run of Algorithm 1 at k = pw. It is usually less, because it stops as soon as V appears at level pw (see the `per_level` statistics).
3. **Memory.** Each discovered set S is stored once, in the bucket of its smallest step cost above the current level, instead of storing one entry per rejected pair (S, x). When the search reaches that level, S is rescanned and rescheduled.
4. **Ordering extraction.** Each set keeps a pointer (parent P, vertex x). The ordering is the concatenation, from ∅\* forward, of the segments [x] + (expansion order of P∪{x}). Expansion vertices are recomputed one at a time, each one subsumed by the set as it stands at that moment. **That order matters**, because a vertex may become subsumed only after other expansion vertices have been added. The parent recorded at first discovery is optimal.

`src/C/kpw.c` is a direct port with n ≤ 64 and `uint64_t` masks, written to measure the speedup. On the test graphs it reports the same numbers of sets, pairs and rescans as the Python version. Build it with `cc -O3 -march=native -o kpw src/C/kpw.c`.

## Verification (empirical)

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
