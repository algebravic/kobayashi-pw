"""Lowering of a Problem's IR to C (the per-problem ops included by the engine).

Sets are W-word bitsets.  A set expression built from S, constants, N(v),
singletons, maintained sets and the Boolean operations is lowered *word-wise*
(a C expression of the word index); anything else (bigunion that is not
maintained, comprehensions) is materialised into a temporary.  Scalars are
lowered to C expressions with temporaries; nodes that depend only on the state
S are hoisted out of the move loop.
"""
from __future__ import annotations

from .ir import BINDERS, FULL, Node, SET, SEQ, INT, BOOL, VERT, walk

WI = "@W@"     # placeholder for the word index in word templates


class CodegenError(Exception):
    pass


class Lowerer:
    def __init__(self, prob, maintained: dict):
        self.p = prob
        self.maint = maintained           # Node -> field index
        self.lines: list[str] = []
        self.ind = 1
        self.cache: list[dict] = [{}]
        self.env: dict = {}               # var name -> C (for sets: (array, mt) ; for vertices: int var)
        self.tmp = 0
        self.cset_idx = {c: i for i, c in enumerate(prob.const_order)}
        self.vfun_idx = {v: i for i, v in enumerate(prob.vfun_order)}

    # ------------------------------------------------------------ utils
    def emit(self, s: str):
        self.lines.append("    " * self.ind + s)

    def new(self, prefix="t"):
        self.tmp += 1
        return f"{prefix}{self.tmp}"

    def lookup(self, node):
        for c in reversed(self.cache):
            if node in c:
                return c[node]
        return None

    def store(self, node, val):
        self.cache[-1][node] = val
        return val

    def push(self):
        self.cache.append({})
        self.ind += 1

    def pop(self):
        self.cache.pop()
        self.ind -= 1

    # ------------------------------------------------------------ sets
    def word(self, node) -> str:
        """Word template (with WI placeholder) for a set expression."""
        op, a = node.op, node.args
        hit = self.lookup(node)
        if hit is not None and hit[0] == "w":
            return hit[1]
        if op == "var":
            arr, _ = self.env[a[0]]
            return f"{arr}[{WI}]"
        if op == "full":
            return f"K->FULLW[{WI}]"
        if op == "empty":
            return "0ULL"
        if op == "or":
            return f"({self.word(a[0])} | {self.word(a[1])})"
        if op == "and":
            return f"({self.word(a[0])} & {self.word(a[1])})"
        if op == "sub":
            if a[0] is FULL:
                return f"(K->FULLW[{WI}] & ~{self.word(a[1])})"
            return f"({self.word(a[0])} & ~{self.word(a[1])})"
        if op == "single":
            v = self.int(a[0])
            return f"((({WI}) == (({v}) >> 6)) ? (1ULL << (({v}) & 63)) : 0ULL)"
        if op in ("N", "Nin", "Nout"):
            v = self.int(a[0])
            arr = {"N": "NB", "Nin": "NIN", "Nout": "NOUT"}[op]
            return f"K->{arr}[({v}) * W + {WI}]"
        if op == "cset":
            return f"K->CS[{self.cset_idx[a[0]]}][{WI}]"
        if op == "vfun":
            v = self.int(a[1])
            return f"K->VF[{self.vfun_idx[a[0]]}][({v}) * W + {WI}]"
        if op == "bigunion" and node in self.maint and self.maint_bound(node):
            _, mt = self.env[a[0].args[0]]
            return f"{mt}->m{self.maint[node]}[{WI}]"
        # materialise
        t = self.new("ts")
        self.emit(f"u64 {t}[W];")
        self.materialise(node, t)
        self.store(node, ("w", f"{t}[{WI}]"))
        return f"{t}[{WI}]"

    def family_read(self, x):
        """|F(e) ∩ S| with a maintained counter family for F → mt->cK[e]."""
        fams = self.p.families
        if not fams or x.op != "and":
            return None
        Fn, Sv = x.args
        if Fn.op in fams and Sv.op == "var" and Sv.args[0] == self.p.S_name:
            arr, mt = self.env.get(Sv.args[0], (None, None))
            if mt is not None:
                return f"{mt}->c{fams.index(Fn.op)}[{self.int(Fn.args[0])}]"
        return None

    def maint_bound(self, node):
        a0 = node.args[0]
        return a0.op == "var" and self.env.get(a0.args[0], (None, None))[1] is not None

    def materialise(self, node, t):
        op, a = node.op, node.args
        if op == "bigunion":
            fn = a[1]
            if fn in ("N", "Nin", "Nout"):
                row = {"N": "K->NB", "Nin": "K->NIN", "Nout": "K->NOUT"}[fn]
            else:
                row = f"K->VF[{self.vfun_idx[fn]}]"
            self.emit(f"for (int w = 0; w < W; w++) {t}[w] = 0;")
            u = self.new("u")
            def body():
                self.emit(f"for (int w = 0; w < W; w++) {t}[w] |= {row}[{u} * W + w];")
            self.foreach(a[0], u, body)
            return
        if op == "filter":
            dom, var, pred = a
            self.emit(f"for (int w = 0; w < W; w++) {t}[w] = 0;")
            u = self.new("u")
            def body():
                self.env[var.args[0]] = u
                c = self.bool(pred)
                self.emit(f"if ({c}) {t}[{u} >> 6] |= 1ULL << ({u} & 63);")
            self.foreach(dom, u, body)
            return
        raise CodegenError(f"cannot lower set expression {op} to C")

    def foreach(self, setnode, u, body, label=None):
        """for u in bits(setnode): body()  (u is a fresh C int)."""
        tmpl = self.word(setnode)
        w, m = self.new("w"), self.new("m")
        self.emit(f"for (int {w} = 0; {w} < W; {w}++) {{")
        self.ind += 1
        self.emit(f"u64 {m} = {tmpl.replace(WI, w)};")
        self.emit(f"while ({m}) {{")
        self.push()
        self.emit(f"int {u} = {w} * 64 + __builtin_ctzll({m}); {m} &= {m} - 1;")
        body()
        self.pop()
        self.emit("}")
        self.ind -= 1
        self.emit("}")

    # ------------------------------------------------------------ seqs
    def foreach_seq(self, node, u, body):
        """Iterate a Seq node in increasing vertex order (with take limits)."""
        if node.op == "seq":
            dom, var, pred = node.args
            def b():
                self.env[var.args[0]] = u
                c = self.bool(pred)
                self.emit(f"if (!({c})) continue;")
                body()
            self.foreach(dom, u, b)
            return
        if node.op == "take":
            k = self.int(node.args[1])
            cnt, done = self.new("cnt"), self.new("L")
            self.emit(f"int {cnt} = 0;")
            def b():
                self.emit(f"if ({cnt} >= {k}) goto {done};")
                self.emit(f"{cnt}++;")
                body()
            self.foreach_seq(node.args[0], u, b)
            self.emit(f"{done}:;")
            return
        raise CodegenError(f"cannot iterate {node.op}")

    # ------------------------------------------------------------ scalars
    def int(self, node) -> str:
        hit = self.lookup(node)
        if hit is not None:
            return hit[1] if isinstance(hit, tuple) else hit
        op, a = node.op, node.args
        if op == "var":
            return self.env[a[0]]
        if op == "int":
            return str(a[0])
        if op == "bool":
            return "1" if a[0] else "0"
        simple = {"add": "+", "isub": "-", "mul": "*", "lt": "<", "le": "<=", "eq": "=="}
        if op in simple:
            return self.store(node, self.scalar(f"({self.int(a[0])} {simple[op]} {self.int(a[1])})"))
        if op == "fdiv":
            return self.store(node, self.scalar(f"fdiv({self.int(a[0])}, {self.int(a[1])})"))
        if op in ("min", "max"):
            x, y = self.int(a[0]), self.int(a[1])
            cmp = "<" if op == "min" else ">"
            return self.store(node, self.scalar(f"(({x}) {cmp} ({y}) ? ({x}) : ({y}))"))
        if op == "where":
            return self.store(node, self.scalar(f"(({self.int(a[0])}) ? ({self.int(a[1])}) : ({self.int(a[2])}))"))
        if op == "not":
            return self.store(node, self.scalar(f"(!{self.int(a[0])})"))
        if op in ("land", "lor"):
            # short-circuit: evaluate the right side only if needed
            x = self.int(a[0])
            r = self.new()
            self.emit(f"int {r} = {x};")
            self.emit(f"if ({'' if op == 'land' else '!'}{r}) {{")
            self.push()
            y = self.int(a[1])
            self.emit(f"{r} = {y};")
            self.pop()
            self.emit("}")
            return self.store(node, r)
        if op == "odd":
            return self.store(node, self.scalar(f"(({self.int(a[0])}) & 1)"))
        if op == "deg":
            return self.store(node, self.scalar(f"K->DEG[{self.int(a[0])}]"))
        if op == "card":
            x = a[0]
            fam = self.family_read(x)
            if fam is not None:
                return self.store(node, fam)
            if x.type == SET:
                tmpl = self.word(x)
                r = self.new("c")
                self.emit(f"int {r} = 0;")
                self.emit(f"for (int w = 0; w < W; w++) {r} += __builtin_popcountll({tmpl.replace(WI, 'w')});")
                return self.store(node, r)
            r = self.new("c")
            self.emit(f"int {r} = 0;")
            u = self.new("u")
            self.foreach_seq(x, u, lambda: self.emit(f"{r}++;"))
            return self.store(node, r)
        if op == "member":
            v = self.int(a[0])
            tmpl = self.word(a[1])
            r = self.new("b")
            self.emit(f"int {r} = (int)(({tmpl.replace(WI, f'(({v}) >> 6)')} >> (({v}) & 63)) & 1);")
            return self.store(node, r)
        if op == "subset":
            ta, tb = self.word(a[0]), self.word(a[1])
            r = self.new("b")
            self.emit(f"int {r} = 1;")
            self.emit(f"for (int w = 0; w < W; w++) if ({ta.replace(WI, 'w')} & ~{tb.replace(WI, 'w')}) {{ {r} = 0; break; }}")
            return self.store(node, r)
        if op == "cut":
            ta = self.word(a[0])
            r, u = self.new("c"), self.new("u")
            self.emit(f"int {r} = 0;")
            self.foreach(a[0], u, lambda: self.emit(
                f"for (int w = 0; w < W; w++) {r} += __builtin_popcountll(K->NB[{u} * W + w] & ~{ta.replace(WI, 'w')});"))
            return self.store(node, r)
        if op in ("sum", "forall", "exists"):
            dom, var, body = a
            r, u = self.new("r"), self.new("u")
            init = {"sum": "0", "forall": "1", "exists": "0"}[op]
            self.emit(f"int {r} = {init};")
            done = self.new("L")
            def b():
                self.env[var.args[0]] = u
                c = self.int(body)
                if op == "sum":
                    self.emit(f"{r} += {c};")
                elif op == "forall":
                    self.emit(f"if (!({c})) {{ {r} = 0; goto {done}; }}")
                else:
                    self.emit(f"if ({c}) {{ {r} = 1; goto {done}; }}")
            self.foreach(dom, u, b)
            self.emit(f"{done}:;")
            return self.store(node, r)
        raise CodegenError(f"cannot lower {op} to C")

    bool = int

    def scalar(self, expr):
        r = self.new()
        self.emit(f"int {r} = {expr};")
        return r


