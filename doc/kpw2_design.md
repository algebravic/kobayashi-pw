# kpw2: design of the four extensions

`src/C/kpw2.c` is a separate program. `kpw.c` stays as the simple 64-bit reference. kpw2 accepts the same input and flags as kpw, plus `-x` and `-t`.

## 1. More than 64 vertices

- A vertex set is a fixed array of `W` 64-bit words, so n ≤ 64·W. `W` is a compile-time constant: `-DW=2` (the default) gives n ≤ 128, and `-DW=1` gives a 64-bit build that can be checked against kpw.
- All set operations work word by word: or, and, and-not, popcount, iteration by count-trailing-zeros.
- Hash-table slots carry an explicit `used` byte, so no key value is reserved. (kpw used S+1 and had to keep V out of the table.)
- DAG dump: originally format 2 (`KPWDAG2`); now format 3 (`KPWDAG3`), which adds the vertex names. Both are defined in `doc/dag_format.md`.

## 2. Expansion restricted to adjacent vertices

- A vertex x ∉ U is subsumed iff N⁻(x) ⊆ C, where C = U ∪ N(U).
- If x was not subsumed before C grew by Δ, it can only become subsumed when N⁻(x) ∩ Δ ≠ ∅, that is, when x is an out-neighbour of Δ.
- So the rule-1 closure runs as a worklist. It starts from candidates = N⁺(Δ₀), and each added vertex y contributes N⁺(Δ_y), where Δ_y = ({y} ∪ N⁻(y)) \ C.
- Δ₀ depends on where the expansion starts:
  - for T = S ∪ {x} with S already rule-1 closed (every table set is), Δ₀ = ({x} ∪ N⁻(x)) \ C(S);
  - for ∅\*, every vertex is a candidate.
- **The result is the same set.** Rule-1 closure is the least fixpoint of a monotone operator, so it does not depend on the order. The second greedy rule (`-g`) still takes the lowest-numbered qualifying boundary vertex after each rule-1 fixpoint, exactly as kpw does. So kpw2 and kpw produce identical sets and identical counts of sets, pairs and rescans. Only the order inside a block can differ, and every order the worklist produces is valid: each vertex is subsumed when it is added.
- **Cost:** O(Σ deg) word operations per expansion, instead of O(n · sweeps).

## 3. `-x`: store only the arc label, recover the predecessor by search

- A slot then holds (key, x, |P|) instead of (key, P, x). With W = 2 that is 24 bytes against 40, so the table is 40% smaller.
- **Recovery, during extraction only.** For each extraction step, scan the table once for a stored set P with:
  - |P| equal to the stored size;
  - P ⊆ T \ {x};
  - |N(P ∪ {x})| ≤ pw;
  - expansion(P ∪ {x}) = T.
- **Correctness.** Any such P is a stored set of bottleneck ≤ pw with an arc of cost ≤ pw into T, so the chain it gives is a valid optimal path. The recorded parent qualifies, so the scan always succeeds.
- **Cost.** At most n table passes. That is 0.1 s or less on the graphs tested; most candidates are rejected by the size and subset tests. The program reports how many candidates passed those tests.
- **What was tried first.** The original plan was to undo the expansion by "peeling" vertices. It branches over every interior vertex and blew up (more than 80 s and running out of memory on G₆₁), so it was replaced.

## 4. `-t N`: parallel levels (pthreads; no OpenMP, so Apple clang works)

- **Correctness.** Within a level, the order in which pairs are processed does not matter (Theorem 13). Threads therefore share a level and synchronise only at level boundaries.
- **Hash table.** 256 shards, each an open-addressing table with its own spin lock, chosen by the high bits of the hash. The lock spins 64 times, then yields. Locks are taken only when N > 1.
- **The stack holds one item per set:** (S, ν(S), mask of the arc labels still to try), not one entry per (set, label). Popping takes the highest label in the top item and leaves the rest on top. This is exactly kpw's LIFO order, so `-t 1` counts match kpw, and the stack is several times smaller. At pw on g2 the final rescan used to push 8 M pairs; it now pushes 0.7 M items.
- **A level** works as follows:
  1. The bucket entries for the level are rescanned in parallel; the items go to the threads' own stacks.
  2. Each thread then drains its own stack depth first. When the stack is empty, the thread steals the oldest half of another thread's stack.
  3. An atomic count of pending pairs detects the end of the level. A thread that fails to steal yields.
