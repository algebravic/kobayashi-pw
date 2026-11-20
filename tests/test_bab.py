"""Tests for src/C/bab.c (C translation of Coudert et al.'s branch and bound,
from SageMath).  Step-for-step agreement with Sage itself was checked
separately (bench/bab_parity.py, needs Sage)."""
import itertools
import os
import random
import shutil
import subprocess

import pytest

from kobayashi_pw import from_edges

from .test_core import brute

SRC = os.path.join(os.path.dirname(__file__), "..", "src", "C")
CC = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
pytestmark = pytest.mark.skipif(CC is None, reason="no C compiler")


@pytest.fixture(scope="module")
def bab(tmp_path_factory):
    exe = str(tmp_path_factory.mktemp("bab") / "bab")
    subprocess.run([CC, "-O2", "-o", exe, os.path.join(SRC, "bab.c")], check=True)
    return exe


def run(exe, n, E, directed=False, flags=()):
    txt = "\n".join(map(str, range(n))) + "\n" + "\n".join(f"{u} {v}" for u, v in E) + "\n"
    r = subprocess.run([exe] + list(flags) + (["-d"] if directed else []), input=txt,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr                 # the program verifies its ordering
    lines = r.stdout.split("\n")
    head = dict(kv.split("=") for kv in lines[0].split())
    order = lines[1].split()[1:] if len(lines) > 1 and lines[1].startswith("order:") else []
    return int(head["pw"]), order


@pytest.mark.parametrize("directed", [False, True])
def test_against_brute(bab, directed):
    rng = random.Random(21 + directed)
    for _ in range(200):
        n = rng.randint(1, 10)
        E = [(i, j) for i, j in itertools.permutations(range(n), 2)
             if (directed or i < j) and rng.random() < rng.random()]
        # bab uses out-neighbours; brute uses in-neighbours: same value
        # (vs(D) = vs(D^R)), so compare with the reversed digraph's brute value too
        pw = brute(from_edges(E, range(n), directed))
        pwr = brute(from_edges([(v, u) for u, v in E], range(n), directed))
        assert pw == pwr
        for flags in ((), ("-l", "2"), ("-m", "3"), ("-l", "0")):
            w, order = run(bab, n, E, directed, flags)
            assert w == pw and sorted(map(int, order)) == list(range(n))


def test_bounds(bab):
    rng = random.Random(5)
    for _ in range(60):
        n = rng.randint(3, 11)
        E = [(i, j) for i, j in itertools.combinations(range(n), 2) if rng.random() < 0.4]
        pw = brute(from_edges(E, range(n)))
        if pw == 0:
            continue
        assert run(bab, n, E, flags=("-u", str(pw)))[0] == -1          # nothing below pw
        assert run(bab, n, E, flags=("-u", str(pw + 1)))[0] == pw
        assert run(bab, n, E, flags=("-k", str(n)))[0] >= pw           # cut-off: any solution <= n
