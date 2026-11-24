The Problem
===========

A number of parallel processes are emitting streams of pairs $(k,v)$,
where $k$ is a key and $v$ is a value. The object is to **reduce**
these pairs in the following way:

There is an associative binary operator, which we'll write as $\star$
applying to values (in the original $\star=+$. We want to process the
streams so that the we have only pairs $(k,w)$, with only one pair per
values of $k$, and $w = v_1 \star \cdots v_r$, where the $v_i$ are all
the values of $v$ associated with $k$.

Since the number of pairs is very large, we must pay attention to the
effects of the storage hierarchy.

The first attempt just used open addressing hashing applying a hash
function $H$ to $k$. This worked poorly for two reasons: (1) in order
for open addressing to be efficient the table needed a large
percentage of emtpy slots. (2) Even worse, the random access worked
very poorly with storage hierarchy: too many cache misses and page
faults.

The second attempt used **extendible hashing** (Niegervelt
et. al.). This ameliorated point (1), in that the table could expand
to fit the demands. This did have to be supplemented by a pre-buffer:
instead of directly processing the hashed value in a page, a number of
values destined for the page were collected in a small buffer, and
only processed when the buffer was full. This greatly improved the
performance given the storage hierarchy

The third attempt accumulated items within a page (as with extendible
hashing using the high order bits of $H(k)$. When the page was full it
was sorted. After accumulating a number of sorted pages, they were
then merged (possibly with a tree structure). The sizes of the pages
and buffers needed to be tuned to the concrete sizes of the various
caches and page sizes.

Does this same problem affect the vertex separation and cutwidth,
etc. calculations? If so, can we be attentive to it?

Answer
======
Before answering I want two measurements: how much of the run time actually goes to the state table, and how much a reordering of the search would cost. Both decide which of your three remedies applies here.

Yes, the same problem is present: the table of visited states in every program (kpw, kpw2, kcw and the generated code) is your first attempt, an open-addressing hash on H(k). How much it hurts depends on the problem, and one difference from your setting changes which remedy fits. I measured before answering; the analysis and a plan are in `doc/memory_hierarchy.md` (attached). Nothing is implemented yet.

**Why it's the same reduction.** Each move offers a pair (key, value), where the key is the state (S, or S ∩ C for kcw), and the table reduces with an associative ⋆:

| output mode | ⋆ |
|---|---|
| width plus one ordering | keep the first (parent, label) |
| complete DAG | union of in-arcs |
| secondary costs | Pareto merge |
| k-best | top-k merge |

**How much it costs today.**

| table | lookup |
|---|---|
| fits in cache | 14–30 ns |
| 1–2 GB | 50–130 ns |

- **Vertex separation:** moves are cheap and runs make about 10 probes per state, so the table is roughly 30% of the time at 3M states, and the share grows with state count.
- **Cutwidth:** each move costs about 1 µs, so it is compute-bound and the table is only 2–10%.
- **Empty slots (your point 1):** minor here, since slots are 4-byte ids beside 8W-byte keys. The real costs are the random probes and the global rehash on doubling, which touches every key in random order.

**What's different from your setting.**
- **The search can't defer its answers for free.** Depth-first search must know at once whether a child is new before deciding to expand it, which a stream reduction never needs. Within one level the order of expansion doesn't matter, and the Lean theorem `closed_eq_reach` proves that. But reordering loses the early stop on the final level, and measured with kpw `-c`, exploring the whole final level costs 2.3–3.1× more states. So a fully deferred scheme is a loss for the width alone, and costs nothing extra in the complete-DAG, Pareto and k-best modes, which must exhaust the final level anyway.
- **The key space has structure your problem lacks.** Every move adds a vertex, so arcs only go from |S| = k to larger sizes. Partitioning the table by |S| therefore gives exact duplicate-detection scope: when layer k comes up, nothing more can arrive for it. Its buffered candidates can be sorted, deduplicated once and merged. That is your third attempt with |S| in place of the high bits of H(k), and Korf's delayed duplicate detection from disk-based search.

**Proposed plan, two tiers:**
1. **Keep depth-first search and fix the table.** This changes no widths, orderings or state counts. The expected gain is 10–25% on large vertex-separation runs and a few percent on cutwidth; that is an estimate still to be measured.
   - Put a 32-bit fingerprint in each slot, so a wrong slot rarely forces a read of the key array. This measured 1.4–1.8× faster lookups at 4·10⁷ states.
   - Batch and prefetch the probes for all children of one state, the per-expansion version of your pre-buffer. Measured alone this gained only about 10%.
   - Split the table by high hash bits, extendible-hashing style, so each part grows on its own with no global rehash. This also gives per-part locks for the threaded kpw2.
2. **An alternative engine with layered delayed duplicate detection.** It uses only sequential buffers, sorted runs and merges, with no empty slots. Runs can spill to disk, layers can be split lock-free across threads, and parents are recovered by scanning, as in kpw2 `-x`. It's the right engine for state counts beyond RAM, the exhaustive output modes and many-core runs. A hybrid is natural: depth-first until a memory budget is hit, then layered.

**How it fits the DSL.** Both tiers are data-layer annotations, e.g. `table hash(fingerprint=32, partitions=2^b, prefetch=batch)` or `table layered-ddd(run=…, buffer=…)`, with the sizes as parameters to tune per machine, which is your third attempt's lesson. Your Apple-silicon iMac uses 16 KB base pages and malloc gets no transparent huge pages, so its tuning will differ from this container, where huge pages are already on. Correctness carries over: the Lean engine theorems are stated about a closed table, not about the order of expansion. The layered engine adds only one obligation: a sweep in layer order leaves the table closed, which follows from arcs only going up in |S|.

Should I implement the first tier now (engine, kpw, kcw) and prototype
the layered engine for the complete-DAG mode?

Question
========
Implement the first tier. I came across this problem in my other repo
which counts the exact number of Hamiltonian paths in an undirected
graph. It uses the Held-Karp dynamic programming, along with a
precalculation of pathwidth. I think that you've seen that because you
pointed out that the simulated annealing calculation I used there
could be replaced by an optimization over the DAG produced by the
pathwidth computation. That repo had code that was parametrized by the
empirical values of the cache sizes (and speeds) and the pagewidth. As
you point out, it might be much more significant in that case.


