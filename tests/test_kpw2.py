"""Tests for src/C/kpw2.c: compiled here (W=1 and W=2) if a C compiler exists."""
import itertools
import os
import random
import shutil
import subprocess

import pytest

from kobayashi_pw import from_edges, pathwidth
from kobayashi_pw.orders import OrderDAG

from .test_core import brute

SRC = os.path.join(os.path.dirname(__file__), "..", "src", "C")
CC = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
pytestmark = pytest.mark.skipif(CC is None, reason="no C compiler")


@pytest.fixture(scope="module")
def bins(tmp_path_factory):
    d = tmp_path_factory.mktemp("kpw2")
    out = {}
    for name, src, extra in (("kpw", "kpw.c", []), ("kpw2", "kpw2.c", ["-pthread"]),
                             ("kpw2_64", "kpw2.c", ["-pthread", "-DW=1"])):
        exe = str(d / name)
        subprocess.run([CC, "-O2", "-o", exe, os.path.join(SRC, src)] + extra, check=True)
        out[name] = exe
    return out


def run(exe, flags, n, E, directed=False, dag=None):
    txt = "\n".join(map(str, range(n))) + "\n" + "\n".join(f"{u} {v}" for u, v in E) + "\n"
    args = [exe, "-q"] + flags + (["-d"] if directed else []) + (["-o", dag] if dag else [])
    r = subprocess.run(args, input=txt, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return dict(kv.split("=") for kv in r.stdout.split())


FLAGS = [[], ["-g"], ["-c"], ["-g", "-c"], ["-x"], ["-x", "-g", "-c"],
         ["-t", "3"], ["-t", "3", "-c"], ["-t", "2", "-x", "-g"]]


@pytest.mark.parametrize("directed", [False, True])
def test_small_against_brute_and_kpw(bins, directed):
    rng = random.Random(101 + directed)
    for _ in range(60):
        n = rng.randint(1, 10)
        E = [(i, j) for i, j in itertools.permutations(range(n), 2)
             if (directed or i < j) and rng.random() < rng.random()]
        pw = brute(from_edges(E, range(n), directed))
        for fl in FLAGS:
            for b in ("kpw2", "kpw2_64"):
                assert int(run(bins[b], fl, n, E, directed)["pw"]) == pw
            if "-t" not in fl and "-x" not in fl:     # sequential: identical counts to kpw
                a, c = run(bins["kpw"], fl, n, E, directed), run(bins["kpw2"], fl, n, E, directed)
                keys = ("pw", "sets", "pairs", "rescans") + (("dag",) if "-c" in fl else ())
                assert all(a[k] == c[k] for k in keys)


def grid(a, b):
    idx = lambda i, j: i * b + j
    return [(idx(i, j), idx(i + di, j + dj)) for i in range(a) for j in range(b)
            for di, dj in ((0, 1), (1, 0)) if i + di < a and j + dj < b]


@pytest.mark.parametrize("a,b", [(8, 9), (7, 11), (9, 10)])
def test_beyond_64_known_grids(bins, a, b):
    for fl in ([], ["-g", "-x"], ["-t", "3"]):
        assert int(run(bins["kpw2"], fl, a * b, grid(a, b))["pw"]) == min(a, b)


def test_beyond_64_matches_python(bins):
    rng = random.Random(7)
    for _ in range(4):
        n = rng.randint(65, 80)
        E = [(i, j) for i, j in itertools.combinations(range(n), 2) if rng.random() < 2.2 / n]
        g = from_edges(E, range(n))
        r = pathwidth(g, want_order=False, greedy2=True)
        d = run(bins["kpw2"], ["-g"], n, E)
        assert int(d["pw"]) == r.width and int(d["sets"]) == r.sets_expanded


def test_dag2_load_equals_build(bins, tmp_path):
    E = grid(8, 9)
    dag = str(tmp_path / "g.dag")
    run(bins["kpw2"], ["-c", "-t", "2"], 72, E, dag=dag)
    a, b = OrderDAG.load(dag), OrderDAG.build(from_edges(E, range(72)))
    assert a.pw == b.pw == 8 and set(a.arcs) == set(b.arcs)
    assert a.num_orderings() == b.num_orderings()
