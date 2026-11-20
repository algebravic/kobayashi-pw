"""Named-vertex edge lists: the C programs and the Python reader must number
vertices identically and print orderings with the input's names."""
import itertools
import os
import random
import shutil
import subprocess

import pytest

from kobayashi_pw import from_edges, ordering_width, pathwidth, read_edge_list
from kobayashi_pw.io import number_names
from kobayashi_pw.orders import OrderDAG

from .test_core import brute

SRC = os.path.join(os.path.dirname(__file__), "..", "src", "C")
CC = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")


@pytest.fixture(scope="module")
def bins(tmp_path_factory):
    if CC is None:
        pytest.skip("no C compiler")
    d = tmp_path_factory.mktemp("el")
    out = {}
    for name, src, extra in (("kpw", "kpw.c", []), ("kpw2", "kpw2.c", ["-pthread"])):
        exe = str(d / name)
        subprocess.run([CC, "-O2", "-o", exe, os.path.join(SRC, src)] + extra, check=True)
        out[name] = exe
    return out


def run(exe, path, flags=()):
    r = subprocess.run([exe] + list(flags) + [str(path)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    head, order = r.stdout.splitlines()[:2]
    return dict(kv.split("=") for kv in head.split()), order.split()[1:]


def test_number_names_rule():
    assert number_names(["3", "1", "-2"]) == [-2, 1, 3]
    assert number_names(["07", "7"]) == ["07", "7"]          # equal values: keep strings
    assert number_names(["a", "1"]) == ["a", "1"]
    assert number_names(["--5", "1"]) == ["--5", "1"]        # not an integer


def test_named_vertices(bins, tmp_path):
    rng = random.Random(4)
    for trial in range(40):
        n = rng.randint(1, 10)
        names = [f"v{rng.randrange(10**6)}_{i}" for i in range(n)]
        rng.shuffle(names)
        E = [(i, j) for i, j in itertools.combinations(range(n), 2) if rng.random() < rng.random()]
        lines = [f"{names[u]}\t{names[v]} {{}}" for u, v in E]
        lines += [names[v] for v in range(n)]                 # isolated or repeated: harmless
        rng.shuffle(lines)
        p = tmp_path / "g.txt"
        p.write_text("# a comment\n" + "\n".join(lines) + "\n")
        g = read_edge_list(str(p))
        pw = brute(g)
        for exe in ("kpw", "kpw2"):
            for flags in ((), ("-g",), ("-c",), ("-r",)):
                head, order = run(bins[exe], p, flags)
                assert int(head["n"]) == n and int(head["pw"]) == pw
                assert sorted(order) == sorted(names)
                tau = order[::-1] if "-r" in flags else order
                assert ordering_width(g, tau) == pw


def test_numeric_names_match_python_numbering(bins, tmp_path):
    rng = random.Random(8)
    for trial in range(30):
        n = rng.randint(2, 14)
        labels = rng.sample(range(-50, 200), n)              # gaps and negatives
        E = [(labels[i], labels[j]) for i, j in itertools.combinations(range(n), 2)
             if rng.random() < 0.35]
        p = tmp_path / "g.txt"
        p.write_text("\n".join(f"{u} {v}" for u, v in E) + "\n" + "\n".join(map(str, labels)) + "\n")
        g = read_edge_list(str(p))
        assert g.labels == sorted(labels)
        r = pathwidth(g, want_order=False)
        for exe in ("kpw", "kpw2"):
            head, order = run(bins[exe], p)
            # identical numbering => identical search, hence identical counts
            assert int(head["pw"]) == r.width and int(head["sets"]) == r.sets_expanded
            assert sorted(map(int, order)) == sorted(labels)


def test_square_sum_has_no_dummy_vertex(bins):
    path = os.path.join(os.path.dirname(__file__), "..", "data", "sq63.txt")
    for exe in ("kpw", "kpw2"):
        head, order = run(bins[exe], path)
        assert head["n"] == "63" and head["pw"] == "14"
        assert sorted(map(int, order)) == list(range(1, 64))


def test_dag3_carries_names(bins, tmp_path):
    p = tmp_path / "g.txt"
    E = [("a", "b"), ("b", "c"), ("c", "d"), ("d", "a"), ("a", "c"), ("e", "a")]
    p.write_text("\n".join(f"{u} {v}" for u, v in E) + "\nlonely\n")
    g = read_edge_list(str(p))
    for exe in ("kpw", "kpw2"):
        df = tmp_path / f"{exe}.dag"
        subprocess.run([bins[exe], "-q", "-c", "-o", str(df), str(p)], check=True, capture_output=True)
        a, b = OrderDAG.load(str(df)), OrderDAG.build(g)
        assert a.g.labels == g.labels == ["a", "b", "c", "d", "e", "lonely"]
        assert set(a.arcs) == set(b.arcs) and a.pw == b.pw
        for tau in a.sample(random.Random(1), k=20):
            assert ordering_width(g, tau[::-1]) == a.pw
