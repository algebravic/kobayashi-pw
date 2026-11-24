# Lean formalisation (Lean 4.36.0, Mathlib v4.36.0)

```
cd lean && lake exe cache get && lake build
```

The first build downloads Mathlib's cache, several GB, into `lean/.lake/`, which is git-ignored.

## What is proved

The formalisation is in Lean 4 with Mathlib. There is no `sorry` and no axioms beyond Lean's standard ones (`propext`, `Classical.choice`, `Quot.sound`); `KobayashiPw/Axioms.lean` prints the axioms used by each main theorem.

| file | content |
|---|---|
| `Width.lean` | step costs `w : Finset V → V → ℕ`; the bottleneck `bw` of a list placed after a prefix set; `bw_append`; orderings and completions; `width` as the least feasible bound (`feasible_iff_width_le`). |
| `MoveSystem.lean` | move systems (states with prefix sets, a root block, arcs labelled by blocks, costs); paths with all costs ≤ B; the obligations **O0** (root), **O1** (exact arc cost, new vertices only, set update) and **O2** (completeness). **`value_iff`**: under O0–O2, `Solves M w B ↔ width w ≤ B`. |
| `Engine.lean` | the facts behind Theorem E: `closed_eq_reach` (an empty stack at level B means the table is exactly the B-reachable set); `skip_levels` (jumping to the smallest bucketed cost is safe); `window` (windowed rescan); **`width_eq_of_first`** (the first level at which V is inserted is the width); **`width_ge_of_interrupted`** (the certified `lb=B`); `key_table` (O3). |
| `Greedy.lean` | diminishing returns `DR` (submodularity); **`greedy_front`**: if f(S+v) ≤ f(S), moving v to the front of a completion of S gives bottleneck ≤ max(f S, old bottleneck). `greedy_seq` extends this to closure blocks; `closure_exists` shows every set has one. The **greedy-closure move system** (choose any x ∉ S, then close) satisfies O0–O2 for *any* rule P with P S v ⇒ f(S+v) ≤ f S, whenever f is DR and f ∅ = 0: **`greedySystem_value`**. |
| `Instances.lean` | **vertex separation**: `vsCost` = \|N⁻(S) ∖ S\| is DR (`vsCost_DR`, via the coverage function \|N⁻(S) ∪ S\|), and Kobayashi's rule 1 and CMN's rule 2 never raise it (`vs_greedy`). Hence **`kpw_value`**: kpw's search, with or without `-g`, returns the vertex separation number. **cutwidth**: `cutCost` = Σ_{u∈S} \|N(u) ∖ S\| has increment \|N(x) ∖ S\| − \|N(x) ∩ S\| (`cutCost_insert`), is DR, and the rank rule Δ ≤ 0 never raises it. Hence **`kcw_closure_value`**: the cutwidth search with the rank closure returns the cutwidth. |

## Where the proofs stop

**The C engine is modelled by its invariants, not by its data structures.** `Engine.lean` proves the consequences of the invariants the C engine maintains: a closed table at an empty stack, the window property, and the gap between levels. It does not prove that `dsl_engine.h` maintains those invariants. That gap is the usual one between an algorithm and its implementation. The randomized checks in `check()` and the re-checking of every ordering the programs return cover it empirically.

**Not yet formalised:**
- **kcw's vertex-cover normal form** (`lemma.cover_normal_form`, after Cygan, Lokshtanov, Pilipczuk, Pilipczuk, Saurabh 2014). `kcw_closure_value` covers `cutwidth(cover=False, twins=False)` only.
- **The twin symmetry rule.** The plan is a general "restrict choices to orbit representatives of a group of automorphisms preserving w and the choice set" lemma, with twins as the instance.
- **The quotient key** S ∩ C with decode = closure (`lemma.normal_key`). `key_table` is only the injectivity half.
- **pathwidth = vertex separation** (Kinnersley 1992). `vsCost` is the vertex separation cost; the identification with pathwidth is a separate classical theorem.
- **Treewidth's simplicial closure.** It is not of the form w S v = f(S + v), so `greedySystem_value` does not apply; it needs its own completeness proof.

**Connection to the DSL.** The links between the Lean development and the DSL are by name: the clause lemmas in `src/kobayashi_pw/dsl/lemma.py` (`greedy`, `submod_cut`, `submod_coverage`) are the Lean theorems `greedy_front`/`greedySystem_value`, `cutCost_DR` and `vsCost_DR`. `Problem.report()` does not yet cite the Lean names.
