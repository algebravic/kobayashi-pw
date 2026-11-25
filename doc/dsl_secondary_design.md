# Secondary-cost optimisation in the DSL, and compile-on-first-use (design, before implementation)

This is an addendum to `doc/dsl_design.md`, and nothing in it has been implemented.

- **Part A** extends the DSL so that the exact optimisation over the DAG of optimal orderings (today `orders.optimize` and `src/C/kopt.c`) can be written as a spec. Secondary costs such as V2, V7 and the hampath work model then become a few lines of Python, and are traced, compiled and cached like the existing specs.
- **Part B** makes `kpw`, `kpw2`, `kopt` and the DSL engine headers work from a non-editable install (a git or PyPI dependency) by compiling them on first use.

Part B is small and independent of Part A, so I propose doing it first (§B7).

---

# Part A. Secondary costs over the move graph

## A1. What is computed

Let 𝓜 be a move system (`dsl_design.md` §1) with value B\* = width(V, w). The **optimal move graph** Γ is defined as follows:

- **nodes:** the normal states s with bottleneck(s₀ → s) ≤ B\* from which V is reachable through arcs of cost ≤ B\*;
- **arcs:** the moves s → apply(s, m) with cost(s, m) ≤ B\*;
- each arc carries its **block**, the full vertex sequence that `apply` adds (the prefix, then x, then the closure, in closure order).

Every path s₀ → V spells an ordering σ = blocks(∅) · block₁ · … · block_r of width B\*. For vertex separation this is the DAG that `kpw -c` writes.

**The secondary objective** is defined on the steps of the **reversed** ordering τ = reverse(σ), which is the direction of a left-to-right frontier DP. Step t places τ_t after the prefix T_{t−1} = {τ₁, …, τ_{t−1}}. A *step model* gives three reals,

    (a_t, e_t, k_t) = step(T_{t−1}, τ_t),

and the cost of the ordering is

    cost(τ) = Σ_t ( a_t + p_{t−1} · e_t ),      p₀ = 1,   p_t = max(p_{t−1} · e_t · k_t, 1).

This is exactly the recursion of `orders.evaluate`:
- additive costs (V2) have e ≡ 0, so p ≡ 1;
- V7 has e = (proxy growth factor), k = (elimination compression);
- the work model has a = 0, e = 2^{nb}, and k = exp(β·x)/2^{nb}, so that p_t is the predicted state count and the cost is the predicted Σ s_t·2^{nb_t}.

The task is **min over paths π of Γ of cost(τ(π))**, with the optimal path, and optionally the k best paths when the cost is additive.

A forward direction, with features of S rather than of V∖S, is the special case `direction="forward"`. Nothing below depends on the choice except where the blocks are reversed.

## A2. Theorem E2 (exactness of Pareto labels)

**Engine E2.** Process the nodes of Γ in decreasing |s|, starting at V with the single label (cost 0, p 1); this is the empty τ-prefix. For a node s, each arc s → t with block β and each label (c, p) of t gives a candidate label. The candidate is obtained by folding the steps of reverse(β) through the recursion, starting from (c, p). Keep the Pareto front of the candidates in (cost, p), and finish by folding the root block. Each label stores a back-pointer.

**Theorem E2.**
1. If e_t ≥ 0 and e_t·k_t ≥ 0 at every step of every arc, then E2 returns min_π cost(τ(π)), and the back-pointers spell a minimising path.
2. If additionally e ≡ 0, every front has one label, and keeping the k cheapest labels per node gives the k best paths exactly.
3. If at most L labels are kept per node (the cheapest L), the result is the cost of a feasible path, an upper bound on the optimum. The result is flagged inexact whenever a nondominated label was dropped.

**Proof sketch for 1.** Let J(s, p) be the least cost-to-go from node s with carried value p. A step contributes a + p·e and passes on max(p·e·k, 1). Since a does not depend on p, and e ≥ 0 and e·k ≥ 0, both quantities are nondecreasing in p. By induction on the number of remaining steps, J(s, ·) is nondecreasing. So a label (c, p) dominated by (c′, p′), with c′ ≤ c and p′ ≤ p, cannot lead to a better completion, and dropping it is safe. Items 2 and 3 are immediate.

This is the theorem that `orders.optimize` and `kopt` rely on. It is proved in `doc/pathwidth.tex`. In the DSL it becomes a library lemma (§A4), like Theorem E.

