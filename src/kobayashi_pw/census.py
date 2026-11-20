"""Compare the relevant-set DAG (Kobayashi/kpw) with the full DAG of pw-feasible prefix sets
on square-sum graphs.  Counts sets that lie on some optimal path, and the number of optimal
orderings (paths) each DAG represents."""
import sys, math, time
sys.path.insert(0, "/home/claude/kobayashi-pw/src")
from kobayashi_pw import from_edges, pathwidth
from kobayashi_pw.core import expand, _bits

def sq(n):
    E = [(i, j) for i in range(1, n+1) for j in range(i+1, n+1) if math.isqrt(i+j)**2 == i+j]
    return from_edges(E, range(1, n+1))

def full_dag(g, k):
    n, nin = g.n, g.nin; full = (1 << n) - 1
    layers = [dict() for _ in range(n+1)]       # set -> union of nin
    layers[0][0] = 0
    for i in range(n):
        nxt = layers[i+1]
        for S, nb in layers[i].items():
            for x in _bits(full & ~S):
                T = S | (1 << x); nbT = nb | nin[x]
                if T not in nxt and ((nbT & ~T).bit_count() <= k):
                    nxt[T] = nbT
    # backward: count completions
    paths = {full: 1} if full in layers[n] else {}
    for i in range(n-1, -1, -1):
        for S in layers[i]:
            c = sum(paths.get(S | (1 << x), 0) for x in _bits(full & ~S))
            if c: paths[S] = c
    return sum(map(len, layers)), len(paths), paths.get(0, 0)

def relevant_dag(g, k):
    n, nin = g.n, g.nin; full = (1 << n) - 1
    S0, nb0, _ = expand(nin, full, 0, 0)
    R = [dict() for _ in range(n+1)]; R[S0.bit_count()][S0] = nb0
    succ = {}
    for i in range(n+1):
        for S, nb in R[i].items():
            out = []
            for x in _bits(full & ~S):
                b = 1 << x
                if ((nb | nin[x]) & ~(S | b)).bit_count() <= k:
                    T, nbT, _ = expand(nin, full, S | b, nb | nin[x])
                    R[T.bit_count()].setdefault(T, nbT); out.append(T)
            succ[S] = out
    paths = {full: 1}
    for i in range(n-1, -1, -1):
        for S in R[i]:
            c = sum(paths.get(T, 0) for T in succ[S])
            if c: paths[S] = c
    return sum(map(len, R)), len(paths), paths.get(S0, 0)

if __name__ == "__main__":
  for n in map(int, sys.argv[1:]):
      g = sq(n); r = pathwidth(g, want_order=False); k = r.width
      t = time.time(); rf, rc, rp = relevant_dag(g, k); t1 = time.time() - t
      t = time.time(); ff, fc, fp = full_dag(g, k); t2 = time.time() - t
      print(f"n={n} pw={k} | kpw-discovered={r.sets_expanded} | relevant: R_pw={rf} on-opt-path={rc} orderings={rp:.3e} ({t1:.1f}s)"
            f" | all subsets: feasible={ff} on-opt-path={fc} orderings={fp:.3e} ({t2:.1f}s)", flush=True)