def _closure_trigger_ok(prob, pred):
    """S occurs in pred only inside N(v) ∩ S (so pred changes only when a neighbour is added)."""
    S, v = prob.S.node, prob.v.node
    ok_nodes = {Node("and", (Node("N", (v,), SET), S), SET), Node("and", (S, Node("N", (v,), SET)), SET)}
    def scan(n):
        if n in ok_nodes:
            return True
        if n is S:
            return False
        return all(scan(x) for x in n.args if isinstance(x, Node))
    return scan(pred)


def generate(prob) -> str:
    """C source of the ops for prob (to be compiled with dsl_rt.h / dsl_engine.h)."""
    p = prob
    maint = {m: i for i, m in enumerate(p.maintained)}
    nm = len(maint)
    out = []
    out.append(f"/* generated from problem {p.name!r}; do not edit */")
    fams = p.families
    inplace = bool(fams)
    out.append("typedef struct { u64 m[1]; " + " ".join(f"u64 m{i}[W];" for i in range(nm))
               + " ".join(f"int c{i}[64 * W];" for i in range(len(fams))) + " } Mt;")
    REV = {"N": "K->NB", "Nin": "K->NOUT", "Nout": "K->NIN"}   # u ∈ F(w)  ⇔  w ∈ REV_F(u)

    def fn(sig, build):
        L = Lowerer(p, maint)
        build(L)
        return [sig + " {"] + L.lines + ["}"]

    # mt_init / st_add
    def b_init(L):
        L.emit("(void)S; (void)K; (void)mt;")
        for m, i in maint.items():
            F = m.args[1]
            row = {"N": "K->NB", "Nin": "K->NIN", "Nout": "K->NOUT"}.get(F, f"K->VF[{L.vfun_idx.get(F, 0)}]")
            L.emit(f"for (int w = 0; w < W; w++) mt->m{i}[w] = 0;")
            L.emit("for (int w = 0; w < W; w++) { u64 q = S[w]; while (q) { int u = w * 64 + __builtin_ctzll(q); q &= q - 1;")
            L.emit(f"    for (int z = 0; z < W; z++) mt->m{i}[z] |= {row}[u * W + z]; }} }}")
        for i, F in enumerate(fams):
            L.emit(f"for (int z = 0; z < K->n; z++) mt->c{i}[z] = 0;")
            L.emit("for (int w = 0; w < W; w++) { u64 q = S[w]; while (q) { int u = w * 64 + __builtin_ctzll(q); q &= q - 1;")
            L.emit(f"    for (int z = 0; z < W; z++) {{ u64 r = {REV[F]}[u * W + z]; while (r) {{ mt->c{i}[z * 64 + __builtin_ctzll(r)]++; r &= r - 1; }} }} }} }}")
    out += fn("static inline void mt_init(const u64 *S, Mt *mt, const Consts *K)", b_init)

    def b_add(L):
        L.emit("(void)K; (void)mt;")
        L.emit("S[u >> 6] |= 1ULL << (u & 63);")
        for m, i in maint.items():
            F = m.args[1]
            row = {"N": "K->NB", "Nin": "K->NIN", "Nout": "K->NOUT"}.get(F, f"K->VF[{L.vfun_idx.get(F, 0)}]")
            L.emit(f"for (int w = 0; w < W; w++) mt->m{i}[w] |= {row}[u * W + w];")
        for i, F in enumerate(fams):
            L.emit(f"for (int z = 0; z < W; z++) {{ u64 r = {REV[F]}[u * W + z]; while (r) {{ mt->c{i}[z * 64 + __builtin_ctzll(r)]++; r &= r - 1; }} }}")
    out += fn("static inline void st_add(u64 *S, Mt *mt, int u, const Consts *K)", b_add)
    def b_del(L):
        L.emit("(void)K; (void)mt;")
        L.emit("S[u >> 6] &= ~(1ULL << (u & 63));")
        for i, F in enumerate(fams):
            L.emit(f"for (int z = 0; z < W; z++) {{ u64 r = {REV[F]}[u * W + z]; while (r) {{ mt->c{i}[z * 64 + __builtin_ctzll(r)]--; r &= r - 1; }} }}")
    out += fn("static inline void st_del(u64 *S, Mt *mt, int u, const Consts *K)", b_del)

    # closure
    trig = all(_closure_trigger_ok(p, c.pred) for c in p.closures) and p.ann.get("closure", "auto") != "sweep"
    def b_clo(L):
        L.env[p.S_name] = ("T", "mt")
        L.emit("(void)K; (void)mt; (void)cand;")
        if not p.closures:
            L.emit("return nr;")
            return
        def test_and_add(v):
            L.env[p.v_name] = v
            r = L.new("ok")
            L.emit(f"int {r} = 0;")
            for c in p.closures:
                L.emit(f"if (!{r}) {{")
                L.push()
                x = L.bool(c.pred)
                L.emit(f"{r} = {x};")
                L.pop()
                L.emit("}")
            return r
        if trig:
            L.emit("for (;;) {")
            L.ind += 1
            L.emit("int v = -1;")
            L.emit("for (int w = 0; w < W; w++) if (cand[w]) { v = w * 64 + __builtin_ctzll(cand[w]); cand[w] &= cand[w] - 1; break; }")
            L.emit("if (v < 0) break;")
            L.emit("if (T[v >> 6] >> (v & 63) & 1) continue;")
            L.push()
            r = test_and_add("v")
            L.emit(f"if ({r}) {{ st_add(T, mt, v, K); if (rec) rec[nr] = v; nr++;")
            L.emit("    for (int w = 0; w < W; w++) cand[w] |= K->NB[v * W + w] & ~T[w]; }")
            L.pop()
            L.ind -= 1
            L.emit("}")
        else:
            L.emit("for (;;) {")
            L.ind += 1
            L.emit("int ch = 0;")
            u = "v"
            def body():
                L.emit(f"if (T[{u} >> 6] >> ({u} & 63) & 1) continue;")
                r = test_and_add(u)
                L.emit(f"if ({r}) {{ st_add(T, mt, {u}, K); if (rec) rec[nr] = {u}; nr++; ch = 1; }}")
            # sweep over V ∖ T (re-evaluated per word)
            L.emit("for (int w0 = 0; w0 < W; w0++) {")
            L.ind += 1
            L.emit("u64 m0 = K->FULLW[w0] & ~T[w0];")
            L.emit("while (m0) {")
            L.push()
            L.emit("int v = w0 * 64 + __builtin_ctzll(m0); m0 &= m0 - 1;")
            body()
            L.pop()
            L.emit("}")
            L.ind -= 1
            L.emit("}")
            L.emit("if (!ch) break;")
            L.ind -= 1
            L.emit("}")
        L.emit("return nr;")
    out += fn("static inline int closure(u64 *T, Mt *mt, const Consts *K, u64 *cand, int *rec, int nr)", b_clo)
    out.append(f"#define CLOSURE_WORKLIST {1 if trig else 0}")

    # key
    def b_key(L):
        L.env[p.S_name] = ("T", None)
        L.emit("(void)K;")
        t = L.word(p.key_node)
        L.emit(f"for (int w = 0; w < W; w++) key[w] = {t.replace(WI, 'w')};")
    out += fn("static inline void make_key(const u64 *T, u64 *key, const Consts *K)", b_key)
    out.append(f"#define KEY_IDENTITY {1 if p.key_node is p.S.node else 0}")

    # move application shared by expand and replay
    def apply_move(L, rec, inplace=False):
        """T, mt2 := apply(S, x) (copy mode), or apply to (T, mt2) == (S, mt) in place
        (inplace: the caller undoes rec[0..nr)).  The prefix is collected first,
        on the unmodified state, then added."""
        if not inplace:
            L.emit("for (int w = 0; w < W; w++) T[w] = S[w];")
            L.emit("mt2 = *mt;")
        L.emit("for (int w = 0; w < W; w++) cand[w] = 0;")
        L.emit("nr = 0;")
        keep = rec or inplace
        def add(u):
            L.emit(f"st_add(T, &mt2, {u}, K);")
            L.emit(f"rec[nr++] = {u};" if keep else "nr++;")
            if trig:
                L.emit(f"for (int w = 0; w < W; w++) cand[w] |= K->NB[({u}) * W + w];")
        if p.move.prefix is not None:
            u = L.new("u")
            L.emit("int npre = 0;")
            L.foreach_seq(p.move.prefix, u, lambda: L.emit(f"pre[npre++] = {u};"))
            L.emit("for (int k = 0; k < npre; k++) {")
            L.ind += 1
            add("pre[k]")
            L.ind -= 1
            L.emit("}")
        add("x")
        L.emit("for (int w = 0; w < W; w++) cand[w] &= ~T[w];")
        L.emit(f"nr = closure(T, &mt2, K, cand, {'rec' if keep else 'NULL'}, nr);")

    hoist_exprs = [p.move.over] + list(p.choice_filters) + ([p.move.cost] if p.move.cost is not None else [p.derived_cost])
    if p.move.prefix is not None:
        hoist_exprs.append(p.move.prefix)

    def hoist(L):
        S = p.S_name
        seen = set()
        def visit(n):
            if id(n) in seen or not isinstance(n, Node):
                return
            seen.add(id(n))
            if n.free and n.free <= {S} and n.type in (INT, BOOL) and n.op not in ("var", "int", "bool"):
                L.int(n)
                return
            for x in n.args:
                if isinstance(x, Node):
                    visit(x)
        for e in hoist_exprs:
            visit(e)

    probe = p.ann.get("probe", False) and p.key_node is p.S.node and p.move.prefix is None

    def b_expand(L):
        L.emit("const Consts *K = E->K;")
        L.emit("int next = INT_MAX; u64 T[W], key[W], cand[W]; int nr = 0; (void)nr;")
        L.emit("int pre[64 * W]; (void)pre;")
        if inplace:
            # one copy per expansion; moves are applied to (T, mt2) and undone
            L.emit("Mt mt2 = *mt; int rec[64 * W];")
            L.emit("for (int w = 0; w < W; w++) T[w] = S[w];")
            L.env[p.S_name] = ("T", "(&mt2)")
        else:
            L.emit("Mt mt2;")
            L.env[p.S_name] = ("S", "mt")
        hoist(L)
        def body():
            L.env[p.x_name] = "x"
            for f in p.choice_filters:
                c = L.bool(f)
                L.emit(f"if (!({c})) continue;")
            cost = p.move.cost if p.move.cost is not None else p.derived_cost
            c = L.int(cost)
            L.emit(f"int cst = {c};")
            L.emit("if (cst <= lo) continue;")
            L.emit("if (cst > B) { if (cst < next) next = cst; continue; }")
            if probe:
                L.emit("for (int w = 0; w < W; w++) T[w] = S[w];")
                L.emit("T[x >> 6] |= 1ULL << (x & 63);")
                L.emit("if (eng_lookup(E, T)) continue;")
            if inplace:
                L.emit("{")
                L.ind += 1
                apply_move(L, rec=False, inplace=True)
                L.emit("make_key(T, key, K);")
                L.emit("int full = is_full(T, K);")
                L.emit("for (int k = nr; k-- > 0;) st_del(T, &mt2, rec[k], K);")
                L.emit("if (eng_offer(E, key, id, x, full)) return -1;")
                L.ind -= 1
                L.emit("}")
            else:
                apply_move(L, rec=False)
                L.emit("make_key(T, key, K);")
                L.emit("if (eng_offer(E, key, id, x, is_full(T, K))) return -1;")
        L.foreach(p.move.over_minus_S, "x", body)
        L.emit("return next;")
    out += fn("static int expand(Eng *E, uint32_t id, const u64 *S, const Mt *mt, int lo, int B)", b_expand)

    def b_replay(L):
        L.env[p.S_name] = ("S", "mt")
        L.env[p.x_name] = "x"
        L.emit("u64 T[W], cand[W]; Mt mt2; int nr = 0; int pre[64 * W]; (void)pre;")
        apply_move(L, rec=True)
        L.emit("return nr;")
    out += fn("static int replay(const u64 *S, const Mt *mt, int x, int *rec, const Consts *K)", b_replay)
    return "\n".join(out) + "\n"
