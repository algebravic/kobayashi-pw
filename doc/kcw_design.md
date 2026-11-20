# kcw: exact cutwidth in C (design, written before implementation)

## Goal

`src/C/kcw.c` ports the cutwidth plug-in of `src/kobayashi_pw/widths.py` to C so that it can be compared with Coudert's branch-and-bound codes (BB1, BB2, BBPR, BB+, BB3+, and Sage's 2ⁿ DP "DYN") on the instances of his `cutwidth` repository:
- CMPLIB 2010: "small", "grids" and Harwell–Boeing;
- GPW2024: ER and geometric.

## Algorithm

The algorithm is the one-pass bucketed bottleneck search over prefix sets S, the same search as kpw. Write f(S) = |E(S, V∖S)| and rank(S, v) = deg v − 2|N(v) ∩ S| = f(S+v) − f(S).

1. **Closure.** Repeatedly add every vertex with rank ≤ 0. This is safe by the submodular greedy lemma (`doc/other_widths.md` §2). No step of the closure raises the cut, so it adds nothing to the cost of the arc.
2. **Cover restriction**, which can be turned off with `-C`:
   - Only vertices of a vertex cover C are chosen voluntarily.
   - Before placing x ∈ C, place i of the vertices in Y(S, x), where Y(S, x) is the set of odd-degree vertices outside C that are adjacent to x and have rank 1 at S.
   - The arc cost is f(S) + max(i, Δ − i), with Δ = rank(S, x) and i = min(|Y|, ⌊Δ/2⌋), clamped to be ≥ 0.
   - This is Cygan et al.'s normal form, as in the prototype.
   - A state is then determined by S ∩ C, because S ∖ C = {u ∉ C : rank(S ∩ C, u) ≤ 0}. So the hash key is the τ-bit set S ∩ C, and S is decoded on expansion in O(m).
3. **Search.**
   - The level B starts at max_v ⌈deg v / 2⌉, which is a valid lower bound.
   - A DFS stack expands every state reachable with bottleneck ≤ B. Each expanded state records the smallest arc cost above B that it skipped, and goes into that bucket.
   - When the stack is empty, B becomes the smallest non-empty bucket, and the states in that bucket are rescanned.
   - The search stops when V is inserted; B is then the cutwidth.
   - While level B is being processed, cw ≥ B is proved. So a run stopped by a time or state limit still reports a certified lower bound, `lb=B`.
4. **Parent pointers.** Each state stores (parent, x, i). The ordering is rebuilt by replaying Y[:i], x and the closure, which is deterministic. The program prints the ordering, recomputes its width, and checks it against B.

## Data structures

- Adjacency lists. Weights are allowed, but only simple graphs are needed: the benchmark files have no parallel edges or loops, which was checked. With multiplicities the Y rule would need re-deriving, so `kcw` refuses the cover restriction on a multigraph.
- State arrays: key words, parent (uint32), x (int32), i (int32).
- An open-addressing hash table of uint32 ids, rehashed at load factor 1/2.
- Buckets: growable id arrays indexed by cost.
- On expansion, an array a[u] = weight of the edges from u into S. A child is evaluated by applying the additions in place with an undo log, so it costs O(Σ degrees of the added vertices) and not O(n).
- **Vertex cover.**
  - Bipartite graphs: an exact cover by König's theorem, from a maximum matching (augmenting paths).
  - Other graphs: greedy by maximum degree, then redundant vertices removed.
  - Any vertex cover is correct; a smaller one gives fewer states.
- **Connected components** are solved separately. The width is the maximum over components, and the orderings are concatenated.

## Options

| option | meaning |
|---|---|
| `-C` | no cover restriction (every vertex may be chosen) |
| `-T sec` | time limit |
| `-M states` | state limit |
| `-q` | do not print the ordering |
| `-v` | progress at each level B |

## Output

`n=.. m=.. tau=.. cw=.. states=.. expansions=.. time=..`, or, when a limit is hit, `cw=? lb=B`. Then `order: names` follows.

## Tests

- Agreement with `brute_cutwidth` (2ⁿ DP) on random graphs and bipartite graphs, with n ≤ 12, with and without `-C`.
- Agreement with the Python prototype on the square-sum graphs.
