Question
--------
I'm interested in algorithms for the optimal vertex separation of an
undirected graph. There are two classes of such algorithms. The first
class are described in a paper by David Coudert. The particular
algorithm that I've used is one described in the comments of
vertex_separation.py. It's in
[program for linear ordering](http://www-sop.inria.fr/members/David.Coudert/code/LinearOrdering.zip)
Referred to by the page
[linear ordering](https://www-sop.inria.fr/members/David.Coudert/code/graph-linear-ordering.shtml)

Given by the link to 

This is described as a MIP, but I've rewritten it as a MaxSat, which
proved to be much more efficient (on some graphs it's over 100 times
faster than the MIP using Gurobi).

There's an alternate method due to Kobayashi in the attached
paper. I've implemented his algorithm 1 in Python. Right now I'm more
interested in it being correct than as fast as possible. For the
latter, it should be rewritten in C or Rust. However, there are a
number of important details in its use that I'd like to clear up:

1) The algorithm given there just determines whether or not the
pathwidth of the graph is \(\le k\) for some \(k\). I realize that one
can then use binary search to determine the correct value of the
pathwidth. However, I believe that one can be much more
efficient. There's a practical problem that the looser \(k\) is
(i.e. above the actual pathwidth) the more work the algorithm does,
since it prunes many fewer sets. So, the first question is: can the
structure of \(R_i\) tell us anything about where the true value might
lie?

2) Once we've determined the true value of the pathwidth how do we
extract an actual ordering that gives that pathwidth? I can imagine
that when we add a new set to \(R_j\) that we can include a pointer
back to the set that it was derived from. By chasing these pointers we
should then get a valid order. Does that sound correct?

Answer
------
I'll read Kobayashi's paper first, then answer both questions.

Both of your ideas work, and Q1 has a better answer than binary search. I checked the claims below by implementing them and comparing against brute-force vertex separation on 3000 random undirected graphs with n ≤ 10. That is an empirical check; the arguments themselves are short. I write N(·) for N⁻(·) (undirected case), and w(U,v) = |N(U∪{v})| for the width of the step at line 7.

**A small erratum first.** Line 2 of Algorithm 1 should read R_i ← ∅, the empty collection. Read literally, R_i ← {∅} makes R_n nonempty every time. You've presumably handled this already.

## The key fact

Expansion never increases the boundary. Suppose x is subsumed by U, so N(x) ⊆ U ∪ N(U). Then N(U∪{x}) ⊆ N(U). This is the first line of the proof of Lemma 1, and it doesn't depend on k. So every step U → (U∪{v})* in Algorithm 1 has one well-defined cost, w(U,v). The vertices added by the expansion only make prefixes whose boundaries are subsets of N(U∪{v}).

## Q1: Finding the true value

**(a) Pick the next k after a failure.** Suppose a run with bound k fails. Let k′ be the smallest w(U,v) among the candidates rejected at line 7. Any bound in [k, k′) produces exactly the same family R, so it also fails. Therefore pw ≥ k′, and k′ is the only next value worth trying. Also, the family at k is a subset of the family at k′. You can resume the old run rather than restart it, provided you kept the rejected candidates.

**(b) Do it in one pass.** Carry that idea all the way and k disappears: you get a bottleneck (min–max) shortest-path search over relevant sets. Keep one bucket of pending pairs (U, v) for each width 0..n. Work at the current level c:

- Pop a pair, compute S = (U∪{v})*, and skip it if S has been seen before.
- For each x ∉ S, push (S, x) into the current level if w(S,x) ≤ c, otherwise into bucket w(S,x).
- When the current level is exhausted, move to the next nonempty bucket.

This is correct for the same reason Dijkstra's algorithm is: max is a monotone path cost. A set first reached at level c has optimal bottleneck exactly c, because all lower levels were exhausted first. The first time S = V is reached, c = pw. By Lemma 2 at k = pw, V is reachable at that level.

The work is at most that of a single run with k = pw. Every set that gets expanded has bottleneck ≤ pw, and pairs with width > pw are pushed but never expanded. So the overshoot cost you described never happens, and you need no lower bound to start from. The pending pairs at levels above pw are the frontier, and you can throw them away at the end. It works unchanged for digraphs with N⁻.

**(c) If you already ran with a loose k.** Algorithm 1 processes sets in order of size, and every parent is strictly smaller than its child. So you can compute f(S) = min over discovered parents of max(f(U), w(U,v)) during that same run. Then f(V) = pw exactly, because that run's R contains everything reachable at level pw. Run (b) is just the cheaper way to get the same number.

## Q2: Extracting an ordering

Pointer chasing is correct, with two details to get right.

1. **Which parent.** Any discovered parent gives a valid ordering, since Lemma 1 makes every element of R k-feasible. With the bucket version, the parent recorded when S is first reached is automatically optimal. With a loose-k run, keep the parent that achieves the minimum in f.
2. **Order of the expansion vertices.** The vertices of (U∪{v})* \ (U∪{v}) must be emitted in the order the expansion procedure added them, not in an arbitrary order. A vertex can be subsumed only after earlier expansion vertices have been added. Here is an example. Take U = {a}, with a adjacent to b and x, and w₁, w₂, w₃ each adjacent to both b and x. Each wᵢ is subsumed by U, but x is subsumed only after the wᵢ are in. Putting x first gives |N({a,x})| = |{b,w₁,w₂,w₃}| = 4, whereas |N(U)| = 2.

   The simplest fix is to expand one vertex at a time, each subsumed by the current set, and record that order. You can store it with the pointer, or recompute it at extraction time, since the procedure is deterministic.

The ordering is then: σ(parent) + v + (the recorded expansion order). The base case is ∅*. Its vertices have N(x) = ∅, so they contribute width 0. Every prefix width is either a checked w(U,v) or bounded by one, by the key fact above. As a sanity check, recompute the width of the final ordering; it's one linear pass. In my tests the extracted ordering always had width exactly pw and contained every vertex.

The test script includes a straightforward Python version of (b) with
pointer extraction, about 40 lines. It is cleanly separated from the
brute-force check and could drop into your implementation as a
reference. I can write it up as a markdown file in your
documentation-first format if that's useful.

Question
--------
Can you give me a Python program that implements what you've outlined?  How much of a speedup would a careful implementation in C, C++ or Rust give over Python (a rough estimate)?

Answer
------
I've written the Python program as a uv project, with tests and a short C port. To answer the speedup question I measured it rather than guessing: the C version runs about 60× faster than the Python and uses about a third of the memory.

**What's in the program** (`src/kobayashi_pw/`):
- **Main search:** `pathwidth(g, upper=None)` runs the bucketed bottleneck search, so you don't supply k. It returns the pathwidth and an optimal ordering. With `upper=k` it becomes a decision test and stops as soon as it knows pw > k.
- **The paper's version:** `decide(g, k)` is Algorithm 1 exactly as written, kept for cross-checking.
- **Graph representation:** graphs are stored as in-neighbour bitmasks, so directed graphs work unchanged. You can read edge lists, graph6 or digraph6.
- **Command line:** `kobayashi-pw`. It recomputes the width of every ordering it prints, independently of the search.
- **One change from my sketch:** it stores each discovered set once, at its next larger step width, rather than storing every rejected (set, vertex) pair. It rescans the set when the search reaches that width. This saves a lot of memory; the README explains it.

**Checks (empirical, not proofs):**
- Exact agreement with a brute-force subset computation on 3000 random graphs and digraphs with n ≤ 10.
- The extracted orderings achieve exactly the pathwidth.
- Decision mode and Algorithm 1 both give the right answers at pw and pw − 1.
- Known values: paths, cycles, K₇, stars, the 3×3 grid, acyclic digraphs (pathwidth 0) and the Petersen graph (5).
- The C port reports exactly the same counts of sets, pairs and rescans as the Python on the timing graphs, which is a good sign the two implement the same algorithm.

**Speedup:** I timed three random graphs. The C port is a direct translation (one 64-bit word per set, so n ≤ 64, plus an open-addressing hash table); it isn't tuned.

| graph | n | pw | relevant sets | Python | C | ratio |
|---|---|---|---|---|---|---|
| g1 | 40 | 11 | 4 022 | 0.22 s | 0.009 s | ~24× (C time is mostly startup) |
| g3 | 45 | 15 | 19 608 | 1.45 s | 0.026 s | ~56× |
| g2 | 60 | 11 | 732 821 | 66–70 s | 1.13 s | ~60× |

On g2, peak memory was 854 MB for Python and 288 MB for C.

So a rough estimate is 50–100× in speed and 3–5× in memory. Memory will probably be the real limit on harder graphs, since the number of relevant sets grows roughly like 3^τ, where τ is the size of a minimum vertex cover. More speed would come from:
- packing each stored entry tighter;
- running the expansion only over vertices adjacent to the newly added vertex, instead of rescanning all of them;
- multi-word sets once n > 64, which will cost something per operation;
- running in parallel within a level.

Rust would perform about the same as C.

