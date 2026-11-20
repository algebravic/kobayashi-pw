# Cutwidth: kcw versus Coudert's branch and bound

This compares `src/C/kcw.c` (design in `doc/kcw_design.md`) with the exact cutwidth codes in David Coudert's repository `cutwidth` (gitlab.inria.fr/dcoudert/cutwidth). His codes are BB1, BB2, BBPR, BB+ and BB3+; BB3+ is the best-first variant with the C\* grooming lower bound from Bermond–Cosnard–Coudert–Havet (2025). The comparison uses his instance collections:
- CMPLIB 2010: "small", "grids" and Harwell–Boeing;
- GPW2024: the ER and geometric graphs, with Gaar–Puges–Wiegele's SDP bounds;
- his GNP set.

## How the runs were made

- **Same machine for both sides.** His Cython modules (`bab_dfs`, `bab_bfs`, `cstar`, `lowerbounds`, `heuristics`) were compiled here against passagemath 10.8. `bench/cutwidth/run_bab.py` reproduces `experiments/BAB.py:experiment_directory` for a single graph:
  - reduce to `reduced_homeomorphic_graph()`;
  - compute a GRASP upper bound (k = 10⁵) and `get_lowerbound(fast=False)`;
  - run BB+ or BB3+ with his parameters.
- **Hardware:** a 2-core x86-64 container. Every program is single-threaded, and two jobs ran at a time.
- **What the times mean.**
  - For BB+ and BB3+ the time is the B&B's own "overall running time". It excludes the GRASP and lower-bound preprocessing, which took 5–100 s per graph here, as in his `.res` files.
  - For kcw the time is the whole run on the original graph G. kcw does no degree-2 reduction, and none is needed: a degree-2 vertex enters by the rank closure as soon as one of its neighbours is placed.
  - The times in his `.res` files come from a different machine. They are about 5× slower than his own code here (Grid9x9, BB+: 1.44 s there, 0.19 s here), so only the same-machine numbers below are compared.
- **What kcw does.** It runs the one-pass bottleneck search with three reductions:
  - the rank closure;
  - the Cygan et al. vertex-cover normal form (exact König cover on bipartite graphs, greedy cover otherwise);
  - twin symmetry breaking.

  It has no heuristic and no lower bound beyond max ⌈deg/2⌉.

## Correctness

- **Exact values.** Every value kcw reports comes with an ordering that the program re-checks.
  - The value is optimal by the greedy lemma, Cygan et al.'s normal form, and twin swaps being automorphisms.
  - Empirically, it agrees with the 2ⁿ brute force on 5,400 runs over random, bipartite and twin-rich graphs with n ≤ 12, each with and without the cover and twin rules; `tests/test_kcw.py` repeats part of this.
- **Agreement with Coudert's results.** On the 147 graphs solved by both kcw and BB+ or BB3+, the values agree. They also agree with his `.res` files.
- **Agreement with GPW2024.** On all 30 instances with published GPW bounds that kcw solved, its value equals GPW's heuristic upper bound.
- **Lower bounds (`lb=B`).** These are proofs: all of level B − 1 was exhausted.

## 1. Same machine, 300 s per run

| set | graphs | kcw solved | BB+ solved | BB3+ solved | BB+ or BB3+ solved |
|---|---|---|---|---|---|
| grids | 53 | 53 | 46 | 47 | 47 |
| harwellboeing | 19 | 19 | 16 | 16 | 16 |
| small | 84 | 84 | 84 | 84 | 84 |

These are the 156 graphs that Coudert's own runs had solved, plus the Harwell–Boeing graphs kcw solved in a first 30 s pass.

**Instances where some solver needed more than 0.1 s**, slowest first. ">300" means no proof within the limit; for nos2 and fs_680_1, Coudert's preprocessing alone exceeded the 420 s wall-clock guard.

