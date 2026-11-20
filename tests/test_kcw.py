"""Tests for src/C/kcw.c (exact cutwidth) against the 2^n brute force."""
import itertools
import os
import random
import shutil
import subprocess

import pytest

from kobayashi_pw import from_edges
from kobayashi_pw.widths import brute_cutwidth, cutwidth_of_order

SRC = os.path.join(os.path.dirname(__file__), "..", "src", "C")
CC = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
pytestmark = pytest.mark.skipif(CC is None, reason="no C compiler")


@pytest.fixture(scope="module")
def kcw(tmp_path_factory):
    exe = str(tmp_path_factory.mktemp("kcw") / "kcw")
    subprocess.run([CC, "-O2", "-o", exe, os.path.join(SRC, "kcw.c")], check=True)
    return exe


def run(exe, n, E, flags=()):
    txt = "\n".join(map(str, range(n))) + "\n" + "\n".join(f"{u} {v}" for u, v in E) + "\n"
    r = subprocess.run([exe] + list(flags), input=txt, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr          # kcw re-checks the width of its ordering
    head, order = r.stdout.split("\n")[:2]
    d = dict(kv.split("=") for kv in head.split())
    return int(d["cw"]), order.split()[1:]


def graphs(seed, count):
    rng = random.Random(seed)
    for t in range(count):
        n = rng.randint(1, 10)
        p = rng.random()
        if t % 3 == 0:                          # bipartite (exact Konig cover)
            k = rng.randint(0, n)
            E = [(i, j) for i in range(k) for j in range(k, n) if rng.random() < p]
        else:
            E = [(i, j) for i, j in itertools.combinations(range(n), 2) if rng.random() < p]
        if t % 4 == 1:                          # add true and false twins
            for _ in range(rng.randint(1, 2)):
                v, w = rng.randrange(n), n
                n += 1
                nb = {u for e in E if v in e for u in e if u != v}
                E += [(u, w) for u in nb] + ([(v, w)] if rng.random() < 0.5 else [])
        yield n, E


@pytest.mark.parametrize("flags", [(), ("-C",), ("-W",)])
def test_against_brute(kcw, flags):
    for n, E in graphs(7, 150):
        g = from_edges(E, range(n))
        w, order = run(kcw, n, E, flags)
        assert w == brute_cutwidth(g)
        assert cutwidth_of_order(g, [int(v) for v in order]) == w


def test_disconnected_and_named(kcw):
    txt = "a b\nb c\nc a\nx y\nlonely\n"
    r = subprocess.run([kcw], input=txt, capture_output=True, text=True)
    head, order = r.stdout.split("\n")[:2]
    assert "cw=2 " in head and sorted(order.split()[1:]) == ["a", "b", "c", "lonely", "x", "y"]


def test_complete_graph_twins(kcw):
    n = 30
    w, _ = run(kcw, n, list(itertools.combinations(range(n), 2)))
    assert w == (n // 2) * ((n + 1) // 2)        # cw(K_n) = floor(n^2/4)