**The cost of a loose k:** the paper's Algorithm 1 goes from 0.62 s at k = pw to 4.7 s at pw+2 and 28.6 s at pw+4 on g1. The bucketed search takes 0.22 s, faster even than Algorithm 1 at the exact k, because it stops as soon as it reaches the full vertex set at level pw. Nearly all of its sets are discovered below that level.

Files are in kobayashi-pw.zip:
- README.md
- pyproject.toml
- src/kobayashi_pw/core.py
- src/kobayashi_pw/io.py
- src/kobayashi_pw/cli.py
- src/C/kpw.c
- tests/test_core.py
- data/g1.txt, data/g2.txt, data/g3.txt

Question
--------
Write a latex paper which describes the algorithm (with appropriate
references to kobayashi) and details the improvements that you've made
(i.e. the one-pass construction and the explicit determination of a
vertex order giving minimum pathwidth). Have a separate section
discussing the data structures used.  On some of my test graphs, the C
implementation is hundreds of times faster than the MaxSat
implemenation, which, in turn was 100s of times faster than the
corresponding MIP implementation using Gurboi.

This was one of my test files. The C program kpw took 0.965 seconds
and the python program 73.6 seconds on my computer.

Answer
------
C now handles n = 64 correctly, and the Python and C versions report identical counts on sq63. Next I'll update the paper.

I've written the paper as LaTeX source with a compiled 10-page PDF. Your sq63 file also exposed a bug in the earlier C program, now fixed.

**The bug.** Because sq63's labels go up to 63, the C program treats it as having 64 vertices. When all 64 bits are in use, the hash table's key for the full vertex set wraps around to the value that means "empty slot". The C program now stores the full set's parent link separately, outside the table; finding the full set ends the search anyway. It handles 64 vertices correctly, including edgeless, path and cycle graphs with 64 vertices.

The pathwidth it printed for you was unaffected. But tracing back the ordering looked up exactly the broken entry, so the old version could have printed a "VERIFY FAILED" line or a wrong order. If you still have that output, it's worth checking. The fixed version agrees with the Python on sq63: pathwidth 14, 364,589 relevant sets, with the same counts of steps and rescans. Here the times were 0.43 s for C and 25.6 s for Python; your 0.965 s and 73.6 s give a ratio of about 76, consistent with the others.

**What's in the paper:**
- **Kobayashi's algorithm** is restated, with a note on the misprint in line 2 of his pseudocode.
- **The step cost doesn't depend on k.** Adding a vertex during expansion never enlarges the boundary. So pathwidth is the cheapest worst-step path to the full vertex set in a DAG of relevant sets, with an ordering of exactly that width read off any such path.
- **Two shortcuts if you keep the decision procedure:** after a "no" answer, the smallest rejected step width is the next k worth trying, and a single run with any k above the pathwidth already contains enough to recover the exact value.
- **The one-pass search** comes with proofs of correctness and of the optimal ordering. Its work lies between Kobayashi's Algorithm 1 at k = pw−1 and at k = pw, so it keeps his 3^τ·poly(n) bound.
- **The ordering example** shows why vertices added during one expansion step must be output in the order they become absorbed.
- **A separate section on data structures:** bitmasks with each set's union of neighbours carried along, one-at-a-time expansion, the hash table with parent pointers, the per-level buckets that hold each set once, the shortcut lookup before expanding, and memory per set.
- **Experiments:** your sq63 run (described as the square-sum graph on {1,…,63}, 135 edges) is in the timing table, with your own times in the caption. A second table checks the "between" claim on two graphs. A third shows how the cost grows when k is too large.

**Things you need to fill in or check:**
- I've stated your MaxSAT and Gurobi results only as you described them, "hundreds of times" at each stage. Table 4 is an empty placeholder for your actual numbers, solver versions and hardware; I didn't invent any figures.
- The author line is "Victor Miller, IDA Center for Communications Research"; adjust as needed.
- I didn't describe your MaxSAT formulation beyond saying it rewrites Coudert's model. You may want a paragraph on it.
- The reference details for Coudert's report, Mallach's paper and Pollack's 1960 paper are from memory or a quick search; check them before submitting.

Files are in kobayashi-pw.zip:
- pathwidth.tex
- pathwidth.pdf
- src/C/kpw.c
- data/sq63.txt

Question
--------
Can you look at the repo at ~/Programming/Combinatorics/separation on
my computer? The program in src/separation/vertex_separation.py gives
my MaxSat implemention of Coudert's MIP.

Answer
------
I'll ask for access to that folder, then read the MaxSAT implementation.

I've read the MaxSAT model, your Kobayashi implementation, and the README. Next I'll check the encoding by running it, here in my workspace, on graphs whose pathwidth I already know.

While those timings run, I'll add a section to the paper describing your MaxSAT model precisely, including the reversal argument that ties its convention to Kobayashi's.

Your MaxSAT model is correct. On my test graphs, kpw is roughly 300–1500× faster than it. I've added a section on the model to the paper and put the timings in the comparison table. I didn't change anything in your repo; I ran copies here.

**How the model differs from Coudert's MIP.** Your clauses count the vertices *inside* the prefix that have a neighbour outside it. That is Kinnersley's convention. Coudert's MIP and Kobayashi count the vertices *outside* the prefix instead. Reversing the order turns one count into the other, so:
- the optimal value is the true vertex separation number in either convention;
- the ordering `pathwidth_order` returns is optimal when read **backwards**, in Kobayashi's convention.

The new section 6 in the paper states the model, proves this, and cites RC2 and PySAT. I also checked it on 400 random graphs and digraphs: the values and the reversed orderings agreed every time.

**Timings, MaxSAT vs kpw (same machine, one core):**

| graph | n | pw | MaxSAT | kpw (C) | ratio |
|---|---|---|---|---|---|
| g1 | 40 | 11 | 11.9 s | 0.008 s | ~1500× |
| g3 | 45 | 15 | 15.4 s | 0.019 s | ~800× |
| g2 | 60 | 11 | 305 s | 1.04 s | ~290× |
| sq63 | 63 | 14 | 198 s | 0.43 s | ~460× |

These are now in Table 4. Its Gurobi column is marked [tbd] for your numbers.

**Problems I found in the repo** (details in separation_review.md):
- **Digraphs never take the `predecessors` branch.** `nx.DiGraph` is a subclass of `nx.Graph`, so `isinstance(gph, nx.Graph)` is True for digraphs too. The code silently uses successors, in `vertex_separation.py` and in `separation`/`alt_separation`. The value is still right, because pathwidth doesn't change when every arc is reversed. But the comments describe neighbours inconsistently with what actually runs. Use `gph.is_directed()` instead.
- **The README describes bandwidth, not vertex separation.** It defines width as max |f(v)−f(w)| and puts a sum over time for each vertex. The code sums over vertices at each time, which is the vertex separation model. The README looks left over from an earlier bandwidth model.
- **`trace > 0` and `verbose > 0` crash.** They call `self._cnf.clauses`, which `WCNF` doesn't have (it has `.hard` and `.soft`); `verbose` only crashes when `bound` is also set. The `verbose` print is also missing its `f` prefix.
- **The `bound` clause is added n times**, once per time step. That's harmless, but `bound ≥ n` raises `KeyError`.
- **`kobayashi.py` gives correct answers but slows down
  quadratically.** `rset[l] = rset[l].union([...])` copies the whole
  collection on every insertion. Use mutable sets and `.add`.
  
Question
--------
I was using vertex_separation.py in the repo
~/Programming/Combinatorics/hamiltonian which was concerned with
counting the exact number of hamiltonian paths in families of
undirected graphs using dynamic programming. You can look in the paper
doc/hampath_paper_full.tex which describes the problem. Originally I
only used one path ordering from vertex_separation.py, but later I
found that considering a number of different orderings with a finer
optimization cost could significantly improve the dynamic program. I'm
guessing that the final table produced by kpw can be used to produce
many different orders. Is that correct?


Answer
------
Your sq63 timings (2636.5 s for MaxSAT, 0.893 s for kpw, about 2950×) are worth adding to the paper alongside mine. I'll put them in.

Yes, kpw's table can produce a huge number of pathwidth-optimal orderings, but only after three changes. The bigger win is that your cost functions allow the best ordering to be found exactly from that table, rather than by simulated annealing.

**What has to change:**
- **Finish the search.** kpw currently stops as soon as it reaches the full vertex set. To capture every optimal ordering it must finish that last level, then drop the sets that can no longer reach the full set. The result is small. At n = 57 it is 13,762 sets carrying about 10²⁶ distinct optimal orderings; at n = 61 it is 264k sets and about 10³³ orderings. Building this took 7 s and 155 s in Python and would take well under a second in C.
- **Reverse the order.** kpw counts boundary vertices outside the prefix; your frontier DP counts prefix vertices that still have a later neighbour. So each kpw ordering must be read backwards. Your MaxSAT orderings are already in your convention.
- **Accept a subfamily.** In your DP's direction, the table only contains orderings that pass through prefixes where every introduced vertex already has an eliminated neighbour. I minimized your V2 cost exactly over this subfamily and over all optimal orderings, for n = 25, 30 and 35. The subfamily's best was within 0.3–1.7% of the true best. That is an empirical result on small graphs only.