| graph | n | m | cw | BB+ (s) | BB3+ (s) | kcw (s) | kcw states | best BB / kcw |
|---|---|---|---|---|---|---|---|---|
| Grid12x21 | 252 | 471 | 13 | >300 | >300 | 4.63 | 1471128 | — |
| Grid12x24 | 288 | 540 | 13 | >300 | >300 | 7.95 | 2185180 | — |
| Grid12x27 | 324 | 609 | 13 | >300 | >300 | 11.5 | 3109434 | — |
| Grid21x12 | 252 | 471 | 13 | >300 | >300 | 5.31 | 1469523 | — |
| Grid24x12 | 288 | 540 | 13 | >300 | >300 | 8.1 | 2183350 | — |
| Grid27x12 | 324 | 609 | 13 | >300 | >300 | 12.7 | 3107169 | — |
| arc130 | 130 | 715 | 202 | >300 | >300 | 0.716 | 58964 | — |
| fs_680_1 | 680 | 1464 | 16 | >300 | >300 | 4.65 | 562874 | — |
| nos2 | 638 | 1272 | 4 | >300 | >300 | 0.001 | 36 | — |
| Grid12x18 | 216 | 402 | 13 | >300 | 261 | 2.66 | 936556 | 98× |
| Grid18x12 | 216 | 402 | 13 | 298 | 258 | 2.9 | 935386 | 89× |
| Grid12x15 | 180 | 333 | 13 | 142 | 151 | 1.38 | 552651 | 103× |
| Grid15x12 | 180 | 333 | 13 | 137 | 146 | 1.65 | 551706 | 83× |
| can__144 | 144 | 576 | 25 | 123 | 144 | 0.055 | 23100 | 2233× |
| Grid12x12 | 144 | 264 | 13 | 49.7 | 80 | 0.656 | 291581 | 76× |
| bcsstk01 | 48 | 176 | 32 | 16.2 | 40.1 | 0.431 | 91660 | 37× |
| bcspwr03 | 118 | 179 | 10 | 13.4 | 56.4 | 0.202 | 74608 | 67× |
| ash85 | 85 | 219 | 16 | 5.9 | 19.9 | 0.065 | 23836 | 91× |
| Grid27x9 | 243 | 450 | 10 | 10.2 | 5.19 | 0.174 | 71713 | 30× |
| Grid9x27 | 243 | 450 | 10 | 10.2 | 5 | 0.166 | 71883 | 30× |
| Grid9x24 | 216 | 399 | 10 | 6.9 | 3.74 | 0.134 | 62249 | 28× |
| Grid24x9 | 216 | 399 | 10 | 6.94 | 3.72 | 0.133 | 61665 | 28× |
| Grid9x21 | 189 | 348 | 10 | 4.32 | 2.62 | 0.099 | 38605 | 27× |
| Grid21x9 | 189 | 348 | 10 | 3.95 | 2.49 | 0.071 | 38483 | 35× |
| Grid9x18 | 162 | 297 | 10 | 2.3 | 1.82 | 0.062 | 31284 | 29× |
| Grid18x9 | 162 | 297 | 10 | 2.25 | 1.71 | 0.057 | 30880 | 30× |
| bcsstk22 | 110 | 254 | 13 | 1.7 | 9.08 | 0.107 | 30338 | 16× |
| nos4 | 100 | 247 | 12 | 1.44 | 1.63 | 0.009 | 3755 | 160× |
| ibm32 | 32 | 90 | 23 | 1.27 | 3.56 | 0.013 | 4168 | 98× |
| Grid9x15 | 135 | 246 | 10 | 1.2 | 1.13 | 0.033 | 17234 | 34× |
| will57 | 57 | 127 | 11 | 0.775 | 4.46 | 0.004 | 1778 | 194× |
| Grid9x12 | 108 | 195 | 10 | 0.503 | 0.628 | 0.026 | 12208 | 19× |
| curtis54 | 54 | 124 | 13 | 0.443 | 2.22 | 0.005 | 1867 | 89× |
| dwt__234 | 117 | 162 | 12 | 0.137 | 0.422 | 0.055 | 23587 | 2× |


On the 25 instances that both sides solve and where either needs more than 0.1 s, kcw is 2.5–2,200× faster than the better of BB+ and BB3+, with a median of 37×. It also solves six 12×k grids, arc130, fs_680_1 and nos2, which neither B&B finishes. His own 3-hour runs on his machine had solved the 12×k grids, but not arc130 or fs_680_1.

## 2. Beyond his solved set

Grid instances that Coudert's 3 h runs did not solve:

