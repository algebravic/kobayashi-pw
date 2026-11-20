# `src/C/bab.c`: a C translation of the Coudert–Mazauric–Nisse branch and bound

## What was translated

`bab.c` translates the following from SageMath (`sage/graphs/graph_decompositions/vertex_separation.pyx`):

- `vertex_separation_BAB`, the driver;
- `vertex_separation_BAB_C`, the recursion.

It keeps Sage's conventions: the boundary of a prefix S is N⁺(S) \ S, using out-neighbours. Since vs(D) = vs(Dᴿ), the width equals kpw's in-neighbour width, but the orderings differ.

| Sage (Cython) | C |
|---|---|
| `binary_matrix_t` rows, `FrozenBitset` | `uint64_t` words; any n (`nw = ⌈n/64⌉`) |
| `bitsets` pool of 3n+2 | the same pool, indexed by `level` |
| `prefix_storage`: a Python `set` of `frozenset`s | an open-addressing hash set of bitsets |
| `delta_i` pairs sorted with `sort()` | `qsort` on (Δ, vertex), the same tie order |
| `cut_off`, `upper_bound`, `max_prefix_length`, `max_prefix_number`, `verbose` | `-k`, `-u`, `-l`, `-m`, `-v` |

The steps are the same:

1. Greedy step: the Δ ≤ 0 vertices (CMN Lemma 6).
2. Branching in increasing Δ.
3. The lower-bound cut `max(lb, |N⁺(S)|)`.
4. Storing prefixes only when the prefix length is ≤ `max_prefix_length`, and only while the store holds fewer than `max_prefix_number`.
5. Updating the upper bound and the best ordering.

The program checks its returned ordering independently before it prints it.

## Parity with Sage

`bench/bab_parity.py` needs Sage (`passagemath-graphs`). It runs both programs and compares four things: the width, the full sequence of improved upper bounds (from verbose output), the number of stored prefixes, and the ordering.

It ran on 463 cases:

- random graphs and digraphs with n ≤ 16;
- the variants `-l 3`, `-m 5`, `-k 3` and `-u 3`;
- the benchmark graphs with n ≤ 50.

There were **0 differences**. This is empirical agreement, not a proof of equivalence. One possible source of divergence remains: Sage's `sort()` on tuples (Δ, v) and `qsort` on the same key give the same order because the key has no ties.

## Timings

All times are wall-clock seconds on one core of the same machine, from a single run each. Column notes:

- "Sage" is `vertex_separation_BAB` with default limits.
- "kpw" is `kpw -q`, without `-g`.

| graph | n | pw | Sage | C bab | kpw | Sage / C | C / kpw |
|---|---|---|---|---|---|---|---|
| sq59 | 59 | 13 | 2.08 | 0.49 | 0.26 | 4.2 | 1.9 |
| sq61 | 61 | 14 | 4.71 | 1.28 | 0.65 | 3.7 | 2.0 |
| sq63 | 63 | 14 | 2.71 | 0.75 | 0.42 | 3.6 | 1.8 |
| gnp_n60_d3_s0 | 60 | 11 | 12.18 | 2.80 | 1.36 | 4.4 | 2.1 |
| gnp_n60_d4_s2 | 60 | 12 | 7.87 | 1.93 | 0.64 | 4.1 | 3.0 |
| gnp_n60_d5_s0 | 60 | 16 | 5.38 | 1.44 | 0.71 | 3.7 | 2.0 |

The translation is about **3.6–4.4×** faster than Sage. That gain comes from the bitset hash set and the absence of Python objects in the inner loop; the search is the same. kpw is still about **2–3×** faster than C bab, so the comparison in the paper does not change in kind.

### Default prefix limits

Four instances run for more than 120 s in Sage and more than 300 s in C bab with the defaults (`max_prefix_length = 20`, `max_prefix_number = 10⁶`). With `-l 64 -m 10000000` they finish quickly:

| graph | pw | C bab, raised limits | nodes | stored prefixes | kpw | kpw sets |
|---|---|---|---|---|---|---|
| gnp_n60_d4_s0 | 14 | 10.94 | 25,208,202 | 3,434,689 | 4.15 | 3,019,891 |
| gnp_n60_d4_s1 | 13 | 2.93 | 7,347,484 | 1,032,228 | 1.68 | 998,184 |
| gnp_n60_d5_s1 | 17 | 4.55 | 10,963,993 | 1,788,341 | 1.53 | 1,194,285 |
| gnp_n60_d5_s2 | 16 | 3.30 | 7,643,257 | 1,249,701 | 1.63 | 1,200,576 |

What goes wrong is the store, not the branching. Once a store limit stops prefixes from being recorded, the same prefixes are explored again and again. When storage is unlimited, the number of stored prefixes is within about 1.04–1.5× of kpw's set count. This fits the view of BAB with full memoisation as a depth-first version of the same relevant-set search. That view is an observation, not a theorem: BAB stores a prefix only when it is not cut by the bound, and that is not exactly Kobayashi's relevant-set family.