**Exact optimization.** Every quantity your cost functions use depends only on the prefix before a step and the vertex added at that step. That covers frontier size, back-edges, edges inside the frontier, components, eliminations and step index. So:
- **V1, V2 and the linear model** add up step by step. They can be minimized exactly by a shortest-path computation over the table.
- **V5–V7** compound through the proxy multiplier. They can still be minimized exactly, by keeping at each prefix set only the (cost so far, proxy) pairs that aren't beaten on both counts. This is exact because the remaining cost never decreases as the proxy grows, including with the clamp at 1.
- **The ConvMLP model** looks at windows of consecutive steps, so this doesn't apply exactly. Use the exact optimum of a simpler cost as the annealing start point, or rerank the best few paths with the MLP.

**Optimizing over all optimal orderings instead.** I counted every possible optimal-prefix set in C, with no restriction. It is 9M sets at n = 55 and 52M at n = 57, and ran out of memory at n = 58 on my 7 GB machine. So an exact optimum over all optimal orderings is realistic up to about n = 57–58 on your 16 GB; beyond that, use the kpw table.

**A correction to your Hamiltonian-path paper.** It gives pw(G₅₀) = 10 and pw(G₅₅) = 11, but both kpw and your own MaxSAT model give 9 and 10. So the treewidth-gap claims at n = 50 and 55 don't hold: htd's width equals pw there. Your values for n = 57, 59 and 61 agree with kpw.

**Your sq63 timing.** That's about a 3000× ratio, and I've added it to the paper. Your MaxSAT run took 2637 s, against 198 s here with RC2 and the CaDiCaL 1.9.5 backend. If you used a different backend or option (stratified, `minimize_profile`), that alone could account for the gap.

I can add a complete-table mode and the exact optimizers, with a pluggable step cost, to kpw. The proposed design is in the markdown file, as you prefer to review changes before implementation; say if you want it built.

Files are in orders_scripts.zip:
- many_orders.md
- census.py
- secopt.py
- relcount.py
- fullcount.c
- pathwidth.pdf
- pathwidth.tex

Question
--------
Implement the changes. I'm also attaching another paper by Coudert
et. al. about a branch and bound implementation for pathwidth. It
looks much more complicated than our Kobayashi inspired one. It would
be useful to do a comparison.



Answer
------
I'll read the Coudert et al. paper, then implement the kpw changes and set up the comparison.

The authors' own implementation (Sage's `vertex_separation_BAB`, compiled with Cython) installed and runs. I'll check its options so the comparison uses sensible settings.

Your `ham_ordering.py` imports cleanly on its own, so I can test against your `_dp_cost` directly. Now the module itself.

The command line works, and on g1 the Pareto front reaches 6 labels, so the label DP is doing real work there. Next come tests for the new pieces, then the comparison with BAB.

While the benchmark runs, I'll update the README and write the change notes. That is light work, so it won't disturb the timings.

The reruns haven't produced output yet (the first case can take up to 600 s). Meanwhile I'll add the experiment tables and bibliography entries.

The pages look right. While the BAB reruns continue, I'll write the change notes into the repo.

The tables float past the conclusion, so I'll put a float barrier before it.

The changes are implemented and the comparison is done. Coudert et al.'s branch and bound (Sage's Cython implementation) is about 6–8× slower than kpw. That rises to 10–22× against kpw's new `-g` mode, which borrows one of their greedy rules. It is far faster than MaxSAT: 2.7 s on sq63, against 198 s.

**What's new:**
- **Complete mode.** `kpw -c -o FILE` finishes the last level and writes a DAG whose paths are all pathwidth-optimal orderings. At n = 57 that is 13,762 sets carrying about 10²⁶ orderings, built in 0.1 s; at n = 61 it takes 3.4 s.
- **Orders module** (`orders.py`). It builds or loads the DAG and computes the step features in your DP's direction. Your V2 cost and your `_dp_cost` (V7) are included, and any cost function returning (a, e, k) per step can be plugged in.
- **Exact optimizers.**
  - `optimize` handles proxy costs like V7 by keeping only the (cost, proxy) pairs not beaten on both counts. This is exact because the remaining cost never decreases as the proxy grows; the proof is in the paper.
  - `k_best` gives the k best orderings for additive costs like V2.
  - `sample` draws optimal orderings uniformly.
- **New command.** `kobayashi-pw-orders FILE` runs this end to end and prints orderings in your DP's convention. At n = 61 it takes about 2 min, mostly Python.
- **Second greedy rule.** The first case of Coudert et al.'s greedy step (their Lemma 6) is exactly Kobayashi's subsumption. Their second case can be added to the expansion with every guarantee intact (`kpw -g`, `greedy2=True`). It visits 2–6× fewer sets, but the DAG it produces gives clearly worse orderings, so it is off for ordering work.

**Checks:**
- **Against your code.** My frontier widths match your `frontier_width`, and my V7 matches your `_dp_cost` to 1e-9. Getting there exposed a quirk in your elimination count: a vertex whose neighbours all come earlier enters and leaves the frontier in the same step but isn't counted, unless it is isolated. I reproduced that behaviour.
- **Brute force.** The C program agreed in 6000 runs on random graphs and digraphs. The optimizer matched full path enumeration on 247 small graphs, for both V2 and V7.
- **Cost of the restriction.** On G₂₀–G₂₈, the DAG's best V2 and V7 orderings are within 1.5% of the best over all optimal orderings. That is an empirical result for small n. The unrestricted family is 52M sets at n = 57 and ran out of memory at n = 58 on a 7 GB machine.

**BAB comparison.** I ran it on 58 graphs: square-sum graphs up to n = 63, grids, and random graphs and digraphs with up to 60 vertices. The pathwidths agreed whenever both finished. BAB exceeded 120 s on four 60-vertex random graphs; one of them still hadn't finished after 600 s. That is caused by Sage's default limit on stored prefixes: with the limit raised, it solved all four in 12–43 s, again 8–13× slower than kpw. There's a structural reason the two are close: to prove optimality, a branch and bound with a memo on prefix sets must exhaust roughly the same family of sets below pw that kpw visits. The paper presents that as an explanation, not a proof.

**Paper.** It has new sections on the stronger expansion and on optimal orderings with secondary costs, plus the comparison tables and the Coudert et al. and Sage references. The Gurobi column in Table 4 is still marked [tbd] for your numbers.

The next step would be running your actual frontier DP on the V7-optimal orderings, to see whether exact optimization beats your simulated annealing in real DP time. I couldn't run your DP here. ConvMLP costs look across neighbouring steps, so they can't be optimized exactly this way; use them to rerank `k_best` or `sample` output instead.

Files are in kobayashi-pw.zip:
- CHANGES.md
- pathwidth.pdf
- pathwidth.tex
- src/C/kpw.c
- src/kobayashi_pw/orders.py
- src/kobayashi_pw/orders_cli.py
- tests/test_orders.py
- bench/bench_bab.py
- bench/bab_hard.py
- data/bench/results.tsv

Question
--------
In the future you can make changes directly to the repo on my computer
in ~/Programming/Combinatorics/kobayashi-pw

Answer
------
I'll stage the updated files here, write them into your repo, merge `pyproject.toml` in place, then build and test a copy on your machine.

Merged. Now I'll test a copy in the Linux VM, leaving your repo's `.venv` and macOS binary untouched.

I've merged the latest version into your repo and used your `uv_build>=0.13.6,<0.14.0` pin from `build.toml` in `pyproject.toml`. I tested a copy in a Linux VM on your machine (your `.venv` and macOS `kpw` were left alone): `uv sync` worked with the new pin, all 12 tests pass, and the C program and `kobayashi-pw-orders` give the same results as my runs. Nothing is committed yet.

**What's in the repo now:**
- **Code:** `orders.py` and `orders_cli.py` are new. `kpw.c` has the `-c`/`-o`/`-g`/`-r`/`-q` flags, `core.py` and `cli.py` have the `greedy2` option, and `__init__.py` exports the new functions.
- **Tests and benchmarks:** `tests/test_orders.py`, `tests/__init__.py`, the two `bench/` scripts, and the benchmark results in `data/bench/`.
- **Docs:** `README.md`, `CHANGES.md`, and in `doc/` the latest paper (tex and pdf) and `many_orders.md`.
- **Config:** `pyproject.toml` has the new `kobayashi-pw-orders` command and your pin, and `.gitignore` now ignores `src/C/kpw`.

**One file wasn't written.** The remote tools treat `Makefile` as protected, so you'll need to create it yourself:
```make
src/C/kpw: src/C/kpw.c
	$(CC) -O3 -march=native -Wall -Wextra -o $@ $<
```
The second line must start with a tab. Or just run `cc -O3 -march=native -o src/C/kpw src/C/kpw.c` once.

**Two things to do on your Mac:**
- **Rebuild the C program.** The `kpw` at the repo root is the old version. `kobayashi-pw-orders` looks for `src/C/kpw`; if it doesn't find it, it falls back to the much slower Python build.
- **Run `uv sync`** to install the new command.

