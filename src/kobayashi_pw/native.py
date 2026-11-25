"""Compiled programs (kpw, kpw2, kopt, kcw, bab, fullcount), built on first use.

``program(name, n)`` returns the path of an executable, compiling it from the
C sources if needed.  The sources are found in (first match):

1. ``$KPW_ENGINE``;
2. ``kobayashi_pw/_csrc`` inside an installed wheel (pyproject.toml maps
   ``src/C`` there);
3. ``src/C`` next to the package in a source tree or editable install.

Binaries are cached in ``$KPW_CACHE/bin/<key>/<name>`` (default
``~/.cache/kobayashi_pw``).  The key is a SHA-256 of the program's source and
every header in the source directory, the word count W, the compiler flags,
``cc --version`` and the machine type, so an edited source or a different
compiler gives a new build and a stale binary is never used.  Compilation
takes a file lock and renames atomically, so concurrent processes are safe.

``$KPW_BIN_<NAME>`` (e.g. ``KPW_BIN_KPW2``) names a binary to use instead.
The DSL's JIT (dsl/jit.py) uses the same source directory and compiler.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

CFLAGS = ["-O3", "-march=native", "-Wall", "-Wextra"]
W_BUCKETS = (1, 2, 3, 4, 8, 16)            # n <= 64 W; kpw2/kopt are built per bucket


@dataclass(frozen=True)
class Prog:
    source: str
    extra: tuple[str, ...] = ()            # flags after the defaults
    libs: tuple[str, ...] = ()             # linker flags at the end
    takes_w: bool = False                  # compiled with -DW=k
    nmax: int | None = None                # fixed vertex limit (None: 64 W)


PROGRAMS: dict[str, Prog] = {
    "kpw": Prog("kpw.c", nmax=64),
    "kpw2": Prog("kpw2.c", extra=("-pthread",), takes_w=True),
    "kopt": Prog("kopt.c", libs=("-lm",), takes_w=True),
    "kcw": Prog("kcw.c"),
    "bab": Prog("bab.c"),
    "fullcount": Prog("fullcount.c"),
}


class NativeUnavailable(RuntimeError):
    """No C compiler, no sources, or a failed compilation."""


# ---------------------------------------------------------------------------
# Locations and compiler
# ---------------------------------------------------------------------------

def c_dir() -> Path:
    """Directory holding the C sources and headers."""
    env = os.environ.get("KPW_ENGINE")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parent
    packaged = here / "_csrc"
    if packaged.is_dir():
        return packaged
    return here.parent / "C"


def cache_dir() -> Path:
    return Path(os.environ.get("KPW_CACHE", Path.home() / ".cache" / "kobayashi_pw"))


def compiler() -> str | None:
    for c in (os.environ.get("CC"), "cc", "gcc", "clang"):
        if c and shutil.which(c):
            return c
    return None


_ident_cache: dict[str, str] = {}


def compiler_ident(cc: str) -> str:
    if cc not in _ident_cache:
        try:
            _ident_cache[cc] = subprocess.run([cc, "--version"], capture_output=True, text=True).stdout
        except OSError:
            _ident_cache[cc] = cc
    return _ident_cache[cc]


def w_bucket(n: int | None, default: int = 2) -> int:
    """Words per vertex set for n vertices (default when n is unknown)."""
    if n is None:
        return default
    need = max(1, (n + 63) // 64)
    for w in W_BUCKETS:
        if w >= need:
            return w
    raise ValueError(f"n = {n} exceeds {64 * W_BUCKETS[-1]}")


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------

def _key(name: str, p: Prog, src: Path, W: int | None, cc: str, flags: list[str]) -> str:
    h = hashlib.sha256()
    for part in (name, src.read_text(), W, " ".join(flags), compiler_ident(cc), platform.machine(),
                 sys.platform):
        h.update(str(part).encode() + b"\0")
    for hdr in sorted(src.parent.glob("*.h")):
        h.update(hdr.name.encode() + b"\0" + hdr.read_bytes() + b"\0")
    return h.hexdigest()[:24]


def program(name: str, n: int | None = None, *, explicit: str | None = None) -> str:
    """Path of program ``name``, able to handle n vertices; compiled if needed.

    Raises NativeUnavailable if it cannot be provided."""
    if explicit:
        if not (os.path.isfile(explicit) and os.access(explicit, os.X_OK)):
            raise NativeUnavailable(f"{explicit} is not an executable file")
        return explicit
    env = os.environ.get(f"KPW_BIN_{name.upper()}")
    if env:
        return program(name, n, explicit=env)
    if name not in PROGRAMS:
        raise ValueError(f"unknown program {name!r}; known: {sorted(PROGRAMS)}")
    p = PROGRAMS[name]
    if p.nmax is not None and n is not None and n > p.nmax:
        raise NativeUnavailable(f"{name} handles at most {p.nmax} vertices (n = {n})")
    src = c_dir() / p.source
    if not src.is_file():
        raise NativeUnavailable(f"C source {src} not found (set KPW_ENGINE to the directory of the C sources)")
    cc = compiler()
    if cc is None:
        raise NativeUnavailable(f"no C compiler found to build {name} (set CC)")
    W = w_bucket(n) if p.takes_w else None
    flags = CFLAGS + list(p.extra) + ([f"-DW={W}"] if W is not None else [])
    d = cache_dir() / "bin" / _key(name, p, src, W, cc, flags)
    exe = d / name
    if exe.exists():
        return str(exe)
    d.mkdir(parents=True, exist_ok=True)
    with open(d / ".lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        if not exe.exists():
            tmp = d / f"{name}.{os.getpid()}.tmp"
            cmd = [cc, *flags, f"-I{src.parent}", "-o", str(tmp), str(src), *p.libs]
            r = subprocess.run(cmd, capture_output=True, text=True)
            (d / "compile.log").write_text(" ".join(cmd) + "\n" + r.stdout + r.stderr)
            if r.returncode != 0:
                raise NativeUnavailable(f"compiling {name} failed; see {d / 'compile.log'}:\n{r.stderr[:2000]}")
            os.replace(tmp, exe)
    return str(exe)


def try_program(name: str, n: int | None = None, *, explicit: str | None = None) -> str | None:
    """``program``, or None if it cannot be provided (callers with a Python fallback)."""
    try:
        return program(name, n, explicit=explicit)
    except NativeUnavailable:
        return None


def main(argv: list[str] | None = None) -> int:
    """kobayashi-pw-build: compile the programs ahead of time."""
    import argparse
    ap = argparse.ArgumentParser(description="Compile kobayashi-pw's C programs into the cache.")
    ap.add_argument("--n", type=int, action="append",
                    help="vertex counts to build W-dependent programs for (repeatable; default 64 and 128)")
    ap.add_argument("programs", nargs="*", default=sorted(PROGRAMS))
    a = ap.parse_args(argv)
    ns = a.n or [64, 128]
    rc = 0
    for name in a.programs:
        targets = sorted({w_bucket(n) * 64 for n in ns}) if PROGRAMS[name].takes_w else [None]
        for n in targets:
            try:
                path = program(name, n)
                print(f"{name:10s} n<={n if n else PROGRAMS[name].nmax or '-'}: {path}")
            except NativeUnavailable as e:
                print(f"{name:10s} FAILED: {e}", file=sys.stderr)
                rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
