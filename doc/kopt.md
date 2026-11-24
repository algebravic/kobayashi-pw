# C optimiser (kopt) and work-model features

- **`src/C/kopt.c` (new).** The exact Pareto-label optimisation of `orders.optimize`, in C, on a DAG file:
  - models `v2`, `v7` and `loglin` (the predicted-work model);
  - `-L` bounds the labels per node;
  - it gives the same orderings as `optimize` on the square-sum graphs, and is about 50× faster.
- **`orders.py`.**
  - `WORK_FEATURES`, `work_features(f, n)` and `make_model_loglin(beta, n)`: the features and model of the hamiltonian repo's fitted work model, defined here once so that the fit, `optimize` and `kopt` agree;
  - `find_kopt()`;
  - `optimize_file(path, cost, ...)`, which runs kopt and returns an `OptResult`.
- **`tests/test_kopt.py` (new).** kopt against `optimize` and against brute-force enumeration of DAG paths on random graphs (with and without `-g`), plus the truncation flag and argument errors.
- **Makefile.** A `kopt` target, included in `all`.

Usage, timings and memory are in the README section on kopt. A label occupies 24 bytes (cost, p, back-pointer, vertex); all fronts are kept for the traceback.