## A3. Layer P: the `secondary` clause

```python
P.secondary(step=lambda T, v: (a, e, k),       # reals; T = placed prefix, v = vertex placed
            direction="reverse",                 # τ = reverse(σ); "forward" also allowed
            by=lemma.pareto_monotone)            # or lemma.additive (then e must be 0)
P.param("beta", 11)                              # runtime real parameters (§A6)
```

- **The fold along a block is derived, not written.** This is the analogue of the derived arc cost (the maximum of w along the block) for the primary cost.
- **Several secondary clauses can be declared on one spec, under names** (`P.secondary(..., name="work")`). `solve(..., secondary="work")` selects one, so V2, V7 and the work model can share the move system and the DAG.
- **Block order.** The primary search never depends on the order of closure additions inside a block, because closure steps never raise the cost and the closed set does not depend on the order. Secondary costs do depend on it. So when a `secondary` clause is present, **the closure is the sweep**, as in eager mode, in `core.expand` and in `kopt`. The compiled neighbour-worklist closure stays available for the primary search; the blocks for the secondary DP are regenerated with the sweep. This is obligation **S1** (§A5).

## A4. Lemma library: two new rows

| lemma | hypothesis | conclusion |
|---|---|---|
| `additive` | e is the constant 0 (checked syntactically) | p ≡ 1. E2 keeps one label per node, and `k_best(k)` is exact. |
| `pareto_monotone` | e ≥ 0 and e·k ≥ 0 at every step | Theorem E2.1: Pareto labels give the exact optimum. |

**Checking `pareto_monotone`.** A sign analysis on the IR covers the cases we use:
- exp(·) > 0, powers of positive constants > 0, card(·) ≥ 0;
- products, quotients and sums of nonnegatives are nonnegative;
- max(x, c) with c ≥ 0 is nonnegative.

V2, V7 and the work model all pass this analysis. If the analysis fails, the hypothesis becomes a stated assumption in `report()`, debug builds assert it at every step, and `check()` tests it on random graphs.

## A5. Obligations

| | obligation | how it is met |
|---|---|---|
| S1 | The blocks are a deterministic function of (s, label), in sweep order. | Generated closure in sweep mode; checked in eager mode against `apply`. |
| S2 | The fold over a path equals `evaluate` on the full ordering τ(π). | By construction: one step function is used both for the fold and for `evaluate`. `check()` compares them on random paths. |
| S3 | The hypothesis of the lemma attached to the clause. | §A4. |
| S4 | Γ is exactly the optimal move graph: every node has bottleneck ≤ B\* and is co-reachable to V through arcs of cost ≤ B\*. | Engine E's level B\* is completed, and a backward pass prunes (§A7.1). In eager mode this is checked against brute force for n ≤ 10. |

## A6. IR additions

| addition | meaning | lowering |
|---|---|---|
| type `REAL` | real scalars | `double` in C, `float` in eager mode |
| `real(i)` | Int → Real | cast |
| `+ − * /` on Real, mixed with Int | arithmetic | as is |
| `rexp(x)`, `rlog(x)`, `rpow(x, y)` | elementary functions | `exp`, `log`, `pow` (needs `-lm`) |
| `rmin`, `rmax`, `where` on Real | | as is |
| `table(name, i)` | a constant real array indexed by `min(i, len−1)` (e.g. log Bell) | a static array in the generated file |
| `comp_sum(A, g)` | Σ over the connected components C of G[A] of g(\|C\|), with g: Int → Real | BFS over the bitset A, word loops, as in `kopt.c` |
| `param(name, i)` | the i-th entry of a runtime real vector | a field of `Params`, so refits do not recompile |

**Tracing.** Python floats lift to Real constants. The tracer's rule that a symbolic value may not be converted to bool applies to Real as well.

**Why parameters and not constants.** If the coefficients of the work model were traced as constants, every refit of `work_model.json` would produce a new cache key and a new compilation. As runtime parameters they leave the generated code unchanged; the model's *form* is what is compiled.

## A7. Engine and Layer D

### A7.1 Producing the DAG (milestone-2 item `output dag`)

Engine E gets a **complete** mode:
- at level B\*, it keeps processing the stack until it is empty, instead of returning at V;
- every state with bottleneck ≤ B\* is then in the table, which is the family of `kpw -c`.