- **Termination.** Finding V sets an atomic flag. Without `-c`, threads stop at once. With `-c`, the level is completed.
- **Pruning (`-c`).** The stored sets are grouped by size and processed from the largest down, in parallel within each size, because a set's arcs lead only to larger sets.
- **`-t 1`** (the default) runs kpw's exact sequential loop.
- **With N > 1,** pw and the complete DAG are deterministic. The number of sets discovered at level pw before V is found, and the ordering printed, can vary from run to run.

## Verification plan

1. **`-t 1` against kpw.** For W = 1 and W = 2, on random graphs and digraphs with n ≤ 64 and on G₅₇–G₆₃: identical pw, sets, pairs, rescans and `dag=`, in all four combinations of `-g` and `-c`.
2. **n > 64.** pw must equal the Python implementation (arbitrary-precision ints, already checked against brute force) on random graphs with 65 ≤ n ≤ 100, and on G₆₅–G₇₅ where Python finishes. Every run's printed ordering is re-checked inside the program.
3. **`-x`.** Same pw. The extracted ordering is re-verified.
4. **`-t 4`.** Same pw, the same `dag=`, and a verified ordering. Speedup is measured on the 4-core VM.
5. **Python.** `OrderDAG.load` of a kpw2 dump equals `OrderDAG.build`, including for n > 64.

## Results

**Tests.** All 19 tests pass, including `tests/test_kpw2.py`, which compiles W = 1 and W = 2 and checks:
- brute force and exact count parity with kpw;
- grids 8×9, 7×11, 9×10 (pw = min side);
- n > 64 against the Python implementation, with identical set counts;
- DAG-file loading equal to the Python DAG.

**Separately:**
- 9000 small runs.
- Grids up to 11×11, with n = 121 and pw = 11.
- G₆₅, G₆₇ and G₇₅ against Python: pw 14, 14 and 15, with identical set counts.

**Timing on this machine (Xeon 2.1 GHz, one thread):**

| graph | kpw | kpw2, W = 1 | kpw2, W = 2 | kpw2, W = 2, `-x` |
|---|---|---|---|---|
| g2 (n = 60) | 0.9 s, 288 MB | 0.9–1.1 s, 111 MB | 1.4 s, 204 MB | 1.3–1.4 s, 175 MB |
| G₆₁ | 0.6–0.7 s, 271 MB | 0.6 s, 104 MB | 0.8–0.9 s, 192 MB | 0.9–1.0 s, 163 MB |
| G₆₃ | 0.4 s, 201 MB | 0.3 s, 57 MB | 0.5 s, 104 MB | 0.5 s, 77 MB |
| G₇₅ | — | — | 0.7 s, 114 MB | 0.8 s, 93 MB |

The restricted sweep and the item stack together make the 64-bit build about as fast as kpw with a third of its memory. Full sweeps took 14–18% of kpw's time, so that is the most the restricted sweep alone can save.

**Threads (4-core aarch64 VM, three runs each, wall time in seconds):**

| graph | `-t 1` | `-t 2` | `-t 4` |
|---|---|---|---|
| G₆₃ | 1.10–1.13 | 0.60–0.72 | 0.39–0.57 |
| G₆₁ | 1.43–1.74 | 1.03–1.12 | 0.60–0.78 |
| g2 | 2.02–2.32 | 1.81–2.34 | 1.36–1.45 |

That is about 2–2.5× on four threads. The search is dominated by hash-table cache misses, so the scaling is sub-linear.

**Square-sum graphs, `kpw2 -g`, one thread:**

| graph | G₆₅ | G₆₇ | G₆₉ | G₇₁ | G₇₃ | G₇₅ |
|---|---|---|---|---|---|---|
| pw | 14 | 14 | 14 | 14 | 14 | 15 |
| time | 0.5 s | 0.3 s | 0.3 s | 0.4 s | 0.3 s | 0.6 s |

Complete mode (`-c`) takes 1.6–3.6 s on these graphs. For G₇₅ the DAG has 132,400 nodes and about 5.5 × 10³⁸ orderings; the V7 optimum takes 24 s to load and 34 s to compute in Python, and agrees with `_dp_cost`.
