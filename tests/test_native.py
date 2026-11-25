"""native.py: compile-on-first-use of the C programs."""

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from kobayashi_pw import native

REPO = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(native.compiler() is None, reason="no C compiler")


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("KPW_CACHE", str(tmp_path / "cache"))
    return tmp_path / "cache"


@pytest.mark.parametrize("name", sorted(native.PROGRAMS))
def test_compiles_once_and_caches(name, cache):
    p1 = native.program(name)
    assert os.access(p1, os.X_OK) and str(cache) in p1
    t1 = os.stat(p1).st_mtime_ns
    p2 = native.program(name)
    assert p2 == p1 and os.stat(p2).st_mtime_ns == t1


def test_edited_source_gets_a_new_build(cache, tmp_path, monkeypatch):
    src = tmp_path / "csrc"
    shutil.copytree(native.c_dir(), src, ignore=shutil.ignore_patterns("kpw", "kpw2*", "kopt", "kcw", "bab",
                                                                       "fullcount", "Makefile*"))
    monkeypatch.setenv("KPW_ENGINE", str(src))
    p1 = native.program("kopt")
    (src / "kopt.c").write_text((src / "kopt.c").read_text() + "\n/* edited */\n")
    p2 = native.program("kopt")
    assert p1 != p2
    (src / "edgelist.h").write_text((src / "edgelist.h").read_text() + "\n/* edited */\n")
    assert native.program("kopt") != p2              # headers are part of the key


def test_word_buckets(cache, tmp_path):
    assert [native.w_bucket(n) for n in (1, 64, 65, 128, 129, 192, 193, 256, 257)] == [1, 1, 2, 2, 3, 3, 4, 4, 8]
    assert native.program("kpw2", 150) != native.program("kpw2", 100)
    # a 3 x 50 grid (150 vertices) has pathwidth 3; the default W=2 build could not read it
    g = tmp_path / "grid.txt"
    idx = lambda r, c: r * 50 + c
    lines = [f"{idx(r, c)} {idx(r, c + 1)}" for r in range(3) for c in range(49)]
    lines += [f"{idx(r, c)} {idx(r + 1, c)}" for r in range(2) for c in range(50)]
    g.write_text("\n".join(lines) + "\n")
    out = subprocess.run([native.program("kpw2", 150), "-q", "-t", "1", str(g)],
                         capture_output=True, text=True, check=True).stdout
    assert "pw=3" in out


def test_kpw_limit(cache):
    with pytest.raises(native.NativeUnavailable):
        native.program("kpw", 65)


def test_concurrent_requests_compile_once(cache):
    code = "from kobayashi_pw import native; print(native.program('kopt', 100))"
    env = dict(os.environ)
    procs = [subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True, env=env)
             for _ in range(4)]
    outs = {p.communicate()[0].strip() for p in procs}
    assert all(p.returncode == 0 for p in procs) and len(outs) == 1
    assert len(list((cache / "bin").iterdir())) == 1


def test_override_and_unavailable(cache, monkeypatch, tmp_path):
    exe = native.program("kopt")
    monkeypatch.setenv("KPW_BIN_KOPT", exe)
    assert native.program("kopt") == exe
    monkeypatch.setenv("KPW_BIN_KOPT", str(tmp_path / "missing"))
    with pytest.raises(native.NativeUnavailable):
        native.program("kopt")
    monkeypatch.delenv("KPW_BIN_KOPT")
    monkeypatch.setattr(native, "compiler", lambda: None)
    with pytest.raises(native.NativeUnavailable):
        native.program("kcw")
    assert native.try_program("kcw") is None


def test_wheel_file_list_matches_sources():
    cfg = tomllib.loads((REPO / "pyproject.toml").read_text())
    fi = cfg["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    shipped = {Path(k).name for k in fi}
    assert all(v == f"kobayashi_pw/_csrc/{Path(k).name}" for k, v in fi.items())
    needed = {p.source for p in native.PROGRAMS.values()} | {h.name for h in (REPO / "src" / "C").glob("*.h")}
    assert needed <= shipped, f"missing from the wheel: {sorted(needed - shipped)}"