A backward pass then marks the co-reachable states. It visits the states in decreasing |s|, enumerates each state's moves of cost ≤ B\*, and looks up apply(s, m) in the table. The result is a list of node keys in decreasing size, which is exactly the content of a `KPWDAG3` file.

Layer D options:
- `output dag` returns it in memory;
- `output dag(file=...)` writes `KPWDAG3`;
- a `KPWDAG3` file can also be the input of E2, so `kpw2 -c` output and cached DAGs keep working.

**Keys other than the identity** (cutwidth with its cover) work unchanged, because nodes are keys and blocks come from `apply`. Their blocks include the decode closure.

### A7.2 E2 (`src/C/dsl_dagopt.h`, fixed and hand-written, like `dsl_engine.h`)

- **Nodes.** The node array in decreasing size, and a hash table from key to node index; this can reuse E's table.
- **Arcs.** Arcs are recomputed per node by the generated `for_each_move` with cost ≤ B\* followed by `apply` in sweep mode. They are never stored; this is what `kopt` does, and it keeps memory proportional to the nodes and labels.
- **Steps.** Per arc, the generated `block_steps(s, block) → (a, e, k)[]` is evaluated once and then folded over every label of the target.
- **Labels.** A label is `{double cost, p; uint32 prev; int16 x}`, 24 bytes. All fronts are kept in one pool for the traceback, with per-node offset and count.
- **Ties** are broken by insertion order, which equals Python's stable sort. The eager E2 and the compiled E2 therefore return the same path, and both agree with `orders.optimize` and `kopt` when the blocks are the same.
- **Layer D annotations:**
  - `output pareto(secondary=name, max_labels=L)`;
  - `output k_best(k)`, for `additive` only;
  - `output sample(k)`, uniform over paths, using path counts in doubles.

### A7.3 Generated code

`ops.h` gains:
- `static inline void step_eval(const u64 *T, int v, const u64 *F_before, ..., double out[3])`;
- `block_steps`, the loop over the reversed block. It maintains T and the frontier as it goes, exactly as `kopt.c::block_steps` does, so a block costs O(|block| · W) word operations plus the component BFS when `comp_sum` is used.

Set expressions in the step reuse the existing lowering. For example, the frontier F(T) = T ∩ ⋃_{u ∉ T} N(u) is a `bigunion` over the complement, and is lowered with the incremental union the D layer already knows.

## A8. The hampath models as specs

```python
from kobayashi_pw.dsl import specs, lemma
from kobayashi_pw.dsl.ir import (N, bigunion, card, comp_sum, isum, param, real, rexp,
                                 rpow, rmax, single, table, where, FULL)

LOGBELL = [...]                                       # log Bell(0..20), a table constant

def frontier(T):                      return T & bigunion(FULL - T, N)

def hampath_steps(T, v):
    """Features of one τ-step, as orders.tau_block_features."""
    T1 = T | single(v)
    F0, F1 = frontier(T), frontier(T1)
    fw, fw0 = card(F1), card(F0)
    nb      = card(N(v) & T & F1)
    nelim   = card(F0 - F1) + where(card(N(v)) == 0, 1, 0)
    ebag    = isum(F1, lambda u: card(N(u) & F1)) // 2
    lbc     = comp_sum(F1, lambda s: table("logbell", s))
    return fw, fw0, nb, nelim, ebag, lbc

def with_hampath_costs(P, n):
    def v2(T, v):
        fw, _, nb, *_ = hampath_steps(T, v)
        q = real(fw) / real(P.width_param())          # pw is a runtime parameter of E2
        return rpow(2.0, nb) * q * q + 0.001 * fw, 0.0, 0.0

    def v7(T, v):
        fw, _, nb, nelim, ebag, lbc = hampath_steps(T, v)
        q = real(fw) / real(P.width_param())
        corr = rexp(0.5 * (rmax(lbc, 0.0) - rmax(table("logbell", fw), 0.0)))
        dens = where(fw > 0, 1.0 + param("alpha", 0) * real(ebag) / real(fw), 1.0)
        e = rpow(param("base", 0), nb) * q * q * corr * dens
        return 0.001 * fw, e, rmax(rpow(0.5, nelim), 0.01)

    def work(T, v):
        fw, fw0, nb, nelim, ebag, lbc = hampath_steps(T, v)
        x = [1.0, nb, nelim, fw, fw0, ebag, lbc, nb * fw, nelim * fw0, nb * nb,
             real(card(T)) / (n - 1)]
        g = sum(param("beta", i) * x[i] for i in range(11))
        return 0.0, rpow(2.0, nb), rexp(g) / rpow(2.0, nb)

    P.secondary(v2, name="v2", by=lemma.additive)
    P.secondary(v7, name="v7", by=lemma.pareto_monotone)
    P.secondary(work, name="work", by=lemma.pareto_monotone)
    return P

P = with_hampath_costs(specs.vertex_separation(), n)
sol = P.solve(G, output="pareto", secondary="work", params={"beta": beta})
sol.width, sol.order, sol.secondary_cost, sol.stats["max_labels"], sol.exact
```

