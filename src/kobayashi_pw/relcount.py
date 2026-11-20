import sys, time
sys.path.insert(0, ".")
from census import sq, relevant_dag
from kobayashi_pw import pathwidth
for n in map(int, sys.argv[1:]):
    g = sq(n); r = pathwidth(g, want_order=False); k = r.width
    t = time.time(); rf, rc, rp = relevant_dag(g, k)
    print(f"n={n} pw={k} discovered={r.sets_expanded} R_pw={rf} on_opt_path={rc} orderings={rp:.3e} {time.time()-t:.0f}s", flush=True)
