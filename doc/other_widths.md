# Do the kpw ideas carry over to cutwidth, treewidth and bandwidth?

## Summary

| width | one-pass bottleneck search | k-independent greedy closure | small-state bound | verdict |
|---|---|---|---|---|
| **cutwidth** | yes | yes; the same lemma as for pathwidth (below) | 2^τ, with Cygan et al.'s normal form | **carries over completely.** Prototype: exact cw(G₆₀) = 22 in 6 min in Python |
| **treewidth** (elimination orderings) | yes | only weak (simplicial vertices) | known 3^τ (Chapelle et al.), by a different method | **partly.** The state of the art, Tamaki's PID-BT, is a much stronger DP; the one-pass idea would give it only a constant factor |
| **bandwidth** | no | no | none | **does not carry over.** The cost depends on positions, not on prefix sets |
| linear widths of any submodular connectivity function (vertex separation, cutwidth, directed versions, linear rank-width, …) | yes | yes (lemma below) | problem-specific | **the natural home of the method** |

Three things were checked here:
- **A unifying lemma, which appears to be new as stated.** Kobayashi's subsumption rule and the second greedy rule of Coudert–Mazauric–Nisse are both instances of one statement: for a submodular prefix cost, a vertex whose addition does not increase the cost can be added at once. The same statement gives the cutwidth rule.
- **A Python prototype**, `src/kobayashi_pw/widths.py`, with one search engine and three plug-ins. It was checked against brute-force DPs on 560 random and bipartite graphs with n ≤ 13, and the tests in `tests/test_widths.py` repeat the check on 390 more.
- **Measurements** on the square-sum graphs G_n.

## 1. The three ingredients, and what each needs

1. **The state is the set of vertices placed so far.** This needs the cost of the next step to depend only on (S, v). That holds for vertex separation, cutwidth (|E(S, V∖S)|) and elimination-ordering treewidth (|Q(S, v)|). It fails for bandwidth.
2. **One pass instead of a search over k.** This needs a min–max objective with nonnegative step costs that do not depend on k. Then the value is a minimum-bottleneck path, and a Dijkstra-type search settles only states of bottleneck ≤ OPT. It applies to all three set-based problems above, and to AND/OR versions such as Tamaki's PID through Knuth's generalisation of Dijkstra (superior functions).
3. **A greedy closure that does not depend on k.** It removes most states, and for vertex separation it gives the 3^τ bound. It needs an exchange argument that does not involve k. Section 2 gives a general one.

## 2. The greedy lemma (proved, and checked by brute force)

**Lemma.** Let f be submodular on subsets of V, and consider orderings minimising max_i f(S_i) over prefixes S_i. Suppose S is a prefix of an ordering of value M, with f(S) ≤ M, and v ∉ S satisfies f(S ∪ {v}) ≤ f(S). Then S ∪ {v} is a prefix of an ordering of value ≤ M.

**Proof.** Take the completion a₁, …, a_m, v, … of S, and move v to the front. Write A_j = {a₁, …, a_j}. Every new prefix S ∪ {v} ∪ A_j, for 0 ≤ j ≤ m, satisfies

f(S∪A_j∪v) = f(S∪A_j) + Δ(S∪A_j, v) ≤ f(S∪A_j) + Δ(S, v) ≤ f(S∪A_j) ≤ M,

using submodularity (Δ(X, v) = f(X∪v) − f(X) is antitone in X). Later prefixes are unchanged. ∎

**Applications.**
- **Vertex separation.** f(S) = |N⁻(S)| is submodular, and Δ(S, v) = −[v ∈ N(S)] + |N⁻(v) ∖ (S ∪ N(S))|. So **Δ ≤ 0 holds exactly when Kobayashi's rule 1 or Coudert–Mazauric–Nisse's rule 2 holds.** Both published rules are this one lemma. The identity was checked on 73,080 (S, v) pairs, and `tests/test_widths.py` checks it again.
- **Cutwidth.** f(S) = |E(S, V∖S)| is submodular, and Δ(S, v) = deg v − 2|N(v) ∩ S|, which is the "rank" of Cygan et al. Their Lemma 1, moving a vertex earlier to a position where its rank ≤ 0, is this lemma.
- **Linear rank-width.** The cut-rank function is symmetric and submodular, so the same closure applies. This was not tested here.