Notes:
- `n` enters only through `step/(n−1)`. It could equally be a runtime parameter; I would make it one.
- `P.width_param()` is B\*, known to E2 at run time.
- The definitions in `orders.py` (`model_v2`, `make_model_v7`, `make_model_loglin`, `work_features`) remain the reference semantics. `check()` asserts that the spec's step values equal them on random steps.

## A9. Checking and acceptance

1. **Eager E2** (Python, on the IR) against brute-force enumeration of all paths of Γ, on random graphs with n ≤ 12. This is the analogue of `tests/test_kopt.py`.
2. **Compiled against eager E2:** the same cost to 1e-9 and the same path, for every secondary clause.
3. **Against `kopt`** on the square-sum graphs n = 40–75, for V2, V7 and work: the same orderings, and costs within 1e-12 relative.
4. **Speed:** within 1.3× of `kopt` (the milestone-1 target relative to hand-written code).
5. **The hamiltonian tests pass** with `ham_kpw` switched to the DSL path.

When 1–5 hold, `kopt.c` stays in the repo as the hand-written reference, as `kpw.c` and `kcw.c` did in milestone 1.

## A10. Scope

**Out of scope:**
- **Costs over windows of steps** (the ConvMLP) and costs with a vector-valued carried state. A two-dimensional carried state would need a vector dominance order and its own lemma. It is a natural next row of the library, but not needed now.
- **Memory caps** (plan §3.4a, variant 1). They fit as a `filter(label) by lemma.monotone_filter` clause: a predicate monotone in p, applied when labels are created. I would add it in the step after this one, once the work model has been refitted on runs that used its own orderings.

**Files:**
- `dsl/ir.py`: Real, the new operations, `param`, `table`, `comp_sum`;
- `dsl/problem.py`: `secondary`, `param`, `solve(output=..., secondary=..., params=...)`;
- `dsl/lemma.py`: `additive`, `pareto_monotone`, the sign analysis;
- `dsl/eager.py`: complete mode, the backward pruning, eager E2, enumeration of paths for `check()`;
- `dsl/codegen.py`: real expressions, `step_eval`, `block_steps`, sweep closure for blocks;
- `src/C/dsl_engine.h`: complete mode and pruning;
- `src/C/dsl_dagopt.h` (new): E2;
- `tests/test_dsl_secondary.py` (new).

---

# Part B. Compile on first use

## B1. The problem

- **A git or PyPI dependency installs only the Python package.** kobayashi-pw is built with `uv_build`, which packages `src/kobayashi_pw` and runs no C compiler. `src/C` is outside the package, so a git or PyPI dependency installs neither the C sources nor the binaries.
- **Today's lookups work only from a source tree.** `orders_cli._find_kpw`, `orders.find_kopt`, hamiltonian's `ham_kpw.find_kpw` and the DSL's `jit.c_dir()` all locate `src/C` relative to the package directory, which exists only in an editable install.

## B2. Shipping the C sources

The C files stay in `src/C`, following the repo convention, and are mapped into the wheel as package data. With hatchling this is

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/kobayashi_pw"]

[tool.hatch.build.targets.wheel.force-include]
"src/C" = "kobayashi_pw/_csrc"
```

The wheel then contains only sources and headers; binaries are excluded by pattern. Before the change I will check whether `uv_build` itself can include a directory outside the module root. If it can, the build backend stays as it is. Either way, acceptance is a wheel built from a clean checkout, installed into an empty virtual environment, that compiles and runs `kpw2` and `kopt` (§B6).

## B3. `kobayashi_pw/native.py`

```python
def program(name: str, n: int | None = None) -> str:
    """Path of a compiled program: kpw, kpw2, kopt, kcw, bab.  Compiled on first use."""
