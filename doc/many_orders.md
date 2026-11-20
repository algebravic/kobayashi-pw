# Using the kpw table to get many pathwidth-optimal orderings

## Short answer

Yes, with three qualifications:

1. The table kpw builds today is incomplete.
2. kpw's orderings must be **reversed** to match your DP's frontier convention.
3. The table represents a large but strict **subfamily** of the optimal orderings.

More importantly, you probably don't need to generate orderings and then search over them. Your step costs are local to a single step, so the secondary cost can be minimized **exactly** by a DP over the table.

## 1. Complete level pw, then prune

kpw stops at the first moment it reaches V. At that point, level pw holds only a handful of sets. To capture every optimal path it must:

- finish level pw, i.e. keep going until the work stack is empty instead of stopping at V. This gives exactly R_pw = {S relevant : b(S) ≤ pw}, the same family as Kobayashi's Algorithm 1 at k = pw;
- then do one backward pass that keeps only the sets from which V is still reachable at level pw.

Every path from ∅\* to V in the resulting DAG is a pw-optimal ordering. Arcs don't need to be stored: the arcs out of S are the x with |N(S∪{x})| ≤ pw, and each target (S∪{x})\* is already in the table.

Measured on the square-sum graphs G_n (Python):

| n | pw | kpw today | R_pw | sets on an optimal path | orderings represented | build time |
|---|---|---|---|---|---|---|
| 57 | 11 | 34 445 | 99 463 | 13 762 | 1.6 × 10²⁶ | 7 s |
| 58 | 12 | 96 416 | 278 855 | 45 056 | 3.6 × 10²⁸ | 21 s |
| 59 | 13 | 249 962 | 762 813 | 151 041 | 2.0 × 10³¹ | 65 s |
| 61 | 14 | 596 416 | 1 665 113 | 263 672 | 2.2 × 10³³ | 155 s |

The ordering counts treat each expansion block as having one canonical order, so they undercount. In C the build times would be well under a second.

## 2. Convention: reverse the order

- **kpw** measures the boundary *outside* the prefix: |N(S_i)|.
- **Your DP** (`frontier_width`, `_max_fw_ok`) counts the prefix vertices that still have a later neighbour: Kinnersley's L_i.

For undirected graphs, L_i(τ) = N(V(τᴿ) prefix of length n − i). So a kpw ordering σ becomes your ordering τ = σᴿ. Each kpw arc S → (S∪{x})\* becomes, in your direction, a block that takes the prefix from V∖(S∪{x})\* to V∖S, adding the expansion vertices in reverse order and then x. Every intermediate prefix stays within width pw.

Your MaxSAT orderings are already in your convention.

## 3. Which orderings the DAG contains

In your direction, the boundaries between blocks are exactly the prefixes T with the following property: **every introduced vertex has at least one neighbour that has already been eliminated.** This follows because S = V∖T is relevant iff no x ∈ T satisfies N(x) ⊆ (V∖T) ∪ L(T). Inside a block anything is allowed.

Orderings that violate this at every possible cut point are excluded. Two experiments measure what that costs.

**Exact optimum of your V2 cost.** The cost is Σ 2^nb (f/pw)² + 0.001 Σ f, with your exact definitions of nb and f. I minimized it exactly over (a) **all** pw-optimal orderings, by DP over every feasible prefix set, and (b) the relevant-set DAG.

| n | pw | optimum over all | optimum over relevant DAG | ratio |
|---|---|---|---|---|
| 25 | 4 | 18.629 | 18.691 | 1.003 |
| 30 | 5 | 21.775 | 22.135 | 1.017 |
| 35 | 5 | 45.386 | 45.706 | 1.007 |

The restriction cost 0.3–1.7% on these graphs. This is empirical, for small n only; the n = 40 run of the full search timed out in Python.

**Size of the full family.** It is the set of all prefix sets of pw-optimal orderings, with no relevant-set pruning. I counted it in C:

| n | pw | feasible prefix sets | largest single layer |
|---|---|---|---|
| 50 | 9 | 5.36 M | 1.43 M |
| 55 | 10 | 8.97 M | 2.26 M |
| 57 | 11 | 51.7 M | 12.8 M |
| 58 | 12 | out of memory on a 7 GB machine | |

An exact DP over all optimal orderings is therefore realistic up to about n = 57–58 on your 16 GB machine. Beyond that, use the relevant DAG.

## 4. Optimizing the secondary cost exactly over the DAG

Every feature your cost models use (in `ham_ordering._dp_cost` and `sa_cost._step_features`) is a function of the prefix T before the step and the vertex v added:

- the frontier L(T∪{v});
- `n_back`, counting only back-edges to vertices that remain in the frontier;
- `e_bag`;
- the components of G[frontier];
- `n_elim`;
- the step index |T|.

Hence:

- **Costs that add up step by step** (V1, V2, the linear model): this is a shortest path in a DAG, exact, and linear in the number of arcs.
- **Compounding proxy costs** (V5, V6, V7): `cost += p·e(T,v)`, then `p ← max(p·e·κ(T,v), 1)`. The cost-to-go J(T, p) is nondecreasing in p. This follows by induction from J(T,p) = min_v [p·e + J(T′, max(p·e·κ, 1))]. So a forward DP that keeps, for each set, the Pareto front of (cost so far, p) labels is **exact**. Without the clamp it collapses to a single label: J = p·g(T), with g(T) = min_v e·(1 + κ·g(T′)).
- **ConvMLP** (features over a window of consecutive steps): this is not local to one step. Use the DAG optimum of a step-local cost as the SA starting point, or rerank the k best DAG paths with the MLP.

Simulated annealing then becomes optional polishing, rather than the only tool for searching an astronomically large space.

## 5. A correction to hampath_paper_full.tex

In the treewidth section, the paper states pw(G₅₀) = 10 and pw(G₅₅) = 11. Both kpw and your own MaxSAT model give **9 and 10**. I re-ran your `vertex_separation.py` on both graphs, and the returned orderings have Kinnersley width 9 and 10 respectively. So the claimed gaps "tw ≤ 9 < pw = 10" and "tw ≤ 10 < pw = 11" disappear: in both cases htd's width equals pw. The other values in the paper (57 → 11, 59 → 13, 61 → 14) agree with kpw.

## Proposed implementation (not yet done)

I'd add the following to kpw (C), with a matching Python reference:

1. a `--complete` mode that finishes level pw and prunes to the sets that can still reach V;
2. a pluggable step cost c(T, v) and multiplier κ(T, v), evaluated in your DP's direction, with a block-cost routine;
3. two exact solvers: a shortest path for step-additive costs, and the Pareto-label DP for proxy costs, with the clamp included;
4. output of the optimal τ, plus optionally the k best τ for reranking or SA.

Scripts used for the numbers above: `census.py`, `secopt.py`, `fullcount.c`.