The brute-force checks used 200 random graphs and digraphs with n ≤ 9. Submodularity, and safety in the sense of the lemma, held in every case: 64,945 checked additions for vertex separation and 47,850 for cutwidth.

**Delaying is subtler than moving earlier.** One might expect the mirror statement: a vertex placed while its rank is positive can be delayed until its rank is ≤ 0. It is false. The prefix just before the new position is not dominated. On the path 2–1–0–3, delaying vertex 2 until after vertex 1 makes the prefix {1} cost 2 instead of 1. The correct normal form (Cygan et al., Lemma 2) keeps odd-degree vertices outside the cover at rank ±1, which is what section 3 implements. My first prototype used the naive version and was one too high on 75 of 400 test graphs.

## 3. Cutwidth

**What the algorithm does.** It is the same one-pass bucketed search as kpw, with three changes:
- **Cost:** f(S) = cut size, and the cost of an arc is f(S ∪ {x}).
- **Closure:** add any vertex with rank ≤ 0, repeatedly. This is safe by the lemma, and the closure never raises the cost of its arc.
- **Optional cover restriction.** Given any vertex cover C, only vertices of C are chosen voluntarily. Before a cover vertex x is placed, an optimal number i of the vertices in Y(S, x) are placed first. Y(S, x) is the set of odd-degree vertices outside the cover that are adjacent to x and have rank +1 at S. The cost of the arc is f(S) + min over 0 ≤ i ≤ |Y| of max(i, Δ(S, x) − i). The rest of Y then has rank −1 and enters through the closure. This follows the normal form of Cygan, Lokshtanov, Pilipczuk, Pilipczuk and Saurabh (*On cutwidth parameterized by vertex cover*, Algorithmica 68 (2014) 940–953).

**State bound (proof sketch).** A vertex outside the cover has all its neighbours in C, so its rank depends only on S ∩ C, and monotonically. Every stored state therefore satisfies S ∖ C = {u : rank(S ∩ C, u) ≤ 0}. So there are at most 2^|C| states, and the running time is O\*(2^τ), the bound of Cygan et al. The one-pass search settles far fewer states than that, because it never goes above OPT.

**Correctness checks.**
- `cutwidth` agrees with a brute-force 2ⁿ DP on 400 random graphs with n ≤ 10, and on 160 more graphs with n = 9–13, half of them bipartite. That is 1,520 runs over the three cutwidth variants, with 0 disagreements.
- Every run's ordering is re-checked: its width is recomputed and equals the reported value.

**Square-sum graphs G_n** (Python prototype; the "settled" column counts states taken from the queue with their final value):

| n | τ | pw | cw | closure + cover: settled (time) | closure only | no rules |
|---|---|---|---|---|---|---|
| 25 | 13 | 4 | 6 | 141 (0.0 s) | 372 | 7,871 |
| 30 | 16 | 5 | 6 | 191 (0.0 s) | 785 | 3,589 |
| 35 | 19 | 5 | 9 | 1,292 (0.2 s) | 6,519 | 31,306 |
| 40 | 21 | 7 | 11 | 3,465 (0.7 s) | 29,085 | 199,503 |
| 45 | 25 | 9 | 13 | 12,065 (2.8 s) | | |
| 50 | 29 | 9 | 14 | 22,345 (6.8 s) | | |
| 55 | 32 | 10 | 17 | 94,068 (37 s) | | |
| 57 | 33 | 11 | 20 | 393,746 (168 s) | | |
| 60 | 34 | 13 | 22 | 771,807 (359 s) | | |

The cutwidths for n ≥ 45 rest on the proof plus the small-graph tests. Each is attained by a printed ordering, and each is consistent with pw ≤ cw.

**Next step.** Porting this to C is easy: kpw2 already has every data structure needed. Only the cost function, the rank closure and the cover-restricted arcs change. Expect roughly the same factor of 100 over Python as for pathwidth.

## 4. Treewidth