| graph | kcw | time | states |
|---|---|---|---|
| Grid15x15 | cw = 16 | 52 s | 12.5 M |
| Grid15x18 | cw = 16 | 128 s | 31.0 M |
| Grid15x21 | cw = 16 | 206 s | 44.6 M |
| Grid18x18 | cw ≥ 17 (stopped at the 110 M state limit) | 534 s | 110 M |

The three exact values equal his GRASP upper bounds, and they follow the pattern cw(P_k × P_l) = min(k, l) + 1. Every grid either code has solved fits this pattern. I believe it is the Rolim–Sýkora–Vrťo theorem on mesh cutwidth, but I have not checked the reference. kcw does not use it. For Grid18x18 the pattern predicts 19, so the search would have had to exhaust two more levels.

**Harwell–Boeing.** kcw solves 19 of 87 instances within 300 s, against 16 for his codes. On the 68 it does not solve, its 30 s certified lower bound is:
- larger than his recorded lower bound on 37;
- equal on 5;
- smaller on 26. These are mostly dense instances or instances of large width, such as mcca, the str\_\_ family, west0381, bcsstk04 and fs_183_1, where his grooming and degree bounds are strong.

Combining the two sources gives one new exact value. kcw's lower bound for saylr1 (n = 238) is 15, and his GRASP upper bound is 15, so cw(saylr1) = 15. The upper bound comes from an ordering of his reduced graph H. That transfers to G only on the assumption that the degree-2 reduction preserves cutwidth, which his pipeline assumes and which I did not check separately.

## 3. GPW2024 random graphs (n = 10–50, densities 0.3–0.9)

There are 76 instances. GPW publish SDP lower bounds and heuristic upper bounds for 56 of them, those with n = 20–50.
- **Within 30 s,** kcw solves 19 of the 36 ER graphs and 29 of the 40 geometric graphs. That covers every graph with n ≤ 20, most with n = 30, and a few geometric graphs with n = 40–50.
- **With 600 s** it also solves er27_n30_p07 (cw = 135, 116 s) and geo28_n40_p05 (cw = 92, 40 s).
- **Upper bounds.** Of the instances with published bounds, kcw solves 30, and on every one of them its value equals GPW's upper bound. So their heuristic was optimal wherever this can be checked.
- **Lower bounds.** On the unsolved instances, kcw's 30 s certified lower bound beats the SDP bound on 10 of 28:
  - ER: er27, er32 and er37 (n = 30), and er04, er10, er16 and er28 (n = 40). For example, er04 has 74 vs 60.1, and er32 has 145 vs 110.6.
  - Geometric: geo28, geo29 and geo32 (n = 40). For example, geo32 has 299 vs 245.1, with upper bound 366.
  - The SDP bound is better on all n = 50 graphs and on the densest n = 40 graphs.

## 4. GNP set (no reference results in his repository)

Within 30 s each, kcw solves 147 of 191 graphs:
- every graph with n = 25;
- every graph with n = 30 and p ≤ 0.5, and 6 of 20 at p = 0.95 (none at p = 0.8);
- every graph with n = 35, p = 0.2;
- one graph at n = 40, p = 0.2.

## Assessment

- **Where kcw wins.** On sparse structured graphs it is one to three orders of magnitude faster: grids, meshes and the CMPLIB matrices. The reasons are those identified for pathwidth: memoisation on sets, a single pass with no restarts on an upper bound, and the closure. The vertex-cover normal form adds a factor that has no analogue in pathwidth: states are determined by S ∩ C.
- **Where it is weak.** kcw has no bound on the cost of the remainder. It must therefore settle every state of bottleneck below cw, and that is what limits it on large grids, on dense graphs and on graphs with large cw. Coudert's C\* grooming bound and degree bounds are strong in exactly that regime: they are his lower bounds on mcca, the str\_\_ family and west0381.
- **What I would try next.** Combine the two. A completion lower bound h(S) satisfying h(S) ≥ any completion's max cut, for example the C\* bound on the remaining graph with the boundary edges as requests, would turn the search into A\*. Only states with max(d, h) ≤ B would be expanded, and every optimality proof would be kept.

## Files

