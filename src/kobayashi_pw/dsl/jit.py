"""On-demand compilation of generated ops, with an on-disk cache.

Cache key: SHA-256 of (generated ops source, W, engine headers, compiler
identity, flags).  The ops source is itself a deterministic function of the
IR and the D annotations, so equal specs share a library across processes and
graphs.  Libraries live in $KPW_CACHE or ~/.cache/kobayashi_pw/<key>/.
"""
from __future__ import annotations

import ctypes
import fcntl
import hashlib
import os
import shutil
import subprocess
import threading
from pathlib import Path

ENGINE_VERSION = "1"
W_BUCKETS = (1, 2, 3, 4, 5, 6, 8, 11, 16, 24, 32)
CFLAGS = ["-O3", "-march=native", "-shared", "-fPIC"]
DEBUG_CFLAGS = ["-O1", "-g", "-shared", "-fPIC", "-fsanitize=undefined"]


def c_dir() -> Path:
    env = os.environ.get("KPW_ENGINE")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "C"


def cache_dir() -> Path:
    return Path(os.environ.get("KPW_CACHE", Path.home() / ".cache" / "kobayashi_pw"))


def compiler() -> str | None:
    for c in (os.environ.get("CC"), "cc", "gcc", "clang"):
        if c and shutil.which(c):
            return c
    return None


_cc_ident: dict = {}


def _ident(cc: str) -> str:
    if cc not in _cc_ident:
        try:
            _cc_ident[cc] = subprocess.run([cc, "--version"], capture_output=True, text=True).stdout
        except OSError:
            _cc_ident[cc] = cc
    return _cc_ident[cc]


def w_bucket(n: int) -> int:
    need = max(1, (n + 63) // 64)
    for w in W_BUCKETS:
        if w >= need:
            return w
    raise ValueError(f"n = {n} exceeds {64 * W_BUCKETS[-1]}")


class Result(ctypes.Structure):
    _fields_ = [("status", ctypes.c_int), ("width", ctypes.c_int), ("lower_bound", ctypes.c_int),
                ("states", ctypes.c_double), ("expansions", ctypes.c_double), ("seconds", ctypes.c_double),
                ("order", ctypes.POINTER(ctypes.c_int))]


class Params(ctypes.Structure):
    _fields_ = [("time_limit", ctypes.c_double), ("max_states", ctypes.c_double)]


U64P = ctypes.POINTER(ctypes.c_uint64)


class Consts(ctypes.Structure):
    _fields_ = [("n", ctypes.c_int), ("FULLW", U64P), ("NB", U64P), ("NIN", U64P), ("NOUT", U64P),
                ("DEG", ctypes.POINTER(ctypes.c_int)), ("CS", ctypes.POINTER(U64P)), ("VF", ctypes.POINTER(U64P))]


_loaded: dict = {}
_lock = threading.Lock()


def build(ops_src: str, W: int, debug: bool = False) -> ctypes.CDLL:
    cc = compiler()
    if cc is None:
        raise RuntimeError("no C compiler found (set CC)")
    cdir = c_dir()
    rt, eng = (cdir / "dsl_rt.h").read_text(), (cdir / "dsl_engine.h").read_text()
    flags = DEBUG_CFLAGS if debug else CFLAGS
    src = f"#define W {W}\n#include \"dsl_rt.h\"\n{ops_src}\n#include \"dsl_engine.h\"\n"
    h = hashlib.sha256("\0".join([ENGINE_VERSION, src, rt, eng, _ident(cc), " ".join(flags)]).encode()).hexdigest()[:24]
    with _lock:
        if h in _loaded:
            return _loaded[h]
        d = cache_dir() / h
        lib = d / "lib.so"
        if not lib.exists():
            d.mkdir(parents=True, exist_ok=True)
            with open(d / ".lock", "w") as lk:
                fcntl.flock(lk, fcntl.LOCK_EX)
                if not lib.exists():
                    (d / "gen.c").write_text(src)
                    tmp = d / f"lib.{os.getpid()}.tmp"
                    r = subprocess.run([cc, *flags, f"-I{cdir}", "-o", str(tmp), str(d / "gen.c")],
                                       capture_output=True, text=True)
                    (d / "compile.log").write_text(r.stdout + r.stderr)
                    if r.returncode != 0:
                        raise RuntimeError(f"compilation failed; see {d / 'compile.log'}:\n{r.stderr[:3000]}")
                    os.replace(tmp, lib)
        so = ctypes.CDLL(str(lib))
        so.dsl_solve.argtypes = [ctypes.POINTER(Consts), ctypes.POINTER(Params), ctypes.POINTER(Result)]
        so.dsl_solve.restype = ctypes.c_int
        so.dsl_stop.argtypes, so.dsl_stop.restype = [], None
        so._kpw_dir = str(d)
        _loaded[h] = so
        return so


def _words(mask: int, W: int):
    return [(mask >> (64 * i)) & 0xFFFFFFFFFFFFFFFF for i in range(W)]


def run(so, g, W: int, cset_order, vfun_order, time_limit=None, max_states=None):
    """Call dsl_solve on GData g.  Runs in a worker thread so that Ctrl-C can stop it."""
    n = g.n
    arr = lambda vals, t=ctypes.c_uint64: (t * max(1, len(vals)))(*vals)
    keep = []
    def rows(masks):
        a = arr([w for m in masks for w in _words(m, W)])
        keep.append(a)
        return ctypes.cast(a, U64P)
    full = rows([g.full])
    nb, nin, nout = rows(g.nb), rows(g.nin), rows(g.nout)
    deg = (ctypes.c_int * max(1, n))(*[m.bit_count() for m in g.nb])
    cs = [rows([g.csets[c]]) for c in cset_order]
    vf = [rows(g.vfuns[v]) for v in vfun_order]
    CS = (U64P * max(1, len(cs)))(*cs)
    VF = (U64P * max(1, len(vf)))(*vf)
    K = Consts(n, full, nb, nin, nout, deg, CS, VF)
    P = Params(time_limit or 0.0, float(max_states or 0))
    order = (ctypes.c_int * max(1, n))()
    R = Result(); R.order = order
    box = {}
    t = threading.Thread(target=lambda: box.setdefault("rc", so.dsl_solve(ctypes.byref(K), ctypes.byref(P), ctypes.byref(R))))
    t.start()
    try:
        while t.is_alive():
            t.join(0.1)
    except KeyboardInterrupt:
        so.dsl_stop()
        t.join()
    return R, list(order[:n])