```

- **Sources:** `kobayashi_pw/_csrc` in an installed package, else `src/C` in a source tree, or `$KPW_ENGINE` (the same rule as `jit.c_dir()`, which moves here).
- **Word count:** W = ⌈n/64⌉, rounded up to {1, 2, 3, 4, 8, 16}, for the programs that take `-DW`. This removes the n ≤ 128 limit of the default `kpw2` build: n = 150 gets W = 3, matching `kpw2_192`.
- **Flags** per program, from one table: `-O3 -march=native`, plus `-pthread` for kpw2 and `-lm` for kopt.
- **Cache:** `$KPW_CACHE/bin/<key>/<name>`, where key = SHA-256 of
  - the program's source and the headers it includes,
  - W and the flags,
  - `cc --version`,
  - `platform.machine()`.

  Editing a source file changes the key, so the next call recompiles, and the cache never serves a binary built from older sources.
- **Concurrency.** A file lock (`fcntl`) protects compilation, with compile-to-temporary and atomic rename. These are the helpers already in `dsl/jit.py`; they move to `native.py` and `jit.py` imports them.
- **Overrides.** `KPW_BIN_<NAME>`, e.g. `KPW_BIN_KPW2=/path`, or an explicit argument, bypass compilation. This is for machines where you want a hand-built binary.
- **No compiler:** a clear error naming the program and the missing compiler. Callers that have a Python fallback (`OrderDAG.build`, `optimize`) use it with a warning, as they do now.
- **`kobayashi-pw-build [--n N]`,** a new console script, compiles everything ahead of time, e.g. before a long batch job or on a login node.

## B4. Call sites

- `orders_cli._find_kpw(explicit, n)` → `native.program("kpw" if n ≤ 64 else "kpw2", n)`.
- `orders.find_kopt(explicit)` → `native.program("kopt", n)`. `optimize_file` reads n from the file header to choose W.
- `dsl/jit.py`: `c_dir()` and the compiler helpers come from `native.py`. The DSL's own cache is unchanged.
- **hamiltonian** `ham_kpw.find_kpw`/`find_kopt` → `kobayashi_pw.native.program`. The `--kpw-bin`/`--kopt-bin` options remain as explicit overrides.
- **The Makefile** stays, for development and benchmarks.

## B5. The hamiltonian dependency

```toml
[tool.uv.sources]
kobayashi-pw = { git = "https://github.com/algebravic/kobayashi-pw.git", rev = "<tag or commit>" }
```

The editable path source remains an option for development. Nothing else in hamiltonian changes. On a new machine the first `count --ordering kpw` compiles `kpw2` and `kopt`, which takes a second or two, and later runs use the cache.

## B6. Tests

1. `native.program` compiles each program, a second call returns the cached path without compiling, and touching a source changes the key.
2. The W buckets: `kpw2` on a 150-vertex graph gives the same width as `kpw2_192`.
3. Two processes requesting the same program at once both succeed, with one compilation.
4. A wheel built from the repo, installed into an empty virtual environment, runs `kobayashi-pw-orders data/sq63.txt` with no source tree present.
5. The existing tests pass, and the hamiltonian tests pass against the installed (not editable) package.

## B7. Order of work

1. **Part B.** It is independent and small: about 150 lines plus packaging, and it is what makes a git dependency usable.
2. **Part A, in this order:**
   - complete mode and pruning in engine E (`output dag`);
   - the Real IR and the eager E2 with `check()`;
   - codegen and the compiled E2;
   - the hampath specs and acceptance against `kopt`;
   - switching `ham_kpw` to the DSL path behind an option, then by default once the acceptance tests pass.

## Questions for you

1. **Build backend.** Is switching to hatchling acceptable if `uv_build` cannot include `src/C`? The alternative is to move the C sources under `src/kobayashi_pw/`, against the repo convention.
2. **Default for the hampath work model.** Should it live in kobayashi-pw (as `model_v7` does now, in `orders.py` and as a DSL spec), or in hamiltonian, which would pass the spec to the DSL? I lean to kobayashi-pw for V2 and V7, which are already there, and hamiltonian for the work model, since its features and fit belong to that repo. The DSL's `param` mechanism makes either work.
3. **`kopt.c` after acceptance.** Keep it as the reference implementation, or retire it once the DSL path is the default?

## Status

**Part B implemented (2026-11-24).**

- **`kobayashi_pw/native.py`.** `program`, `try_program` and the `kobayashi-pw-build` command. The DSL's `jit.py` now takes its source directory, cache directory and compiler from it.
- **Packaging.** hatchling, with each C source and header force-included as `kobayashi_pw/_csrc/<file>`; files are listed one by one so that binaries never enter the wheel.
- **Call sites switched:** `orders.find_kopt` (W chosen from the DAG file's header), `orders_cli._find_kpw`, and hamiltonian's `ham_kpw.find_kpw`.
- **`tests/test_native.py`:**
  - each program compiles once and is cached;
  - edited sources and headers change the key;
  - the W buckets, including kpw2 on a 150-vertex graph;
  - the kpw n ≤ 64 limit;
  - four concurrent processes give one compilation;
  - the `KPW_BIN_*` override, and the behaviour without a compiler;
  - the wheel's file list against `native.PROGRAMS` and the headers.
- **Acceptance (B6.4).** A wheel built with `pip wheel .` contains only sources under `_csrc`. Installed into an empty virtual environment and run outside the source tree, it compiled and ran:
  - `kobayashi-pw-orders` (kpw, n = 63);
  - `kpw2` (n = 75, W = 2);
  - `kopt` (the V7 optimum at n = 75, 1.107831, as before);
  - a DSL `vertex_separation` solve.

The root file `build.toml` still contains the old `uv_build` `[build-system]` table. Nothing reads it (`pyproject.toml` is what counts), so I left it alone.

**Part A implemented (2026-11-24).**

**What exists:**
- **IR:** the Real type and the operations of §A6.
- **Problem:** `secondary`, `param`, `table`, `solve(output="pareto", ...)`, `evaluate_secondary`, `check_secondary`, and `report()`/`pretty()` lines for secondary clauses.
- **Lemmas:** `lemma.additive` and `lemma.pareto_monotone`, with the sign analysis of §A4.
- **Engine E:** the complete mode (`Eng.complete`; `eng_run` shared by `dsl_solve` and `dsl_dagopt`).
- **Codegen:** `dag_arcs`, the step functions and `sec_block`, with prefix unions for the frontier, and the sweep closure forced when secondary output is compiled.
- **`src/C/dsl_dagopt.h`:** E2.
- **Eager mode:** complete search, E2, and enumeration of every path for checking.
- **`dsl/hampath.py`:** V2, V7 and the log-linear work form.
- **Tests:** `tests/test_dsl_secondary.py`.

**How it differs from the design:**
- **Only `direction="reverse"`** (the frontier-DP direction) is implemented; `forward` raises `NotImplementedError`.
- **The `k_best` and `sample` outputs are not in the DSL.** `orders.k_best` and `OrderDAG.sample` remain the way to get them.
- **Pruning is implicit.** E2 does not build the pruned DAG first: a state with no labelled successor stays empty, which is the backward pass of §A7.1 done in the same loop. `output dag(file=...)` (writing KPWDAG3 from the DSL) is not implemented.
- **Secondary output does not split components.** It solves the whole graph, because the secondary cost is not additive over components.
- **Block order with `greedy2`.** The DSL applies its closure rules in one sweep, while `core.expand` reaches a rule-1 fixpoint before each rule-2 step. With `greedy2` the blocks can therefore differ from kopt's. The comparison with kopt is made without `greedy2`, as in hamiltonian.

**Acceptance:**
1. `check_secondary` passes: the E2 optimum equals the minimum over all paths, compiled equals eager, the fold equals evaluation of the whole ordering, and the ordering is width-optimal. This was run on 180 graph-and-cost pairs during development, and the tests run 2 × 40 graphs × 3 costs.
2. The DSL equals `orders.optimize` on G₁₆–G₃₀, in both modes.
3. The DSL equals kopt on G₄₀–G₇₅ for V2, V7 and work, with the same ordering in every case.
4. Speed: `doc/dsl_codegen_perf.md`. On the optimisation proper the DSL takes 0.69–1.02× kopt's time, and 0.66–1.02× of kpw + kopt in total.
5. Hamiltonian: `ham_count --ordering kpw --kpw-engine dsl` gives the same orderings as the kopt path (`tests/test_kpw.py::test_dsl_engine_equals_kopt`). It remains an option, with kopt as the default, until you decide otherwise.
