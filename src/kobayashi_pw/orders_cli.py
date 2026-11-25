"""kobayashi-pw-orders: pathwidth-optimal orderings for a left-to-right frontier
DP, optimised for a secondary cost.

Orderings are printed in the frontier-DP convention: the frontier after step i
is the set of placed vertices that have an unplaced neighbour, and its maximum
over the ordering equals pw.
"""

from __future__ import annotations

import argparse
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time

from .core import Graph
from .io import read_edge_list, read_graph6
from .orders import (OrderDAG, evaluate, k_best, make_model_v7, model_v2,
                     optimize, tau_features)


def _find_kpw(explicit: str | None, n: int) -> str | None:
    """kpw for n <= 64, kpw2 otherwise, compiled on first use (native.py);
    None if no C compiler is available (the DAG is then built in Python)."""
    from .native import try_program
    return try_program("kpw" if n <= 64 else "kpw2", n, explicit=explicit)


def build_dag(g: Graph, greedy2: bool, kpw: str | None, threads: int = 1) -> OrderDAG:
    """Build with the C program when available, else in Python.  The graph
    is passed to the C program with vertices renamed 0..n-1 (which the C
    reader numbers identically), so the DAG's vertex numbering is g's."""
    if kpw is None:
        return OrderDAG.build(g, greedy2=greedy2)
    with tempfile.TemporaryDirectory() as td:
        ef, df = os.path.join(td, "g.txt"), os.path.join(td, "g.dag")
        with open(ef, "w") as f:
            for v in range(g.n):
                f.write(f"{v}\n")
            for v in range(g.n):
                for u in range(g.n):
                    if g.nin[v] >> u & 1 and u < v:
                        f.write(f"{u} {v}\n")
        cmd = [kpw, "-q", "-c", "-o", df] + (["-g"] if greedy2 else [])
        if threads != 1 and os.path.basename(kpw).startswith("kpw2"):
            cmd += ["-t", str(threads)]
        cmd.append(ef)
        subprocess.run(cmd, check=True, capture_output=True)
        dag = OrderDAG.load(df)
    dag.g = Graph(g.n, g.nin, list(g.labels))
    return dag


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("file", help="edge list (or graph6 with --format graph6); undirected")
    ap.add_argument("--format", choices=["edges", "graph6"], default="edges")
    ap.add_argument("--cost", choices=["v2", "v7", "none"], default="v7",
                    help="secondary cost: hampath V2 (additive) or V7 (proxy, _dp_cost)")
    ap.add_argument("--expand-base", type=float, default=1.55, help="V7 parameter")
    ap.add_argument("--density-alpha", type=float, default=0.25, help="V7 parameter")
    ap.add_argument("--k", type=int, default=1, help="k best orderings (additive cost only)")
    ap.add_argument("--sample", type=int, default=0,
                    help="also print N orderings drawn uniformly from the DAG")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--greedy2", action="store_true",
                    help="smaller DAG via Coudert et al.'s second greedy rule (fewer orderings)")
    ap.add_argument("--kpw", default=None,
                    help="path to kpw or kpw2 (default: compiled on first use; see native.py)")
    ap.add_argument("--threads", type=int, default=1, help="threads for kpw2 (0 = all cores)")
    ap.add_argument("--python", action="store_true", help="build the DAG in Python even if kpw exists")
    ap.add_argument("--profile", action="store_true", help="print the frontier profile of the result")
    a = ap.parse_args(argv)

    if a.format == "graph6":
        with open(a.file) as f:
            g = read_graph6(f.readline())
    else:
        g = read_edge_list(a.file)
    if any((g.nin[v] >> u & 1) != (g.nin[u] >> v & 1) for v in range(g.n) for u in range(g.n)):
        print("error: secondary costs are defined for undirected graphs", file=sys.stderr)
        return 1

    t0 = time.perf_counter()
    dag = build_dag(g, a.greedy2, None if a.python else _find_kpw(a.kpw, g.n), a.threads)
    t1 = time.perf_counter()
    print(f"n={g.n} pw={dag.pw} dag_nodes={len(dag)} orderings={dag.num_orderings():.3e} "
          f"greedy2={dag.greedy2} build={t1 - t0:.2f}s")

    model = {"v2": model_v2, "v7": make_model_v7(a.expand_base, a.density_alpha),
             "none": None}[a.cost]
    if model is not None:
        if a.k > 1:
            if a.cost != "v2":
                print("error: --k needs an additive cost (v2)", file=sys.stderr)
                return 1
            for rank, (c, tau) in enumerate(k_best(dag, model, a.k), 1):
                print(f"rank {rank} cost={c:.6g}\norder: {' '.join(map(str, tau))}")
        else:
            r = optimize(dag, model)
            print(f"{a.cost} optimum={r.cost:.6g} (exact={r.exact}, max_labels={r.max_labels}, "
                  f"{time.perf_counter() - t1:.2f}s)")
            print("order:", " ".join(map(str, r.tau)))
            if a.profile:
                print("profile:", " ".join(str(f.fw) for f in tau_features(g, r.tau)))
    if a.sample:
        rng = random.Random(a.seed)
        for tau in dag.sample(rng, k=a.sample):
            line = "sample:"
            if model is not None:
                line += f" cost={evaluate(g, tau, model, dag.pw):.6g}"
            print(line, " ".join(map(str, tau)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