- **What carries over.** Treewidth is the minimum over elimination orderings of max_i |Q(S_{i−1}, v_i)|. Here Q(S, v) is the set of vertices outside S ∪ {v} that are reachable from v through S (Bodlaender et al. 2012). The cost depends only on (S, v), so the one-pass bottleneck search applies unchanged; the prototype `treewidth()` agrees with brute force.
- **Safe closure.** Eliminating simplicial vertices is safe: their degree is at most the treewidth of the remaining elimination graph. Unlike in vertex separation, this step can raise the arc's cost, so the arc cost becomes the maximum over the block. That is still a valid bottleneck path.
- **What does not carry over.** There is no submodular prefix function, so the general lemma does not apply. The simplicial rule is weak: on G₂₀ it reduced the settled states only from 61,963 to 20,788 (while slowing the Python, since the test is expensive). The elimination-ordering DP itself is far weaker than the dynamic program over minimal separators and potential maximal cliques. Tamaki's positive-instance-driven version of that DP generates positive subproblems only, and solved all 100 public instances of the PACE 2017 exact track ([ESA 2017](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.ESA.2017.68)).
- **The one idea that does transfer to PID** is replacing the outer loop over k by a single bottleneck pass. PID combines blocks (an AND/OR structure), so this needs Knuth's superior-function generalisation of Dijkstra rather than plain Dijkstra. The gain is at most the cost of the runs below the optimum. I expect a modest constant factor, since the run at the optimal k usually dominates; this was not measured.
- **Vertex-cover parameterisation.** O\*(3^τ) for treewidth is due to Chapelle, Liedloff, Todinca and Villanger (WADS 2013).
- **Recommendation.** Use an existing PID solver rather than building one.

## 5. Bandwidth

**Why it does not fit.** The cost of an ordering is max over edges of |pos u − pos v|. That depends on the positions inside the prefix, not on the prefix set. Two prefixes with the same set but different orders have different futures, because a placed vertex u forces its unplaced neighbours to land by position pos(u) + b. The classical exact DP (Saxe; Gurari–Sudborough) therefore keeps the last b placed vertices in order, so the state space itself depends on b. With no k-independent state space there is no bottleneck path. For the same reason there is no exchange lemma like the one in section 2: moving a vertex shifts the positions of everything it passes.

**What can be used.**
- **pw ≤ bw.** Any layout of bandwidth b has prefix boundaries of size ≤ b, so kpw gives a strong lower bound quickly; for G₆₀ it is 13. Cutwidth gives a weaker one, since cw ≤ b(b+1)/2.
- **Exact methods.**
  - SAT/ILP with an increasing b, starting from pw. One formulation has O(n²) variables and O(n·m) constraints / O(n³) clauses for bandwidth ≤ k ([Biedl et al., arXiv:1308.6778](https://arxiv.org/pdf/1308.6778)).
  - Problem-specific branch and bound, such as [Martí, Campos and Piñana](https://www.uv.es/~rmarti/paper/docs/bmp3.pdf) and [T. K. Vo's thesis](https://archiv.ub.uni-heidelberg.de/volltextserver/12580/1/KhoaVo_Dissertation.pdf).
  - The best exponential-time bounds: [Cygan and Pilipczuk](https://arxiv.org/pdf/0902.1661) give O(4.83ⁿ), improved to [O(4.383ⁿ)](https://arxiv.org/pdf/1004.5012).

## 6. Suggested next steps

1. **A C cutwidth solver**, `kcw`, inside kpw2, with `-c` (complete DAG) and the secondary-cost machinery. The orders module works unchanged on any step-local cost.
2. **Linear rank-width.** The same engine with cut-rank over GF(2), which is a few word operations per cut for n ≤ 128. No small-state bound is known for it here, so it is purely empirical.
3. **A bandwidth lower bound.** Use kpw's pw to seed an incremental SAT search.

## Files

- `src/kobayashi_pw/widths.py`: the engine and the plug-ins `vertex_separation`, `cutwidth` (with `cover=None | "auto" | mask`), `treewidth`, brute-force references, and width checkers.
- `tests/test_widths.py`: brute-force agreement for all three widths, plus the rule-1 ∪ rule-2 identity.
