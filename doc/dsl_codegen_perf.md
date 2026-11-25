# Why generated code was slower than kpw, and what fixed it

## The observation

Milestone 1 compared the DSL's vertex separation with kpw on 61 benchmark graphs. Without `-g`, the generated code was already faster: 11.9 s against 17.1 s in total. With `-g` (CMN rule 2) it was slower: 7.3 s against 6.1 s, and 1.45× slower on the worst instance.

## Diagnosis

I measured two candidate causes on the five largest instances (gnp_n60_*), each switched on and off on its own (one run each, same machine):

| change | rule 1 only | rules 1 + 2 |
|---|---|---|
| maintained nb carried with each state instead of recomputed on decode | 9.10 s vs 8.36 s (*slower*) | 2.47 s vs 2.26 s (*slower*) |
| guard push-down for rule 2 (below) | no effect | the whole gap |

**Recomputing `nb` was not the cause.** Recomputing nb = ⋃_{u∈S} N_in(u) on decode costs O(|S|) word operations. Storing nb in the table per state costs as much in memory traffic as it saves. The `carry` annotation is kept, but its default is off.

**The cause was the domain of the closure scan.**
- **What kpw does.** kpw's `expand` runs rule 1 to its fixpoint, then looks for a single rule-2 vertex *among `nb ∖ U` only*, and repeats.
- **What the generated code did.** It swept all of V ∖ T and evaluated both rule predicates at every vertex in every sweep. The rule-2 predicate is v ∈ nb(S) ∧ |N_in(v) ∖ (S ∪ nb(S))| = 1. Every vertex outside nb(S) failed it at its first conjunct, but only after the loop had visited that vertex.

## The fix: a general compiler optimisation, not a kpw special case

`codegen.guard_split` recognises a closure predicate of the form

    v ∈ A(S) ∧ rest(S, v)        with A not depending on v

and lowers the rule as a scan over A(S) ∖ T, testing only `rest`. This is the usual *filter push-down into the loop domain*. The rules are now swept one at a time, each over its own domain, repeating until no rule fires.

**Why this is correct.** The closure rules are required to be monotone in S, and `check()` tests this. A monotone inflationary operator has a unique least fixpoint, so the closed set does not depend on the order in which rules fire or vertices are visited. Only the replayed order inside a block changes; O1 still holds, because each step satisfies `greedy`.

The same push-down applies to any spec whose closure has such a guard: any rule restricted to the boundary or to a frontier set.

## Results after the fix

Same 61 graphs, same machine, run back to back:

| | DSL | kpw |
|---|---|---|
| rule 1 | 10.4 s | 15.2 s |
| rules 1 + 2 (`-g`) | **3.5 s** | 5.3 s |

Every width agrees. The generated code is now faster in total in both modes.

On individual instances the DSL is occasionally slower: gnp_n60_d5_s1 without `-g` takes 1.60 s against 1.44 s. That is *not* code quality. The two programs search the final level in different orders. kpw pushes (S, nb, x) triples and closes a child only when it pops it. The engine closes and inserts children as it generates them. When V is found partway through the last level, the number of states visited before it depends on that order: 1.75 M against 1.19 M here. Neither order is better in general.

## Why the generated code is often *faster* than the hand-written programs

- **Window rescan.** On a rescan the engine offers only the moves with cost in (lo, B]. kcw rescanned every move (lookups that are bound to hit), and kpw pushes a 24-byte triple for every candidate pair.
- **Specialisation.** Constants such as the number of words W are compile-time, so the word loops unroll. kcw's loops run over a run-time `nw`.
- **Hoisting.** Quantities that depend only on S, such as f(S) and maintained sets, are computed once per expansion.

## Can generation always match hand-written code?

There is no theorem here; it is an engineering claim with a clear boundary.

**What is covered.** Generated code matches a hand-written program whenever every optimisation in the hand-written program is either:
1. a generic rewrite or lowering rule that the compiler knows (guard push-down, finite differencing of maintained quantities, hoisting, fusion of comprehensions), or
2. a data-layer choice that can be named (counter families with undo, carried sets, packed keys, rescan policy).

**What is not covered.** Tricks that are neither, such as kpw2's Item masks or a hand-unrolled closed-form cost, need either a new rule in the compiler or the `P.native(...)` escape hatch, which comes with a debug-mode equivalence check.

**The record so far.** Each slowdown found so far (popcounts at large W, the rule-2 sweep) was a missing *generic* optimisation of kind 1 or 2. None needed a problem-specific hack.

