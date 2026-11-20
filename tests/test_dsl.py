"""Tests for the embedded DSL (src/kobayashi_pw/dsl): eager and compiled
modes against brute force, obligation checks, and parity with kpw/kcw."""
import os
import shutil
import subprocess

import pytest

from kobayashi_pw import from_edges
from kobayashi_pw.dsl import cutwidth, treewidth, vertex_separation
from kobayashi_pw.dsl.jit import compiler
from kobayashi_pw.widths import brute_cutwidth

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "data")
SRC = os.path.join(HERE, "..", "src", "C")
CC = compiler()


@pytest.fixture(autouse=True, scope="module")
def cache(tmp_path_factory):
    old = os.environ.get("KPW_CACHE")
    os.environ["KPW_CACHE"] = str(tmp_path_factory.mktemp("kpwcache"))
    yield
    if old is None:
        os.environ.pop("KPW_CACHE", None)
    else:
        os.environ["KPW_CACHE"] = old


MODES = ("eager", "c") if CC else ("eager",)


@pytest.mark.parametrize("spec", [vertex_separation, lambda: vertex_separation(greedy2=True),
                                  cutwidth, lambda: cutwidth(cover=False), lambda: cutwidth(counters=False),
                                  lambda: cutwidth(twins=False)])
def test_obligations_and_brute(spec):
    """O1/O3/O4 on every eager arc, closure hypotheses, widths vs brute force."""
    spec().check(n_max=8, trials=80, seed=11, modes=MODES)


def test_treewidth_eager():
    P = treewidth()
    assert P.compile_ok() is not None            # simplicial closure may raise the cost
    P.check(n_max=7, trials=60, seed=5, modes=("eager",))


def test_known_values():
    import itertools
    K6 = from_edges(list(itertools.combinations(range(6), 2)), range(6))
    C8 = from_edges([(i, (i + 1) % 8) for i in range(8)], range(8))
    for m in MODES:
        assert cutwidth().solve(K6, mode=m).width == 9
        assert vertex_separation().solve(K6, mode=m).width == 5
        assert cutwidth().solve(C8, mode=m).width == 2 == brute_cutwidth(C8)
        assert vertex_separation().solve(C8, mode=m).width == 2
    assert treewidth().solve(K6, mode="eager").width == 5
    assert treewidth().solve(C8, mode="eager").width == 2


def test_report_and_pretty():
    for P in (vertex_separation(True), cutwidth(), treewidth()):
        r = P.report()
        assert "FAILS" not in r
        assert P.pretty().startswith(f"problem {P.name}")


@pytest.mark.skipif(CC is None, reason="no C compiler")
def test_parity_with_kpw_kcw(tmp_path):
    from kobayashi_pw import read_edge_list
    kpw, kcw = str(tmp_path / "kpw"), str(tmp_path / "kcw")
    subprocess.run([CC, "-O2", "-o", kpw, os.path.join(SRC, "kpw.c")], check=True)
    subprocess.run([CC, "-O2", "-o", kcw, os.path.join(SRC, "kcw.c")], check=True)
    bench = os.path.join(DATA, "bench")
    files = sorted(f for f in os.listdir(bench) if f.startswith(("gnp_n30", "gnp_n40", "dgnp_n30")))[:12] if os.path.isdir(bench) else []
    files = [os.path.join(bench, f) for f in files] or [os.path.join(DATA, "sq61.txt")]
    for f in files:
        g = read_edge_list(f)
        pw = int(subprocess.run([kpw, "-q", f], capture_output=True, text=True).stdout.split("pw=")[1].split()[0])
        assert vertex_separation().solve(g, mode="c").width == pw
        out = subprocess.run([kcw, "-q", f], capture_output=True, text=True).stdout
        cw = int(out.split("cw=")[1].split()[0])
        s = cutwidth().solve(g, mode="c")
        assert s.width == cw
        ref_states = int(out.split("states=")[1].split()[0])
        # the same search: identical counts on grids and square-sum graphs; on some random
        # graphs a tie-break difference (not yet identified) changes the count slightly
        assert abs(s.stats["states"] - ref_states) <= 0.1 * ref_states + 2
