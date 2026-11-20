# Review of `separation` (MaxSAT model and Kobayashi implementation)

Repo: `~/Programming/Combinatorics/separation`. I changed nothing in it; all runs below used copies.

## 1. `vertex_separation.py`: the model is correct

I checked it in two ways.

- **Proof.** It is written up as Proposition 18 in the paper.
- **Experiment.** On 400 random graphs and digraphs with n ≤ 9, I compared it with the bucketed Kobayashi search, which had already been checked against brute force on graphs this small. In every case the optimal value agreed, and the reversed ordering had width exactly vs(D) in Kobayashi's N⁻ convention.

### What the model counts

```
¬y[v,t] ∨ y[w,t] ∨ u[v,t]     for w ∈ self._nbr(v)
Σ_v u[v,t] + Σ_s ¬z[s] ≤ n     (with z unary)  ⇒  Σ_v u[v,t] ≤ Z
```

So u[v,t] counts the vertices **inside** the prefix that have a neighbour outside it. This is Kinnersley's V_L convention. Kobayashi (and Coudert's MIP, through x − y) count the vertices **outside** the prefix. The two conventions are related by reversing the order: L_t(σ) = N⁻(V(σᴿ_{n−t})). So:

- the optimal value is vs(D) in either convention;
- **`pathwidth_order` returns an ordering that is optimal read backwards** in Kobayashi's convention. Read forwards, it is optimal only in the V_L sense.

## 2. Issues found

1. **`isinstance(gph, nx.Graph)` is True for `nx.DiGraph`**, because DiGraph subclasses Graph. So the `predecessors` branch never runs, in `VertexSeparation.__init__`, `separation` or `alt_separation`. For digraphs the code uses successors.
   - This is harmless for the value. With successors, L_t is exactly Kobayashi's N⁻ boundary of the reversed order, so the value is vs(D).
   - With predecessors you would get vs(Dᴿ). That is also equal to vs(D), since pathwidth is invariant under reversing all arcs; I also checked this empirically.
   - The comments on lines 73–78 and 126 describe in- or out-neighbours inconsistently with what actually runs.
   - Suggested fix if the intent is "out-neighbours": `self._nbr = gph.successors if gph.is_directed() else gph.neighbors`.
2. **The README describes bandwidth, not vertex separation.** It defines width as max |f(v) − f(w)| over edges, and it bounds the per-vertex sum Σ_t u[v,t] ≤ z. The code bounds Σ_v u[v,t] for each t, which is the vertex separation model. The README is presumably left over from an earlier bandwidth model.
3. **`self._cnf.clauses` does not exist on `WCNF`.** It has `.hard` and `.soft`; I checked with PySAT 1.9.dev22. So both `trace > 0` and `verbose > 0` with `bound` set raise `AttributeError`. The `verbose` print on line 163 is also missing its `f` prefix.
4. **`bound`:** the unit clause `[-z[bound+1]]` is appended once per time step, n copies of the same clause. Harmless, but it belongs outside the loop. If `bound >= n` it raises `KeyError`, since `z` only goes up to n.
5. **`pyproject.toml`** uses the poetry backend rather than uv. This doesn't matter functionally.

## 3. `kobayashi.py` (Algorithm 1)

- **Correct as a decision procedure.** `rset` is initialised to empty collections, so the paper's misprint does not apply. Batch expansion is fine for deciding pw ≤ k. Only ordering extraction needs one-at-a-time expansion.
- **Quadratic insertion.** `rset[l] = rset[l].union([n_star])` copies the whole frozenset of frozensets on every insertion, so time grows quadratically in |R_l|. Use `rset = [set() for ...]` and `rset[l].add(n_star)`.
- **Digraphs:** `self._gph.neighbors` gives successors, so this computes the N⁺ convention, that is vs(Dᴿ) = vs(D). The value is fine.

## 4. Timings: MaxSAT (RC2 + CaDiCaL 1.9.5) vs `kpw`, same machine (Xeon 2.1 GHz, one core)

| graph | n | pw | MaxSAT | kpw (C) | ratio |
|---|---|---|---|---|---|
| g1 | 40 | 11 | 11.9 s | 0.008 s | ~1500× |
| g3 | 45 | 15 | 15.4 s | 0.019 s | ~800× |
| g2 | 60 | 11 | 305 s | 1.04 s | ~290× |
| sq63 | 63 | 14 | 198 s | 0.43 s | ~460× |

These numbers are now in Table 4 of the paper. Its Gurobi column is marked [tbd] for your numbers.
