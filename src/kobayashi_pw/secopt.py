"""Exact minimisation of an arc-additive secondary cost (V2 of the hampath paper, in the
user's frontier convention) over (a) all pw-optimal orderings and (b) the orderings carried by
the Kobayashi relevant-set DAG (kpw table completed at level pw, reversed)."""
import sys, math, time
sys.path.insert(0, "/home/claude/kobayashi-pw/src")
from kobayashi_pw import pathwidth
from kobayashi_pw.core import expand, _bits
from census import sq

def mk(g, pw):
    n, nin = g.n, g.nin; full = (1 << n) - 1
    def nbu(X):
        m = 0
        for u in _bits(X): m |= nin[u]
        return m
    def L(T):                       # user's frontier: vertices of T with a neighbour outside T
        return T & nbu(full & ~T)
    def step(T, v):                 # cost of introducing v after prefix T (user's DP order)
        T2 = T | (1 << v); F = L(T2); f = F.bit_count()
        nb = (nin[v] & T & F).bit_count()        # back-edges to vertices still in frontier
        return 2.0 ** nb * (f / pw) ** 2 + 0.001 * f, f
    return n, nin, full, L, step

def full_opt(g, pw):
    n, nin, full, L, step = mk(g, pw)
    layer = {0: (0.0, None)}
    for i in range(n):
        nxt = {}
        for T, (c, _) in layer.items():
            for v in _bits(full & ~T):
                dc, f = step(T, v)
                if f > pw: continue
                T2 = T | (1 << v); c2 = c + dc
                if T2 not in nxt or c2 < nxt[T2][0]: nxt[T2] = (c2, None)
        layer = nxt
    return layer[full][0]

def relevant_opt(g, pw):
    n, nin, full, L, step = mk(g, pw)
    S0, nb0, a0 = expand(nin, full, 0, 0)
    R = [dict() for _ in range(n + 1)]; R[S0.bit_count()][S0] = nb0
    arcs = {}
    for i in range(n + 1):
        for S, nb in R[i].items():
            out = []
            for x in _bits(full & ~S):
                b = 1 << x
                if ((nb | nin[x]) & ~(S | b)).bit_count() <= pw:
                    T, nbT, added = expand(nin, full, S | b, nb | nin[x])
                    R[T.bit_count()].setdefault(T, nbT); out.append((T, [x] + added))
            arcs[S] = out
    def block_cost(Tpre, block):    # user order adds block reversed: e_m ... e_1, x
        c = 0.0; T = Tpre
        for v in reversed(block):
            dc, f = step(T, v); assert f <= pw; c += dc; T |= 1 << v
        return c
    h = {full: 0.0}
    for i in range(n - 1, -1, -1):
        for S in R[i]:
            best = math.inf
            for T, block in arcs[S]:
                if T in h:
                    best = min(best, h[T] + block_cost(full & ~T, block))
            if best < math.inf: h[S] = best
    return h[S0] + block_cost(full & ~S0, a0)

for n in map(int, sys.argv[1:]):
    g = sq(n); pw = pathwidth(g, want_order=False).width
    t = time.time(); r = relevant_opt(g, pw); t1 = time.time() - t
    t = time.time(); f = full_opt(g, pw); t2 = time.time() - t
    print(f"n={n} pw={pw}  V2 optimum over all pw-optimal orderings = {f:.4f} ({t2:.0f}s)   "
          f"over relevant-set DAG = {r:.4f} ({t1:.1f}s)   ratio = {r/f:.4f}", flush=True)