Question
--------
In the paper you mention three extensions to kpw: (1) allowing more
than 64 nodes.  I've processed the square sum graphs up to n=75, so
I'd like that. If you want to do this as a separate program that
would be ok. (2) restricting the expansion sweep to adjacent
vertices. (3) Storing only the label x and recovering the predecessor
by search. That should be only by option, since it trades off space
for time (4) parallel processing. Could you implement them?

Answer
------
This is substantial C work, so I'll write the design down first, as you prefer, and then implement it. I'll check the core count here first, since that bounds what I can measure for the parallel version.

Identical counts to kpw in all modes, for both the 64-bit and the 128-bit builds. Next I'll time the restricted sweep, then test `-x` and `-t`.

While that runs, I'll add support for kpw2's DAG format to the Python loader and command line.

The test is still running; the Python reference is slow for n near 110. Meanwhile I'll benchmark threading on your 4-core VM, using a scratch copy so nothing in the repo changes yet.

Meanwhile, I'll update the VM copy and benchmark work stealing on 4 cores.

Work stealing fixes sq63: 2.04 s, 1.07 s and 0.62 s with 1, 2 and 4 threads (3.3× on four). g2 still doesn't scale, and its memory grows. I'll add per-level timing to find which phase is stuck.

Counts are still identical to kpw. Now the 4-core VM.

All six grids return the known pathwidth, up to 121 vertices. Now the square-sum graphs G₆₅–G₇₅, with `-g` first since it is fastest.

All 19 tests pass. Next I'll take final timings on the now-idle container (nothing else running) for the docs and the paper.

Now the paper's data-structures section, which still lists these extensions as future work.

The paper compiles cleanly. Now I'll write everything into your repo.

Everything is written. Last step: a fresh copy of the repo in the VM (Linux, aarch64), built from scratch, with the full test suite and the larger square-sum graphs.

All four extensions are implemented as a separate program, `src/C/kpw2.c`, and are in your repo. It finds pw(G_n) = 14 for odd n from 65 to 73 and pw(G₇₅) = 15, each in under a second. A fresh copy of the repo builds and passes all 19 tests in your Linux VM. I wrote the design note (`doc/kpw2_design.md`) first, as you prefer; nothing is committed.