## Secondary costs: the generated E2 against kopt (2026-11-24)

This is the measurement that decision 3 of `doc/dsl_secondary_design.md` asks for before the DSL path becomes the default in hamiltonian.

**Setup.**
- 2-core Linux container, both sides single-threaded (`kpw2 -t 1`), median of 3 runs.
- Square-sum graphs G_n, with the hampath V7 cost and the log-linear work model (the fitted coefficients from hamiltonian's `work_model.json`).
- In every case the DSL and kopt return **the same ordering**, with costs equal to about 1e-15 relative.

| n | cost | `kpw -c` | kopt | DSL search | DSL E2, dead states (pruning) | DSL E2, live nodes (DP) | DP: DSL / kopt | total: DSL / (kpw + kopt) |
|---|---|---|---|---|---|---|---|---|
| 57 | v7 | 0.11 | 0.06 | 0.04 | 0.04 (85 701 of 99 463) | 0.04 | 0.69 | 0.71 |
| 57 | work | 0.11 | 0.26 | 0.04 | 0.05 | 0.25 | 0.94 | 0.91 |
| 61 | v7 | 3.50 | 1.84 | 1.01 | 1.99 (1 401 441 of 1 665 113) | 1.54 | 0.84 | 0.85 |
| 61 | work | 3.50 | 12.16 | 1.15 | 2.54 | 12.36 | 1.02 | 1.02 |
| 65 | v7 | 3.03 | 1.22 | 0.69 | 1.20 (780 356 of 893 268) | 0.91 | 0.75 | 0.66 |
| 65 | work | 3.03 | 4.07 | 0.73 | 1.59 | 3.55 | 0.87 | 0.83 |
| 70 | v7 | 2.87 | 1.24 | 0.75 | 1.30 (670 118 of 780 578) | 0.99 | 0.80 | 0.74 |
| 70 | work | 2.87 | 3.94 | 0.66 | 1.30 | 3.43 | 0.87 | 0.79 |
| 75 | v7 | 4.62 | 1.70 | 1.17 | 2.14 (1 098 401 of 1 230 801) | 1.29 | 0.76 | 0.73 |
| 75 | work | 4.62 | 9.47 | 1.32 | 2.38 | 8.68 | 0.92 | 0.88 |

(Seconds.)

**Result.** The generated E2 is at least as fast as kopt on the optimisation proper (0.69–1.02×). Counting everything — search, pruning and optimisation, against `kpw -c` plus kopt — it is 0.66–1.02× as long. Neither number reaches the 1.3× threshold, so on this evidence nothing blocks making the DSL path the default.

### How the first comparison misled, and what it taught

The first measurement compared the DSL's whole E2 phase with kopt alone, and showed the DSL 1.05–1.8× *slower*. The cause was where the pruning work sits on each side:
- kopt reads a DAG that `kpw -c` has already pruned to the co-reachable states. At n = 61 that is 263 672 nodes.
- E2 starts from engine E's complete table (1 665 113 states at n = 61) and prunes it in passing: a state whose moves reach no labelled state stays empty. Enumerating the arcs of the 1.4 M dead states is the pruning pass, which kpw charges to `-c`.

The number of dead states equals kpw's `sets − dag` exactly. Separating the two (the `dead_nodes` and `prune_seconds` statistics of `dsl_dagopt`) gives the table above.

### A codegen change made on a wrong hypothesis, kept

Before the attribution was understood, the generated step functions were changed to read the frontier's neighbour unions ⋃_{u ∉ T} F(u) from prefix unions computed once per arc in `sec_block`. Previously each step computed a fresh union over the whole complement; the new version does one row OR per block vertex, which is what kopt does.

This is the finite differencing of Layer D, applied in the direction the block DP needs: the σ-side set grows while the τ prefix grows. It had **no measurable effect** at these sizes, within noise, and it is kept because it is correct, tested and asymptotically cheaper. The lesson is the one in the section above: measure the split before changing the generated code.

### What would still separate the two

- **Search.** The complete-mode search of engine E is already 3–4× faster than `kpw -c`. That is the partitioned table and window rescan (§ above) plus probe-before-closure.
- **Arc enumeration in E2** recomputes each move's closure, as kopt does. A Layer-D option to store arcs during the complete search would trade memory for this time; it is not needed at these sizes.
- **Label folding** is the same loop in both, and dominates for the work model.
