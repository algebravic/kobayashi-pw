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