1. **More than 64 vertices.** Sets are arrays of W 64-bit words, fixed at compile time. The default build handles n ≤ 128, and `-DW=3` gives n ≤ 192.
2. **Expansion restricted to adjacent vertices.** It finds exactly the same sets as before, so with one thread every count matches kpw. The gain is small, because in kpw the full sweep was only 14–18% of the time. A separate change mattered more: the stack now holds one entry per set rather than one per (set, vertex). With 64-bit sets, kpw2 matches kpw's speed with about a third of the memory (57 MB against 201 MB on sq63). The 128-bit build costs about 1.5× in time.
3. **`-x` (store only the label and the parent's size).** The table is 40% smaller. My first recovery search, which undid each expansion step by step, blew up (over 80 s on G₆₁ and out of memory), so I replaced it. It now scans the table once per extraction step for a stored set that leads to the current one; that takes 0.1 s or less on the graphs tested.
4. **`-t N` threads** (`-t 0` = all cores). It uses plain pthreads, so Apple's compiler works without OpenMP. On your 4-core VM, four threads gave about 2–2.5× (sq63 1.1 s → 0.4–0.6 s; g2 2.2 s → 1.4 s). The search is dominated by hash-table cache misses, which limits the scaling.

**Checks:**
- Brute force on small graphs and digraphs, in every flag combination, with counts identical to kpw.
- Grids up to 11×11 (121 vertices) give the known pathwidth.
- Random graphs and G₆₅, G₆₇, G₇₅ agree with the Python implementation, including identical set counts.
- I ran the small graphs and grids beyond the test suite. The Python check stopped short on denser random graphs with n > 64 because it was too slow; the sparse ones checked all had pw ≤ 4.

**Ordering optimization beyond 64 vertices:** `kobayashi-pw-orders` now calls kpw2 automatically when n > 64, and has a new `--threads` option. For G₇₅ the DAG of optimal orderings has 132,400 sets and about 5.5 × 10³⁸ orderings. The V7 optimum took about a minute in Python and agrees with your `_dp_cost`.

**On your Mac:** I can't write your `Makefile` remotely. Either add this rule (the second line starts with a tab), or run the command once:
```make
src/C/kpw2: src/C/kpw2.c
	$(CC) -O3 -march=native -pthread -o $@ $<
```
I also added the square-sum edge lists `data/sq61.txt` and
`data/sq65.txt` through `data/sq75.txt`. The paper's data-structures
section now describes the four extensions, with these
measurements. README.md and CHANGES.md are updated.

Question
--------
Could you make the following change to kpw.c and kpw2.c: The input is
an edge list. You assume that they're integers in [0,n) for some
n. The standard edgelist definition allows the nodes to be strings
separated by a space. So, for the square graphs you include a node of
0, which really isn't there. Can you handle an edgelist given with
node names, and calculate a map to [0,n) for processing, and then
convert back for the output ordering. Also, is the structure of the
output DAG defined anywhere? If not it should be documented in the
markdown.

Answer
------
I'll check the repo's current state first, in case anything changed since Tuesday.

`kpw` now reports n = 63 for sq63, with no dummy vertex, and prints the original names. Now `kpw2.c`:

Both programs now accept named vertices and print the names back, and the sq63 counts are unchanged. Next, the Python side: align the reader's integer rule and teach the loader the new format.

Docs are updated, and the paper needs no change. Now I'll write everything into your repo.

`kpw` and `kpw2` now read edge lists with any vertex names and print orderings using those names. The DAG file format was not documented anywhere before except in source comments; `doc/dag_format.md` now defines it. A fresh copy of the repo builds in your Linux VM and passes all 24 tests.

**Input.** Both programs now use a shared parser in `src/C/edgelist.h`:
- **Format.** Lines are "u v [data...]", networkx style. Extra fields such as `{}` or a weight are ignored, a single token on a line is an isolated vertex, and `#` starts a comment.
- **Numbering.** If every name is an integer and no two have the same value, vertices are numbered by increasing value. Otherwise they are numbered in order of first appearance.
- **No phantom vertex.** The square-sum files labelled 1..n now give n vertices. sq63 reports n = 63 instead of 64, with the same pw and search counts as before.
- **Size limits** are now on the number of vertices, not on the labels: 64 for `kpw`, 128 for the default `kpw2` build.

**A small change on the Python side.** Its reader now uses exactly the same numbering rule, so the C and Python searches stay identical. Before, it merged names with equal integer value (`07` and `7`) and accepted `--5` as an integer.

**DAG file.**
- **New version.** Both programs now write `KPWDAG3`, which adds the vertex names at the end. `OrderDAG.load` reads it and uses the names as labels. It still reads the two older versions; `data/sq63.dag` is one of those, and its labels come back as bit indices.
- **The new document** covers the byte layout and what the file means:
  - which sets are stored, and that the full vertex set is implicit;
  - the rule for recomputing arcs, since arcs aren't stored;
  - the exact expansion procedure, with and without `-g`;
  - how a path becomes an ordering, and which direction to read it in;
  - the older formats;
  - a short reader you can copy.

**New tests** (`tests/test_edgelist.py`, 5 tests) check:
- random graphs with arbitrary names in shuffled order, with extra fields and comments, against brute force;
- integer names with gaps and negative values give the same set counts in C and Python;
- the `07`/`7` case;
- sq63 has no dummy vertex;
- names survive in the DAG file.

**On your Mac:** rebuild both programs, because the binaries in `src/C` are the old ones:
```
cc -O3 -march=native -o src/C/kpw src/C/kpw.c
cc -O3 -march=native -pthread -o src/C/kpw2 src/C/kpw2.c
```
Nothing is committed. README.md, CHANGES.md and `doc/kpw2_design.md`
are updated.

Question
--------
This algorithm ended up being a huge improvement over the MIP/MaxSat
algorithm. An interesting question is if the ideas in this algorithm
can be applied to the computation of other width decompositions such
as cutwidth, bandwidth or treewidth. Can you investigate that?

Answer
------
This is a research question, so I'll check the literature first, then test the ideas with small prototypes before writing anything up. I'll start with what is known about cutwidth and treewidth parameterized by vertex cover, and about exact solvers for each width.

The Cygan et al. result exists: cutwidth in 2^k·n^O(1) time, with k the vertex cover number. I'll read their argument to see whether it is the same greedy placement rule I derived.

Everything matches brute force except cutwidth with the vertex-cover restriction, which is always exactly one too high. So my restriction argument has a gap. I'll take a failing case apart.

I'll correct two counts in the report: the number of graphs checked and the number of cutwidth runs.

Now the change log and README, then I'll write everything to your repo and test it on the VM.

Your copies are unchanged since my last write, so it's safe to overwrite them.

The ideas carry over completely to cutwidth, only partly to treewidth, and not at all to bandwidth. They also come from one general lemma, which seems to be new as stated. I've written this up in `doc/other_widths.md`, with a Python prototype in `src/kobayashi_pw/widths.py`; both are in your repo, and nothing is committed.

**The lemma.** Suppose the prefix cost f is submodular, as |N(S)| and the cut size are. Then a vertex whose addition doesn't increase f can be added at once without losing optimality. The proof is a short exchange argument, and it is independent of any width bound k. For vertex separation, "adding v doesn't increase |N(S)|" turns out to be exactly Kobayashi's subsumption rule or Coudert–Mazauric–Nisse's second rule. So both published rules are one statement; I checked that identity on 73,080 cases. A brute-force check on 200 random graphs and digraphs found no counterexample to the lemma itself.

**Cutwidth: everything transfers.**
- **What existed.** The lemma is the rank argument (Lemma 1) of Cygan et al. Their known 2^k bound, with k the vertex cover number, needs a vertex cover. We give an algorithm for CUTWIDTH with running time O(2knO(1)). Here k is the size of a minimum vertex cover of the input graph G.
- **What I built.** The same one-pass search as kpw, with the "rank ≤ 0" closure and an optional restriction to vertex-cover vertices. The search only touches states up to the optimum, which in practice is far below 2^k.
- **A trap.** My first attempt at the cover restriction delayed vertices naively and came out one too high on 75 of 400 test graphs. The fix follows Cygan et al.'s normal form: Odd-degree I-vertices have rank ±1. In practice that means placing the right number of a cover vertex's balanced neighbours just before it.
- **Checks.** The corrected version agrees with brute force in all 1,520 runs, on random and bipartite graphs up to n = 13.
- **Square-sum graphs.** Exact cutwidth for G₂₅–G₆₀, with cw(G₆₀) = 22, took 6 minutes in Python. At n = 40 it settled 3,465 states, against about 200,000 without the rules. Values for n ≥ 45 rest on the proof and the small-graph tests; each is attained by its ordering, and each is consistent with pw ≤ cw.
- **Next.** A C port is straightforward from kpw2.

**Treewidth: partly.**
- **What transfers.** The one-pass search applies to the elimination-ordering DP, and the prototype agrees with brute force.
- **What doesn't.** There is no submodular prefix cost here, and the safe rule (eliminate simplicial vertices) is weak: on G₂₀ it only cut settled states from 61,963 to 20,788. That DP is also far behind the state of the art. Tamaki's positive-instance-driven solver solves all of the 100 public instances posed by the exact treewidth track in PACE 2017.
- **Where it could help.** Replacing PID's loop over k by a single pass, which needs Knuth's generalised Dijkstra. I'd expect only a constant factor, but haven't measured it. My recommendation is to use an existing PID solver.

**Bandwidth: no.** The cost depends on positions, not on the set of vertices placed so far. The exact DPs therefore keep the last b vertices in order, so the state space depends on b. That rules out both the single pass and the exchange lemma. What does help:
- kpw gives a good lower bound, since pw ≤ bw.
- An incremental SAT search starting from that bound is the natural approach; there exists an ILP/SAT formulation with O(n²) variables and O(n·m) constraints / O(n³) clauses.
- Specialised branch and bound is the other option.

Two natural next steps are a C cutwidth solver and an experiment with linear rank-width. The cut-rank function is also submodular, so the same engine applies, but there it would be purely empirical.

**Testing.** Four new tests are in `tests/test_widths.py`, bringing
the suite to 28, all passing here. On your Linux VM I ran the width,
core and order tests: 15 passed and 1 skipped, because that copy
didn't have the C binaries built.

Question
--------
Can you add a section (or more than one) to the latex paper about
this? Perhaps this means that the title and introduction need changing
too.

Answer
------
I'll check whether the paper in your repo has changed since I last wrote it, then plan the edits.

Now the new section itself.

The layout looks right. The new table is now Table 1, and the later tables are renumbered automatically. Next I'll write the paper to your repo.

I've added a section on other width parameters and updated the title, abstract and introduction to match. The paper compiles cleanly at 21 pages, and the `.tex` and PDF in your repo's `doc/` folder are updated; nothing is committed.

**New Section 6, "Other width parameters":**
- **What the method needs.** Three properties: a step cost that depends only on the prefix set and the next vertex, a min–max objective, and greedy rules that don't depend on the width bound. The correctness and optimal-ordering proofs carry over verbatim.
- **6.1, the greedy lemma for submodular costs.** It is proved in Lemma 22. Proposition 23 shows that for vertex separation, the lemma's condition is exactly Kobayashi's rule or Coudert–Mazauric–Nisse's second rule. So both published rules follow from it. A remark gives the path counterexample showing that the mirror-image statement (delaying a vertex) is false.
- **6.2, cutwidth.**
  - **Method:** the same search with the "rank ≤ 0" closure, plus the restriction to vertex-cover vertices from Cygan et al.'s normal form.
  - **Proposition 25:** at most 2^τ states, matching their bound.
  - **Table 1:** the square-sum graphs up to cw(G₆₀) = 22.
  - **What the paper says is unproved:** that the closure is compatible with their normal form is not fully proved. It rests on 1,520 brute-force runs, and the paper also mentions that a naive first version was one too high on 75 of 400 graphs.
- **6.3, treewidth and bandwidth.**
  - **Treewidth:** the search applies to elimination orderings, but the safe rule is weak, and Tamaki's PID is the right tool. A single pass via Knuth's generalised Dijkstra might give a constant factor; that is unmeasured.
  - **Bandwidth:** doesn't fit, because its cost depends on positions. What transfers is the lower bound pw ≤ bw.

**Other changes:**
- **Title:** now "One-pass bottleneck search for linear width parameters: exact pathwidth and cutwidth, optimal orderings, and secondary costs".
- **Abstract:** a new paragraph on the lemma, cutwidth, treewidth and bandwidth.
- **Introduction:** an "Other widths" paragraph and two new contributions.
- **Stronger-expansion subsection (4.1):** now points to the lemma.
- **Conclusion:** a paragraph naming linear rank-width as the next candidate.
- **Bibliography:** seven new entries:
  - Cygan et al. on cutwidth;
  - Tamaki;
  - Knuth;
  - Saxe;
  - Gurari–Sudborough;
  - Cygan–Pilipczuk on bandwidth;
  - Biedl et al.

  The page numbers and volume details for Saxe, Gurari–Sudborough, Knuth and the ACM version of Cygan–Pilipczuk are from memory, so please check them.

Inserting Table 1 shifts the numbers of the later tables and
sections. `\cref` updates all the references, but tell me if you'd
rather keep the old Table 1 numbering. The previous version of the
paper is saved as `pathwidth_v3_backup.tex` in my working folder, not
in your repo.

Question
--------
It might not make that much of a difference, but it would informative
to take the Cython source of Coudert's code, and convert it to C. That
way it would also be available directly in the repo. Can you do that?

Answer
------
I'll find the Cython source of Sage's `vertex_separation_BAB`, either in the installed package or its source distribution.

The glob picked up the benchmark results file. I'll restrict it to the graph files.

Before overwriting, I'll check that the device repo's README and CHANGES match the base my edits were made against.

Only my changes differ. Committing to the repo.

I've translated Coudert's Cython branch and bound into C as `src/C/bab.c` and added it to `~/Programming/Combinatorics/kobayashi-pw`, uncommitted. It makes exactly the same search decisions as Sage's version, runs about 4× faster, and kpw is still about 2–3× faster than it.

**Matching Sage.** I compared the two step by step on 463 cases: random graphs and digraphs with n ≤ 16, runs with each of the four limit options changed (`-l`, `-m`, `-k`, `-u`), and the benchmark graphs with n ≤ 50. The width, the sequence of improved upper bounds, the number of stored prefixes and the final ordering were identical in every case. That is agreement on tests, not a proof that the two are equivalent.

The C version handles any n and has the same options as Sage. Like Sage, it measures the boundary with out-neighbours; the width is the same as kpw's, but the orderings differ.

**Timings** (seconds, one core, one run each):

| graph | Sage | C bab | kpw |
|---|---|---|---|
| sq59 | 2.08 | 0.49 | 0.26 |
| sq61 | 4.71 | 1.28 | 0.65 |
| sq63 | 2.71 | 0.75 | 0.42 |
| gnp_n60_d3_s0 | 12.18 | 2.80 | 1.36 |
| gnp_n60_d4_s2 | 7.87 | 1.93 | 0.64 |
| gnp_n60_d5_s0 | 5.38 | 1.44 | 0.71 |

The C version is 3.6–4.4× faster than Sage, because it doesn't use Python objects in the inner loop; the search itself is the same. kpw is still 1.8–3.0× faster than the C version.

**Timeouts.** The four gnp_n60 instances where Sage timed out (> 120 s) also run past 300 s in C with Sage's default limits on stored prefixes (prefix length 20, at most 10⁶ stored). The cause is those limits, not the branching: once nothing more can be stored, the same prefixes get searched over and over. With the limits raised (`-l 64 -m 10000000`):

| graph | C bab, raised limits | kpw |
|---|---|---|
| gnp_n60_d4_s0 | 10.9 s | 4.2 s |
| gnp_n60_d4_s1 | 2.9 s | 1.7 s |
| gnp_n60_d5_s1 | 4.5 s | 1.5 s |
| gnp_n60_d5_s2 | 3.3 s | 1.6 s |

**What I added:**
- **Tests:** `tests/test_bab.py` checks the C version against brute force on 400 random graphs and digraphs, with and without the limits, and checks the bound options. The full suite passes here (31 tests).
- **Comparison script:** `bench/bab_parity.py` reruns the comparison with Sage; it needs Sage installed.
- **Write-up:** `doc/bab_port.md` has the translation notes, the matching results and both tables above.
- **Docs:** I added the build line `cc -O3 -march=native -o src/C/bab src/C/bab.c` and a section on the program to `README.md`, and an entry to `CHANGES.md`.
- **`edgelist.h`:** its functions are now `static inline`, which stops an unused-function warning when compiling `bab.c`.

**Licence.** Because it's derived from Sage, `bab.c` is GPL-2-or-later and its header credits Nathann Cohen and David Coudert. The README says this applies to that file only. If the rest of the repo is going to have a different licence, you'll want to decide whether keeping a GPL file in it is acceptable.

On your machine, `bab.c` compiles with `-Wall -Wextra` without
warnings and gives pw=14 on sq63. I couldn't run pytest there: `uv`
needs to delete its own lock file in `.venv`, and file deletion isn't
allowed in that folder from here. Running `uv run pytest -q
tests/test_bab.py` yourself will check it.

Question
--------
I've cloned a recent repo of Coudert's about cutwidth. It's at
/Users/victorsmiller/Programming/Combinatorics/cutwidth on my mac. It
would be interesting to compare the new cutwidth algorithm you've
outlined with his results.

Answer
------
I'll look through Coudert's cutwidth repo first, then run our cutwidth
search on the same instances.

Question
--------
Maybe it would be better to translate the cython code to C, as you did with bab.

Answer
------
I may not need a C translation for the comparison. I've compiled Coudert's Cython code here against passagemath: `bab_dfs`, `bab_bfs`, `cstar`, `lowerbounds` and `heuristics`. That gives same-machine timings, so the comparison doesn't depend on numbers from his machine. On Grid9x9 his own `.res` files list BB+ 1.44 s and BB3+ 1.65 s; here they took 0.19 s and 0.30 s, so his recorded times can't be compared across machines directly.

Unlike Sage's pathwidth BAB, his cutwidth code is already mostly typed `cdef` code, with C++ vectors and bucket queues. For `bab.c` the 4× gain came mostly from replacing a Python set of frozensets, and his cutwidth code has no equivalent bottleneck, so I'd expect a smaller speedup here. Translating BB3+ means about 100 KB of Cython: the BFS search, the C\* grooming lower bound and the GRASP heuristic. I'll finish the same-machine comparison with his compiled code first. If you still want a standalone C port of BB3+ in the repo after that, I'll do it next.

Only my mtime rounding was off; the md5s match my last commit, so I'll pass the exact mtimes.

I wrote the cutwidth algorithm as a C program, `src/C/kcw.c`, and ran it against Coudert's code on the same machine. On sparse structured graphs it is much faster than his best codes, BB+ and BB3+. On dense graphs and graphs of large width it runs out of time or memory, and there his lower bounds are stronger. For the comparison I compiled his Cython against passagemath and ran it here instead of translating it to C; if you still want a C port of BB3+ in the repo, I'll do that next.

I wrote the design note `doc/kcw_design.md` before implementing. kcw uses:
- the rank closure;
- the Cygan et al. vertex-cover normal form, so a state is stored as its intersection with the cover;
- twin symmetry breaking. I added this after his K₆₆ instance (`bcsstk02`) defeated the first version.

kcw has no heuristic and no lower bound on what remains to be placed.

**Correctness.** The proof is the greedy lemma, the Cygan normal form, and the fact that swapping twins is a graph automorphism. On the testing side:
- kcw agreed with the 2ⁿ brute force in 5,400 runs (n ≤ 12, including graphs with many twins), with and without each reduction.
- It re-checks every ordering it prints.
- Its values agree with Coudert's on all 147 instances both solve.

**Same machine, 300 s per run.** His recorded times come from a machine about 5× slower, so these numbers are from runs here. His times exclude his preprocessing (GRASP upper bound and lower bound), which took 5–100 s per graph; kcw's times are for the whole run.
- **Solved:** kcw solves all 156 graphs that his runs had solved, plus the Harwell–Boeing graphs kcw solved in a first 30 s pass. BB+ or BB3+ solve 147 of them.
- **Speed:** on the 25 instances where both solve and either needs more than 0.1 s, kcw is 2.5–2,200× faster than the better of his two, with a median of 37×. Grid12x12 takes 0.66 s against 50 s; can__144 takes 0.055 s against 123 s.
- **Only kcw:** the 12×21, 12×24 and 12×27 grids, arc130 and fs_680_1. On nos2 his preprocessing alone ran past the 420 s guard.

**Beyond what he solved in 3-hour runs.**
- **Grids:** Grid15x15, Grid15x18 and Grid15x21 all have cutwidth 16 (52 s, 128 s, 206 s). Grid18x18 stopped at the 110 M-state limit with cw ≥ 17 proved; his upper bound is 19.
- **saylr1:** kcw's proved lower bound of 15 meets his upper bound of 15, so cw = 15. This assumes his reduction (contracting degree-2 vertices) preserves cutwidth, which I didn't check.
- **GPW2024 random graphs:** kcw gets exact values for 50 of the 76. On every one of the 30 that have published bounds, the value equals their heuristic upper bound. On 10 of the unsolved ones, kcw's 30 s proved lower bound beats their SDP bound (e.g. geo32: 299 against 245).

**Where kcw is weak.** On the 68 Harwell–Boeing graphs it doesn't solve, its 30 s lower bound beats his recorded one on 37 and is weaker on 26. The weaker ones are mostly dense or have large cutwidth (mcca, the str__ family, west0381). That's the cost of having no remainder bound: kcw must exhaust every level below the cutwidth. The natural next step is to use his grooming lower bound as an estimate of the remaining cost (an A\* search); I haven't tried it.

**Repo changes.** The following are in `~/Programming/Combinatorics/kobayashi-pw`, uncommitted to git:
- `src/C/kcw.c`
- `tests/test_kcw.py` (the full suite passes, 36 tests)
- `doc/kcw_design.md` and `doc/cutwidth_comparison.md` (attached, with the full tables)
- `bench/cutwidth/`: drivers and a `setup.py` that builds his code against passagemath
- `data/cutwidth/`: his graphs and recorded results, plus our runs
- README and CHANGES updates

Two things need your action:
- **His source archive:** I'd put a copy of his source in `data/cutwidth/coudert_src.tgz` so I could read it here. I can't delete files in that folder, so I moved it to `data/cutwidth/_to_delete/`; please delete that folder.
- **Makefile:** the Makefile is protected from my edits. To build kcw with it, add `cc -O3 -march=native -o src/C/kcw src/C/kcw.c`.

Question
--------
All of these algorithms have the same sort of flavor. I would like to
see if we can write a DSL which can describe the overall flow of the
algorithms, and then annotate pieces of it concerning concrete data
structures. The ideal is that the code of kpw, and kcw can be
specified in a fairly short description which is rigorous.

Answer
------
I've written the design for the DSL as `doc/dsl_design.md` (attached, and also in the repo). Nothing is implemented yet. In it, kpw takes about 20 lines of problem description plus about 10 of data-structure annotations, and kcw takes about 30 plus 10, with each correctness claim tied to a named lemma.

**Why one DSL can cover them.** In all three problems the cost of the next step depends only on the set S already placed and the vertex v being added:

| problem | step cost w(S, v) |
|---|---|
| vertex separation | f(S+v), with f(S) = \|N⁻(S) ∖ S\| |
| cutwidth | f(S+v), with f(S) = the number of edges between S and the rest |
| treewidth | \|Q(S, v)\| |

So each width is a minimum-bottleneck path from ∅ to V through subsets. What differs between kpw, kcw and the treewidth prototype is a set of reductions that don't change the answer, plus the data structures. Bandwidth isn't of this form, so it's out of scope by design.

**Three pieces:**
- **Problem layer.** This states the cost and the reductions: closure rules, which vertices may be chosen, prefix sequences placed before a choice, symmetry, and what the hash table stores as a state's key. Each reduction carries `by LEMMA`, pointing to a library of lemmas with precise hypotheses. Arc costs are derived automatically as the maximum along each move. A hand-written closed form, like kcw's, needs its own lemma.
- **Data layer.** This holds annotations such as how sets are represented, which quantities are maintained incrementally or recomputed, the hash table, how deferred states are rescanned, probing the table before closing a set, label-only parent recovery, and parallelism. Each annotation comes with a condition guaranteeing it can only change time and memory, never the result.
- **A fixed search engine,** proved correct once. Its theorem covers optimality, extracting the ordering, and the certified lower bound when a run is stopped. A spec has to meet four conditions:
  1. Each arc cost is exact.
  2. Completeness: an optimal ordering can be built from the allowed moves.
  3. The stored key determines the state.
  4. Replaying a move is deterministic.

  Condition 2 is the only one with real mathematical content. It comes from composing lemmas: the submodular greedy lemma, the Cygan et al. vertex-cover normal form, and the fact that swapping twins is a graph automorphism.

**Things that surfaced while writing it:**
- kcw's requirement that the vertex cover contain all twins of its members, which I added by hand in kcw.c, appears in the spec as the automorphism lemma's hypothesis.
- kpw's "probe the table before closing a set" and "rescan only the window (lo, B]" become data-layer annotations with stated conditions.
- Treewidth fits without changing the engine. Its simplicial closure can raise a move's cost, and the maximum over the move absorbs that. I wrote down a general form that every closure lemma must satisfy.
- Coudert's grooming lower bound would enter through an optional `bound` clause, which turns the search into A\*. Its proof obligation is that the bound never overestimates the best completion.

**What I'd build:**
1. An embedded Python version first: the engine as the reference semantics, plus a checker that tests conditions 1, 3 and 4 on every arc and condition 2 against brute force.
2. Then a generator that emits only each problem's per-problem C operations against a hand-written engine.
3. The test of success: the generated kpw and kcw reproduce the current programs' outputs at a time within about 1.3×.

Before I implement, I need four decisions from you (§9 of the doc):
- **Embedded or textual first?** I'd start with the embedded Python DSL and add a parser for the textual syntax later.
- **What to generate?** I'd generate only the per-problem C operations against a fixed engine, rather than complete programs.
- **First milestone?** I'd do vertex separation and cutwidth plus the checker first, and leave the DAG output, label-only storage and threads for later.
- **Lean or not?** Formalising the engine theorem and the greedy and
  submodularity lemmas is a contained project; the vertex-cover normal
  form is the expensive part. Do you want that track, or is "lemma
  with reference plus randomized checks" rigorous enough for now?
  
Question
--------
An interesting implementation would be like pytorch - the DSL is
embedded in Python, which then "under the covers" generates a C
program which is compiled on demand (with appropriate caching).

Answer
------
I'll fold that architecture into the design doc: how the embedded Python DSL is traced into an intermediate representation, generated as C, compiled on demand and cached.

I've rewritten §8 of `doc/dsl_design.md` around that model; it's updated in the repo and attached. Nothing is implemented yet.

- **Tracing.** The spec is ordinary Python: lambdas over symbolic `Set`, `Int` and `Vertex` objects. Each lambda is called once with symbolic arguments, which records a typed expression graph (the IR) without touching the graph. As with PyTorch's tracer, branching on a symbolic value is an error; you write `P.min` or `P.where` instead of `if`. §8.1 has the full cutwidth spec in this style, about 20 lines.
- **Two modes over one IR.**
  - **Eager** interprets the IR in Python. It is the reference semantics and drives `spec.check()`, which tests the four conditions from my previous message (exact arc costs, completeness, keys that determine the state, deterministic replay) against the 2ⁿ brute force.
  - **Compiled** lowers the IR to C: bitset loops, popcounts, and comprehensions as bit loops. Wherever an expression matches a quantity the data layer says to maintain, such as kpw's `nb` or kcw's `a[v]`, it reads the maintained value instead.
- **What gets generated.** Only a per-problem `ops.h` of `static inline` functions, which a fixed hand-written `engine.h` includes. The compiler inlines them into the search loop, so there are no function pointers in the hot path. The graph and its constants are passed in at run time, so one compiled library serves every graph.
- **Compiling and caching.**
  - The cache key is a SHA-256 of the IR, the data-layer annotations, the number of 64-bit words per bitset, the engine version and the compiler with its flags.
  - Libraries live in `~/.cache/kobayashi_pw/<key>/`. Compilation is locked and atomic, so several processes can share the cache safely.
  - The word count is rounded up to 1, 2, 4, 8 or variable, so a new n usually reuses an existing library; this is like torch.compile's shape guards.
  - A debug build adds sanitizers and checks maintained values and closed-form costs against recomputation.
  - Without a C compiler it falls back to eager mode.
  - The call releases the GIL, and Ctrl-C still returns the certified lower bound.
- **Acceptance test.** On `data/` and Coudert's sets, the vertex-separation and cutwidth specs must reproduce kpw and kcw: the same widths, the same state counts, and a time within about 1.3×. Treewidth must run without engine changes.
- **Main risk.** Matching hand-tuned speed depends on recognising a few idioms. The escape hatch is `P.native(...)` with a debug-mode equivalence check.

Two decisions are still open:
- **First milestone.** I'd build the tracer, the eager mode with `check()`, the C lowering with the cache, and the vertex-separation and cutwidth specs, plus treewidth in eager mode only. The DAG output, label-only storage, threads and an A\* `bound` clause would wait for a second milestone.
- **Lean.** Do you want machine-checked proofs of the engine theorem and the greedy and submodularity lemmas? Or is a cited lemma plus randomized checks enough for now?

If the milestone looks right, I'll start on it.

Question
--------
On first scan I do like your syntax, which is very functional oriented
(I'd always want to describe the algorithm functionally, and then use
an implementation to map into efficient code). So to do this you'd
have to write a compiler (perhaps in python).

Answer
------
Yes, it means writing a compiler, in Python. It's a much smaller job than a general one, though, because the language is narrow: no user loops, recursion or mutation, just set algebra, comprehensions and a fixed set of clauses. The search loop itself isn't compiled at all; it's the hand-written `engine.h`. My estimate is 2–4k lines of Python for the first milestone. I've added the stage-by-stage plan to `doc/dsl_design.md` as §8.7:

1. **Tracer.** Symbolic objects with overloaded operators build a typed expression graph. Identical subexpressions are shared automatically.
2. **Analysis.** It works out what each node depends on: the state S, the chosen vertex x, a comprehension variable, or only the graph. Graph-only parts are precomputed once per solve. Lemma hypotheses are checked by pattern-matching on this graph.
3. **Rewriting.** Set-algebra simplification, plus rewriting f(S+v) − f(S) to its derivative when f has a known form.
4. **Incremental maintenance.** This turns "maintain q(S)" into an update rule for adding a vertex, with its inverse for undo. It's Paige and Koenig's finite differencing of set expressions, from SETL. It's the step that turns a functional definition like nb(S) = ⋃_{u∈S} N_in(u) into kpw's `nb |= nin[x]`.
5. **Lowering.** Each set expression is either stored as bitset words or just looped over, according to how it's used and to the data-layer annotations. A count or "exists" over a comprehension never builds the set.
6. **Emission** of the generated C functions, plus the debug-build assertions, then compilation and caching as described in §8.4.

The eager interpreter is simply an evaluator for the stage-1 expression graph. It defines the semantics every later stage must preserve, and `check()` tests that.

Your preference for a functional description mapped onto efficient code has close precedents:
- **Halide** separates the algorithm from the schedule. That is exactly the split between our problem layer and data layer.
- **TACO** separates sparse-tensor expressions from per-operand storage-format annotations.
- **Doug Smith's KIDS/Specware at Kestrel** is the closest in spirit. It derived search algorithms from functional specifications through algorithm theories (global search with dominance relations and filters), then refined the data structures. It used finite differencing as a standard step too.

Our lemma library plays the role of those algorithm theories, specialised to set-determined bottleneck problems.

I still need your call on two things. Is the first milestone right:
the tracer, eager mode with `check()`, the C lowering with caching,
and the vertex-separation and cutwidth specs matching kpw and kcw? And
do you want the Lean track for the engine theorem and the greedy and
submodularity lemmas?

Question
--------
Yes, the first milestone looks good. Afterwards the lean formalization
is what I'd like.

Answer
------
Before coding I'll write the milestone plan into the repo, since you like changes documented first. Then I'll implement it.

Now the code generator, the heart of the compiler:

Now the rewrite rules and the runtime/engine headers:

Now the three specs:

Generated code now matches or beats the hand-written programs everywhere I've measured, with identical state counts for cutwidth. Next, a full acceptance run over the benchmark sets:

Committed. A smoke test on your machine's side (aarch64 VM, different compiler):

Milestone 1 is done and in `~/Programming/Combinatorics/kobayashi-pw`, uncommitted to git. You write a spec as functional Python, and `P.solve(g)` turns it into C, compiles it, caches it and runs it. The generated vertex-separation and cutwidth programs give the same widths as kpw and kcw, and are usually faster. The one exception is kpw's `-g` rule, where they are slower.

The plan is in `doc/dsl_milestone1.md` (attached), written before the code, along with what changed during the build and the results.

**What you write.** Each spec is about 15–25 lines in `dsl/specs.py`. `P.pretty()` prints the spec in the notation of the design doc. `P.report()` lists each clause with its lemma and whether the lemma's hypothesis was:
- checked syntactically on the expression graph (e.g. "cost is a cut function", "the closure predicate is Δ ≤ 0");
- checked at run time on the actual graph (e.g. "C is a vertex cover closed under twins");
- or simply assumed.

**How the compiler works.**
- **Tracing.** The spec's lambdas are traced into a typed expression graph in which identical subexpressions are shared. Bound variables get canonical names, so kcw's Y set, which appears four times in the spec, is generated once.
- **Lowering to C.**
  - Set expressions become word-wise bitset operations.
  - Quantities that depend only on S are computed once per expansion rather than once per move.
  - The arc cost is derived by rewriting f(S + x) in terms of S.
  - Closures become a worklist over the neighbours of added vertices when the predicate only reads N(v) ∩ S, and full sweeps otherwise.
  - The hand-written engine (`src/C/dsl_rt.h`, `src/C/dsl_engine.h`) includes the generated per-problem functions, so the compiler inlines them into the search loop.
- **Caching.** Compiled libraries are cached under `~/.cache/kobayashi_pw/` with a SHA-256 key, and Ctrl-C still returns the proven lower bound.
- **Incremental counts.** The data layer can keep vertex-indexed counts such as kcw's |N(v) ∩ S| up to date, applying each move in place and then undoing it. This matched kcw's speed on large graphs; plain popcounts lost to kcw from about 5 words per bitset upward.

**Correctness checks.**
- `P.check()` tests every arc of the eager search for the obligations O1, O3 and O4 from the design doc. It also tests the closure hypotheses (each addition doesn't raise the cut; the predicate is monotone in S) and compares widths against the 2ⁿ brute force. It passed on over 2,000 random graphs and digraphs with n ≤ 10.
- Every ordering the compiled code returns is re-checked.
- The full test suite passes (46 tests).
- It also compiled and ran on your machine's VM (aarch64, Python 3.10).

**Speed against the hand-written programs.** All runs were on this machine, single-threaded, one after the other.

| comparison | graphs | widths | time |
|---|---|---|---|
| DSL vs kpw | 61 | all agree | 11.9 s vs 17.1 s total |
| DSL vs kpw `-g` | 61 | all agree | 7.3 s vs 6.1 s total; worst single graph 1.45× slower |
| DSL vs kcw | 156 (the Coudert set) | all agree | 0.20–0.92× kcw's time on the 14 graphs where kcw needs over 0.3 s (Grid12x27 0.90, fs_680_1 0.85) |

The `-g` loss is because the second closure rule is run as full sweeps, where kpw scans only the in-neighbour boundary. For cutwidth, state counts are identical to kcw's on grids, square-sum graphs and Harwell–Boeing graphs. On a few random graphs they differ slightly (319 vs 341 states), from a tie-break difference I haven't tracked down.

**Treewidth** runs in eager mode with no engine changes. Compiled mode correctly refuses it, because its simplicial closure can raise a move's cost.

**Left for milestone 2:**
- a closure worklist for predicates like the second kpw rule, which read S through more than N(v) ∩ S;
- packed keys (|C| bits instead of n);
- the optimal-orderings DAG output, label-only parent storage, and threads;
- the A\* `bound` clause;
- named subexpressions in `pretty()`, which currently inlines Y and i in full.

Next, as you asked, I'll start the Lean formalisation. I plan to begin with:
- the abstract move system and the four obligations;
- Theorem E for the bucketed search;
- the greedy lemma for submodular f;
- submodularity of the cut and coverage functions.

The vertex-cover normal form would come last, since it's the expensive
one.

Question
--------
Do the lean formalization. Also, why is the generated C code slightly
slower than the handcrafted kpw (for instance). Can code generation
from the DSL be made to match that?

Answer
------
I'll set up a Lean project inside the repo (Lean 4.36.0 + Mathlib v4.36.0, the latest stable pair) and build it with the Lean server on your Mac.

While Mathlib's cache downloads, I'll write the formalization. First the core definitions and the move-system theorem:

Now the greedy lemma and the completeness of greedy-closure systems — the mathematical heart:

Width.lean compiles (it was just Mathlib's first cold load). Checking the rest:

MoveSystem.lean compiles, with only a linter warning. Now pushing Instances.lean and checking Engine and Greedy:

Two small errors, both elaboration-order issues. Fixing:

While Engine.lean elaborates, I'll write up the code-generation performance analysis:

Engine.lean compiles cleanly. Now the fixed Greedy.lean:

Greedy.lean (the greedy lemma and completeness of greedy-closure systems) now compiles with no errors. Checking Instances.lean:

Two small errors in the cut-increment proof. Fixing:

All five Lean files now elaborate with no errors and no `sorry`. To confirm nothing rests on unproved assumptions, I'll print the axioms each main theorem depends on:

Meanwhile, committing the code-generation changes. I'm staging them under fresh names and verifying every file by checksum, including files from the earlier milestone commit:

Everything matches except `doc/dsl_design.md`: your copy is stale from the same transfer bug, so the later revision (§8.7 on the compiler) never reached you. Re-sending it:

Meanwhile, the Lean documentation:

Every main theorem depends only on Lean's three standard axioms. Final docs and commit:

The Lean formalisation is done and checks on your Mac: kpw is proved correct with or without `-g`, and so is cutwidth with the rank closure only. The generated code is no longer slower than kpw; it was one missing optimisation, now fixed.

## Lean formalisation (`lean/`, Lean 4.36.0 + Mathlib v4.36.0)

It is about 600 lines in five files and compiles with no `sorry` and no errors. An axiom audit (`Axioms.lean`) shows every main theorem depends only on `propext`, `Classical.choice` and `Quot.sound`.

- **Value theorem (`value_iff`).** For any move system satisfying the root, exact-arc-cost and completeness obligations (O0–O2), a bound is achieved if and only if it is at least the width.
- **Engine correctness.** Lean proves the facts behind Theorem E:
  - an empty stack at level B means the table is exactly the B-reachable set;
  - jumping straight to the smallest bucketed cost is safe;
  - the windowed rescan offers exactly the moves not offered before;
  - the first level at which V appears is the width, and an interrupted run's `lb=B` is a valid lower bound.
- **Greedy lemma (`greedy_front`).** For f with diminishing returns, if f(S+v) ≤ f(S), moving v to the front of a completion doesn't raise its bottleneck.
- **Greedy-closure systems.** "Choose any x, then close" is correct for *any* closure rule that never raises f, provided f has diminishing returns and f(∅) = 0 (`greedySystem_value`).
- **Instances:**
  - **kpw is correct (`kpw_value`).** The boundary cost |N⁻(S) ∖ S| has diminishing returns, and Kobayashi's rule 1 and the CMN rule 2 never raise it.
  - **Cutwidth with the rank closure is correct (`kcw_closure_value`).** This rests on the exact cut increment, cut(S+x) + |N(x) ∩ S| = cut(S) + |N(x) ∖ S|.

**Not yet covered:**
- **The C engine itself.** The engine is modelled by its invariants, not by `dsl_engine.h`'s data structures. The randomized checks still cover that gap only empirically.
- **kcw's cover restriction and twin rule.** kcw's vertex-cover normal form (the expensive one) and the twin symmetry rule are not formalised, so `kcw_closure_value` corresponds to `cutwidth(cover=False, twins=False)` only.
- **Other gaps.** The quotient-key decode lemma, pathwidth = vertex separation, and treewidth's simplicial closure are also not done.

`lean/README.md` (attached) lists all of this.

## Why the generated code was slower than kpw, and the fix

It was only slower with `-g`; without it, it was already faster (11.9 s vs 17.1 s over the 61 benchmark graphs).

**Cause.** kpw looks for rule-2 vertices only among the current in-neighbour boundary (nb ∖ U). The generated closure swept every vertex in every pass and tested both rules everywhere. Most vertices failed rule 2 at its first condition, v ∈ nb(S), but were still visited.

I first ruled out the other suspect, recomputing nb when a state is decoded. Storing it with each state instead made things slightly *slower* (9.10 s vs 8.36 s on the five largest graphs), so that option exists but is off by default.

**Fix.** The fix is a general compiler optimisation, not a kpw special case. For a closure rule of the form v ∈ A(S) ∧ …, the compiler now loops over A(S) ∖ T only, and each rule is swept separately until nothing changes. This is valid because the rules are monotone: the closed set is the unique fixpoint whatever the order.

**Results (61 benchmark graphs, all widths agree):**

| mode | DSL | kpw |
|---|---|---|
| without `-g` | 10.4 s | 15.2 s |
| with `-g` | 3.5 s | 5.3 s |

**Individual instances.** A few still lose on their own; for example gnp_n60_d5_s1 without `-g` takes 1.60 s vs 1.44 s. That is not code quality: the two programs search the final level in different orders, so they visit different numbers of states before reaching V (1.75 M vs 1.19 M).

**Can generation always match hand-written code?** Not as a theorem. It works whenever each hand-written trick is either a general rewrite the compiler knows or a data-layer choice you can name. Both slowdowns so far (popcounts on large graphs, the rule-2 sweep) were missing general optimisations. `doc/dsl_codegen_perf.md` (attached) has the details.

## A transfer problem you should know about

While verifying, I found that re-sending a file to your Mac from the same staging location sometimes delivered an older copy. It silently left `doc/dsl_design.md` stale; it's fixed now. I now stage under fresh names and compared checksums for every file touched in the DSL and Lean work, and all match. Only the Lean files and `.gitignore` (I added `lean/.lake/`, since Mathlib's cache there is several GB) were written in place rather than sent.

Nothing has been committed to git. Building from a cold start on your Mac takes 10–25 minutes per Lean file, mostly loading Mathlib for the first time; later builds are fast.

The natural next Lean step is a general symmetry lemma (restricting
choices to one representative per orbit of a group preserving the
costs), with twins as an instance, and then the cover normal form.