- `src/C/kcw.c` (build: `cc -O3 -march=native -o src/C/kcw src/C/kcw.c`).
- `tests/test_kcw.py`.
- `bench/cutwidth/`:
  - `run_bab.py`: one graph through his BB+ or BB3+;
  - `setup.py`: builds his Cython against passagemath;
  - `run_kcw.sh` and `run_sage.sh`: the batch drivers;
  - `tables.py`.
- `data/cutwidth/`:
  - `coudert_graphs.tgz`: his instance directories;
  - `coudert_results.csv`: his `.res` files, concatenated;
  - `kcw_*.tsv` and `sage300.tsv`: the runs above.

## Appendix: Harwell–Boeing and grid instances not solved by kcw in 30 s

| graph | n | m | tau | kcw lb (30 s) | Coudert lb | Coudert ub |
|---|---|---|---|---|---|---|
| Grid15x15 | 225 | 420 | 112 | 16 | 4 | 16 |
| Grid15x18 | 270 | 507 | 135 | 15 | 4 | 16 |
| Grid18x15 | 270 | 507 | 135 | 15 | 4 | 16 |
| Grid15x21 | 315 | 594 | 157 | 14 | 4 | 16 |
| Grid21x15 | 315 | 594 | 157 | 14 | 4 | 16 |
| Grid18x18 | 324 | 612 | 162 | 14 | 4 | 19 |
| Grid15x24 | 360 | 681 | 180 | 14 | 4 | 16 |
| Grid24x15 | 360 | 681 | 180 | 14 | 4 | 16 |
| Grid18x21 | 378 | 717 | 189 | 14 | 4 | 19 |
| Grid21x18 | 378 | 717 | 189 | 14 | 4 | 19 |
| Grid15x27 | 405 | 768 | 202 | 14 | 4 | 16 |
| Grid27x15 | 405 | 768 | 202 | 14 | 4 | 16 |
| Grid18x24 | 432 | 822 | 216 | 13 | 4 | 19 |
| Grid24x18 | 432 | 822 | 216 | 13 | 4 | 19 |
| Grid21x21 | 441 | 840 | 220 | 14 | 4 | 22 |
| Grid18x27 | 486 | 927 | 243 | 13 | 4 | 19 |
| Grid27x18 | 486 | 927 | 243 | 13 | 4 | 19 |
| Grid21x24 | 504 | 963 | 252 | 13 | 4 | 22 |
| Grid24x21 | 504 | 963 | 252 | 13 | 4 | 22 |
| Grid21x27 | 567 | 1086 | 283 | 13 | 4 | 22 |
| Grid27x21 | 567 | 1086 | 283 | 13 | 4 | 22 |
| Grid24x24 | 576 | 1104 | 288 | 12 | 4 | 25 |
| Grid24x27 | 648 | 1245 | 324 | 12 | 4 | 25 |
| Grid27x24 | 648 | 1245 | 324 | 12 | 4 | 25 |
| Grid27x27 | 729 | 1404 | 364 | 12 | 4 | 28 |
| impcol_b | 59 | 281 | 41 | 48 | 29 | 55 |
| gent113 | 104 | 549 | 64 | 33 | 29 | 88 |
| gre__115 | 115 | 267 | 52 | 26 | 14 | 36 |
| lns__131 | 123 | 275 | 65 | 19 | 12 | 30 |
| bcsstk04 | 132 | 1758 | 116 | 85 | 121 | 310 |
| west0132 | 132 | 404 | 86 | 23 | 21 | 72 |
| impcol_c | 137 | 352 | 85 | 21 | 14 | 47 |
| lund_a | 147 | 1151 | 142 | 58 | 41 | 113 |
| lund_b | 147 | 1147 | 138 | 57 | 41 | 111 |
| bcsstk05 | 153 | 1135 | 131 | 47 | 51 | 115 |
| west0156 | 156 | 371 | 100 | 19 | 22 | 56 |
| can__161 | 161 | 608 | 126 | 30 | 12 | 54 |
| west0167 | 167 | 489 | 105 | 22 | 18 | 55 |
| mcca | 168 | 1662 | 132 | 32 | 355 | 390 |
| fs_183_1 | 183 | 701 | 90 | 52 | 104 | 191 |
| gre__185 | 185 | 650 | 133 | 27 | 9 | 48 |
| will199 | 199 | 660 | 128 | 25 | 75 | 133 |
| impcol_a | 206 | 557 | 128 | 19 | 12 | 50 |
| dwt__209 | 209 | 767 | 155 | 24 | 14 | 57 |
| gre_216a | 216 | 660 | 108 | 24 | 9 | 52 |
| dwt__221 | 221 | 704 | 161 | 23 | 11 | 27 |
| impcol_e | 225 | 1187 | 138 | 23 | 54 | 180 |
| saylr1 | 238 | 445 | 119 | 15 | 4 | 15 |
| steam1 | 240 | 1761 | 240 | 57 | 50 | 182 |
| dwt__245 | 245 | 608 | 158 | 14 | 11 | 29 |
| nnc261 | 261 | 794 | 93 | 34 | 16 | 46 |
| bcspwr04 | 274 | 669 | 156 | 15 | 14 | 31 |
| ash292 | 292 | 958 | 217 | 21 | 12 | 37 |
| can__292 | 292 | 1124 | 194 | 23 | 34 | 102 |
| dwt__310 | 310 | 1069 | 233 | 22 | 9 | 26 |
| gre__343 | 343 | 1092 | 168 | 23 | 11 | 72 |
| dwt__361 | 361 | 1296 | 276 | 22 | 9 | 38 |
| plat362 | 362 | 2712 | 312 | 41 | 34 | 155 |
| plskz362 | 362 | 880 | 244 | 16 | 6 | 30 |
| str__200 | 363 | 3049 | 222 | 25 | 84 | 617 |
| str__600 | 363 | 3244 | 237 | 27 | 93 | 661 |
| str____0 | 363 | 2446 | 204 | 21 | 81 | 432 |
| west0381 | 381 | 2150 | 251 | 28 | 318 | 525 |
| dwt__419 | 419 | 1572 | 328 | 22 | 12 | 55 |
| bcsstk06 | 420 | 3720 | 376 | 34 | 58 | 226 |
| bcsstm07 | 420 | 3416 | 365 | 33 | 50 | 219 |
| impcol_d | 425 | 1267 | 265 | 17 | 15 | 68 |
| hor__131 | 434 | 2138 | 345 | 24 | 66 | 153 |
| bcspwr05 | 443 | 590 | 205 | 7 | 8 | 19 |
| can__445 | 445 | 1682 | 341 | 22 | 24 | 123 |
| pores_3 | 456 | 1769 | 436 | 19 | 11 | 29 |
| bcsstk20 | 467 | 1295 | 416 | 14 | 11 | 21 |
| nos5 | 468 | 2352 | 346 | 28 | 39 | 196 |
| west0479 | 479 | 1889 | 311 | 19 | 38 | 309 |
| mbeacxc | 487 | 41686 | 381 | 248 | 6214 | 16552 |
| 494_bus | 494 | 586 | 225 | 5 | 6 | 16 |
| west0497 | 497 | 1715 | 303 | 29 | 49 | 211 |
| dwt__503 | 503 | 2762 | 387 | 23 | 30 | 135 |
| lns__511 | 503 | 1425 | 294 | 10 | 12 | 72 |
| gre__512 | 512 | 1680 | 256 | 20 | 12 | 94 |
| fs_541_1 | 541 | 2466 | 388 | 270 | 270 | 299 |
| sherman4 | 546 | 1341 | 273 | 15 | 6 | 36 |
| dwt__592 | 592 | 2256 | 457 | 21 | 14 | 70 |
| steam2 | 600 | 6580 | 600 | 78 | 67 | 308 |
| west0655 | 655 | 2841 | 424 | 19 | 51 | 479 |
| 662_bus | 662 | 906 | 323 | 7 | 7 | 26 |
| shl__200 | 663 | 1720 | 393 | 220 | 220 | 409 |
| shl__400 | 663 | 1709 | 399 | 213 | 213 | 403 |
| shl____0 | 663 | 1682 | 395 | 211 | 211 | 383 |
| nnc666 | 666 | 2148 | 236 | 24 | 16 | 80 |
| nos6 | 675 | 1290 | 337 | 12 | 4 | 29 |
| saylr3 | 681 | 1373 | 337 | 11 | 7 | 48 |
| 685_bus | 685 | 1282 | 389 | 9 | 11 | 33 |

