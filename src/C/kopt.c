/* kopt.c -- exact secondary-cost optimisation over a kpw DAG file.
 *
 * C port of kobayashi_pw.orders.optimize (Pareto labels (cost, p) per node,
 * exact because the cost-to-go is nondecreasing in p).  Reads a DAG written by
 * `kpw -c -o` / `kpw2 -c -o` (formats KPWDAG1-3, doc/dag_format.md),
 * recomputes the arcs exactly as OrderDAG.load does (same expansion order, so
 * the same blocks and the same step features), and prints the optimal
 * ordering in the frontier-DP (tau) direction.
 *
 * Models (per tau step, features as in orders.tau_block_features):
 *   -m v2    a = 2^nb (fw/pw)^2 + 0.001 fw,  e = 0,  k = 0             (additive)
 *   -m v7    hampath _dp_cost; -b expand_base (1.55), -a density_alpha (0.25)
 *   -m loglin  predicted DP work:  a = 0, e = 2^nb, k = exp(beta . x) / 2^nb,
 *            x = orders.WORK_FEATURES (11 values); -B b0,b1,...,b10
 * applied as   cost += a + p e;   p <- max(p e k, 1)   (p starts at 1).
 *
 * Usage: kopt -m MODEL [-b C] [-a A] [-B list] [-L max_labels] [-q] DAGFILE
 * Output: one line "kopt: ..." with n, pw, nodes, arcs, max_labels, exact,
 * cost (%.17g) and time; then "order: v1 v2 ..." (names from the file).
 *
 * Build: cc -O3 -march=native -o kopt kopt.c -lm        (n <= 128; -DW=k for n <= 64k)
 */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifndef W
#define W 2
#endif
#define NMAX (64 * W)

typedef uint64_t u64;
typedef struct { u64 w[W]; } bs;

static inline bs bzero_(void) { bs r; memset(&r, 0, sizeof r); return r; }
static inline bs bor(bs a, bs b) { for (int i = 0; i < W; i++) a.w[i] |= b.w[i]; return a; }
static inline bs band(bs a, bs b) { for (int i = 0; i < W; i++) a.w[i] &= b.w[i]; return a; }
static inline bs bandn(bs a, bs b) { for (int i = 0; i < W; i++) a.w[i] &= ~b.w[i]; return a; }
static inline int beq(bs a, bs b) { for (int i = 0; i < W; i++) if (a.w[i] != b.w[i]) return 0; return 1; }
static inline int bnone(bs a) { for (int i = 0; i < W; i++) if (a.w[i]) return 0; return 1; }
static inline int bpop(bs a) { int c = 0; for (int i = 0; i < W; i++) c += __builtin_popcountll(a.w[i]); return c; }
static inline int btest(bs a, int x) { return (a.w[x >> 6] >> (x & 63)) & 1; }
static inline void bset(bs *a, int x) { a->w[x >> 6] |= 1ULL << (x & 63); }
static inline int bnext(bs a, int x) {
    int i = (x + 1) >> 6, s = (x + 1) & 63;
    if (i >= W) return -1;
    u64 m = a.w[i] & (s ? ~0ULL << s : ~0ULL);
    for (;;) {
        if (m) return i * 64 + __builtin_ctzll(m);
        if (++i >= W) return -1;
        m = a.w[i];
    }
}
#define FOR(x, m) for (int x = bnext((m), -1); x >= 0; x = bnext((m), x))
static inline u64 bhash(bs a) {
    u64 h = a.w[0];
    for (int i = 1; i < W; i++) h = (h ^ (h >> 31)) * 0x9e3779b97f4a7c15ULL ^ a.w[i];
    h ^= h >> 33; h *= 0xff51afd7ed558ccdULL; h ^= h >> 33;
    return h;
}

static void die(const char *m) { fprintf(stderr, "kopt: %s\n", m); exit(2); }
static void *xmalloc(size_t n) { void *p = malloc(n ? n : 1); if (!p) die("out of memory"); return p; }
static void *xrealloc(void *p, size_t n) { p = realloc(p, n ? n : 1); if (!p) die("out of memory"); return p; }

/* ---------------- graph ---------------- */
static int n, pw, greedy2;
static bs nin[NMAX], full;
static char **names;

static bs union_nin(bs U) { bs r = bzero_(); FOR(u, U) r = bor(r, nin[u]); return r; }

/* orders/core.expand, same order of added vertices */
static int expand(bs *U, bs *nb, int *added) {
    int na = 0;
    for (;;) {
        bs closed = bor(*U, *nb);
        int changed = 1;
        while (changed) {
            changed = 0;
            bs cand = bandn(full, *U);          /* snapshot, as Python's _bits(full & ~U) */
            FOR(x, cand) {
                if (bnone(bandn(nin[x], closed))) {
                    bset(U, x); *nb = bor(*nb, nin[x]); closed = bor(*U, *nb);
                    added[na++] = x; changed = 1;
                }
            }
        }
        if (!greedy2) return na;
        int hit = -1;
        bs c2 = bandn(*nb, *U);
        FOR(x, c2) { if (bpop(bandn(nin[x], closed)) == 1) { hit = x; break; } }
        if (hit < 0) return na;
        bset(U, hit); *nb = bor(*nb, nin[hit]); added[na++] = hit;
    }
}

/* ---------------- node table ---------------- */
static bs *nodes; static size_t nnodes;          /* file order: decreasing size */
static int64_t *ht; static size_t htcap;         /* open addressing: node index */
static void ht_build(void) {
    htcap = 1; while (htcap < 2 * nnodes + 2) htcap <<= 1;
    ht = xmalloc(htcap * sizeof *ht);
    for (size_t i = 0; i < htcap; i++) ht[i] = -1;
    for (size_t i = 0; i < nnodes; i++) {
        size_t h = bhash(nodes[i]) & (htcap - 1);
        while (ht[h] >= 0) h = (h + 1) & (htcap - 1);
        ht[h] = (int64_t)i;
    }
}
/* index of S, nnodes for V, -1 if absent */
static int64_t ht_find(bs S) {
    if (beq(S, full)) return (int64_t)nnodes;
    size_t h = bhash(S) & (htcap - 1);
    while (ht[h] >= 0) { if (beq(nodes[ht[h]], S)) return ht[h]; h = (h + 1) & (htcap - 1); }
    return -1;
}

/* ---------------- models ---------------- */
static const double BELL[21] = {1, 1, 2, 5, 15, 52, 203, 877, 4140, 21147, 115975, 678570,
    4213597, 27644437, 190899322, 1382958545, 10480142147.0, 82864869804.0,
    682076806159.0, 5832742205057.0, 51724158235372.0};
static double LOGBELL[21];
enum { M_V2, M_V7, M_LOGLIN };
static int model = -1;
static double expand_base = 1.55, density_alpha = 0.25;
#define NFEAT 11
static double beta[NFEAT];

typedef struct { double a, e, k; } step_t;

/* sizes of the components of G[F]: returns sum log Bell(size) and fills nothing else */
static double comp_log_bell(bs F) {
    double s = 0.0;
    bs rest = F;
    while (!bnone(rest)) {
        int seed = bnext(rest, -1);
        bs comp = bzero_(); bset(&comp, seed);
        bs front = comp;
        while (!bnone(front)) {
            bs nx = bzero_();
            FOR(u, front) nx = bor(nx, nin[u]);
            nx = bandn(band(nx, F), comp);
            comp = bor(comp, nx); front = nx;
        }
        int sz = bpop(comp);
        s += LOGBELL[sz < 20 ? sz : 20];
        rest = bandn(rest, comp);
    }
    return s;
}

static step_t eval_model(int step, int v, int fw, int fw_before, int nb, int nelim, int ebag,
                         double logbell_comp) {
    step_t r;
    (void)v;
    if (model == M_V2) {
        double q = (double)fw / (pw > 1 ? pw : 1);
        r.a = ldexp(1.0, nb) * q * q + 0.001 * fw; r.e = 0.0; r.k = 0.0;
    } else if (model == M_V7) {
        double lbfw = LOGBELL[fw < 20 ? fw : 20];
        double corr = exp(0.5 * ((logbell_comp > 0 ? logbell_comp : 0.0) - (lbfw > 0 ? lbfw : 0.0)));
        double q = (double)fw / (pw > 1 ? pw : 1);
        double fw_weight = q * q * corr;
        double dens = fw > 0 ? 1.0 + density_alpha * ((double)ebag / fw) : 1.0;
        r.e = pow(expand_base, nb) * fw_weight * dens;
        double k = pow(0.5, nelim);
        r.k = k > 0.01 ? k : 0.01;
        r.a = 0.001 * fw;
    } else {
        double x[NFEAT] = {1.0, nb, nelim, fw, fw_before, ebag, logbell_comp,
                           (double)nb * fw, (double)nelim * fw_before, (double)nb * nb,
                           (double)step / (n > 1 ? n - 1 : 1)};
        double g = 0.0;
        for (int i = 0; i < NFEAT; i++) g += beta[i] * x[i];
        r.a = 0.0; r.e = ldexp(1.0, nb); r.k = exp(g) / r.e;
    }
    return r;
}

/* Features of the tau steps realising the sigma arc S -> S u block
 * (orders.tau_block_features), turned into (a, e, k) per step. */
static int block_steps(bs S, const int *blk, int m, step_t *out) {
    bs C[NMAX + 1], nbu[NMAX + 1];
    C[0] = S; nbu[0] = union_nin(S);
    for (int j = 1; j <= m; j++) {
        C[j] = C[j - 1]; bset(&C[j], blk[j - 1]);
        nbu[j] = bor(nbu[j - 1], nin[blk[j - 1]]);
    }
    bs Tb = bandn(full, C[m]);
    bs Fb = band(Tb, nbu[m]);
    int ns = 0;
    for (int j = m; j >= 1; j--) {
        int v = blk[j - 1];
        bs Ta = bandn(full, C[j - 1]);
        bs Fa = band(Ta, nbu[j - 1]);
        int fw = bpop(Fa);
        int nb = bpop(band(band(nin[v], Tb), Fa));
        int nelim = bpop(bandn(Fb, Fa)) + (bnone(nin[v]) ? 1 : 0);
        int e2 = 0;
        FOR(u, Fa) e2 += bpop(band(nin[u], Fa));
        double lbc = (model == M_V2) ? 0.0 : comp_log_bell(Fa);
        out[ns++] = eval_model(bpop(Tb), v, fw, bpop(Fb), nb, nelim, e2 / 2, lbc);
        Tb = Ta; Fb = Fa;
    }
    return ns;
}

/* ---------------- labels ---------------- */
typedef struct { double cost, p; uint32_t prev; int16_t x; } label_t;   /* x = -1: none */
static label_t *pool; static size_t npool, cappool;
static size_t *loff; static uint32_t *lcnt;   /* per node (index nnodes = V) */

typedef struct { double cost, p; uint32_t prev; int16_t x; uint32_t seq; } cand_t;
static int cand_cmp(const void *A, const void *B) {
    const cand_t *a = A, *b = B;
    if (a->cost != b->cost) return a->cost < b->cost ? -1 : 1;
    if (a->p != b->p) return a->p < b->p ? -1 : 1;
    return a->seq < b->seq ? -1 : (a->seq > b->seq);
}

/* ---------------- DAG file ---------------- */
static void read_dag(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) die("cannot open DAG file");
    char magic[8];
    if (fread(magic, 1, 8, f) != 8) die("short file");
    int hdr[4];
    if (fread(hdr, 4, 4, f) != 4) die("short header");
    n = hdr[0]; pw = hdr[1]; greedy2 = hdr[2];
    int fw = 1, fmt = 0;
    if (!memcmp(magic, "KPWDAG1\n", 8)) fmt = 1;
    else if (!memcmp(magic, "KPWDAG2\n", 8)) { fmt = 2; fw = hdr[3]; }
    else if (!memcmp(magic, "KPWDAG3\n", 8)) { fmt = 3; fw = hdr[3]; }
    else die("not a kpw DAG file");
    if (n > NMAX) die("n too large for this build (rebuild with -DW=k, n <= 64k)");
    if (fw < 1 || fw > 64) die("bad word count");
    u64 *buf = xmalloc(sizeof(u64) * fw);
    full = bzero_();
    for (int v = 0; v < n; v++) bset(&full, v);
#define READSET(dst) do { if (fread(buf, 8, fw, f) != (size_t)fw) die("short file"); \
        (dst) = bzero_(); for (int _j = 0; _j < fw; _j++) { \
            if (_j < W) (dst).w[_j] = buf[_j]; else if (buf[_j]) die("set beyond n"); } } while (0)
    for (int v = 0; v < n; v++) READSET(nin[v]);
    u64 cnt;
    if (fread(&cnt, 8, 1, f) != 1) die("short file");
    nnodes = cnt;
    nodes = xmalloc(sizeof(bs) * (nnodes ? nnodes : 1));
    for (size_t i = 0; i < nnodes; i++) READSET(nodes[i]);
    names = xmalloc(sizeof(char *) * n);
    if (fmt == 3) {
        u64 nbytes;
        if (fread(&nbytes, 8, 1, f) != 1) die("short file");
        char *s = xmalloc(nbytes + 1);
        if (fread(s, 1, nbytes, f) != nbytes) die("short names");
        s[nbytes] = 0;
        size_t o = 0;
        for (int v = 0; v < n; v++) { names[v] = s + o; o += strlen(s + o) + 1; if (o > nbytes + 1) die("bad names"); }
    } else {
        for (int v = 0; v < n; v++) { names[v] = xmalloc(16); snprintf(names[v], 16, "%d", v); }
    }
    free(buf); fclose(f);
    for (size_t i = 1; i < nnodes; i++)
        if (bpop(nodes[i]) > bpop(nodes[i - 1])) die("sets not in decreasing size order");
}

int main(int argc, char **argv) {
    const char *path = NULL;
    long max_labels = -1;
    int quiet = 0, nbeta = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-m") && i + 1 < argc) {
            const char *m = argv[++i];
            model = !strcmp(m, "v2") ? M_V2 : !strcmp(m, "v7") ? M_V7 : !strcmp(m, "loglin") ? M_LOGLIN : -2;
            if (model == -2) die("unknown model (v2, v7, loglin)");
        } else if (!strcmp(argv[i], "-b") && i + 1 < argc) expand_base = atof(argv[++i]);
        else if (!strcmp(argv[i], "-a") && i + 1 < argc) density_alpha = atof(argv[++i]);
        else if (!strcmp(argv[i], "-L") && i + 1 < argc) max_labels = atol(argv[++i]);
        else if (!strcmp(argv[i], "-B") && i + 1 < argc) {
            char *s = argv[++i], *e;
            while (*s && nbeta < NFEAT) { beta[nbeta++] = strtod(s, &e); if (e == s) die("bad -B"); s = (*e == ',') ? e + 1 : e; }
            if (*s) die("-B: too many coefficients");
        } else if (!strcmp(argv[i], "-q")) quiet = 1;
        else if (argv[i][0] == '-') die("usage: kopt -m v2|v7|loglin [-b C] [-a A] [-B b0,..,b10] [-L max_labels] [-q] DAGFILE");
        else path = argv[i];
    }
    if (model < 0 || !path) die("usage: kopt -m v2|v7|loglin [-b C] [-a A] [-B b0,..,b10] [-L max_labels] [-q] DAGFILE");
    if (model == M_LOGLIN && nbeta != NFEAT) die("loglin needs -B with 11 coefficients");
    for (int i = 0; i <= 20; i++) LOGBELL[i] = log(BELL[i]);

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    read_dag(path);
    ht_build();

    /* expansion of the empty set */
    int a0[NMAX], na0;
    bs S0 = bzero_(), nb0 = bzero_();
    na0 = expand(&S0, &nb0, a0);
    if (!beq(S0, full) && ht_find(S0) < 0) die("S0 not in the DAG");

    loff = xmalloc(sizeof(size_t) * (nnodes + 1));
    lcnt = xmalloc(sizeof(uint32_t) * (nnodes + 1));
    cappool = 1 << 20; pool = xmalloc(sizeof(label_t) * cappool); npool = 0;
    loff[nnodes] = 0; lcnt[nnodes] = 1;                       /* V: the label (0, 1) */
    pool[npool++] = (label_t){0.0, 1.0, UINT32_MAX, -1};

    size_t candcap = 1 << 16; cand_t *cand = xmalloc(sizeof(cand_t) * candcap);
    step_t steps[NMAX + 1];
    int added[NMAX];
    uint32_t biggest = 1; int exact = 1; size_t narcs = 0;

    for (size_t si = 0; si < nnodes; si++) {
        bs S = nodes[si], nbS = union_nin(S);
        size_t nc = 0; uint32_t seq = 0;
        bs out = bandn(full, S);
        FOR(x, out) {
            bs b = bzero_(); bset(&b, x);
            if (bpop(bandn(bor(nbS, nin[x]), bor(S, b))) > pw) continue;
            bs T = bor(S, b), nbT = bor(nbS, nin[x]);
            int blk[NMAX + 1]; blk[0] = x;
            int na = expand(&T, &nbT, added);
            int64_t ti = ht_find(T);
            if (ti < 0) continue;
            narcs++;
            memcpy(blk + 1, added, sizeof(int) * na);
            int ns = block_steps(S, blk, na + 1, steps);
            size_t lo = loff[ti]; uint32_t lc = lcnt[ti];
            if (nc + lc > candcap) { while (nc + lc > candcap) candcap *= 2; cand = xrealloc(cand, sizeof(cand_t) * candcap); }
            for (uint32_t li = 0; li < lc; li++) {
                double c = pool[lo + li].cost, p = pool[lo + li].p;
                for (int s = 0; s < ns; s++) {
                    c += steps[s].a + p * steps[s].e;
                    double q = p * steps[s].e * steps[s].k;
                    p = q > 1.0 ? q : 1.0;
                }
                cand[nc++] = (cand_t){c, p, (uint32_t)(lo + li), (int16_t)x, seq++};
            }
        }
        if (nc == 0) die("node with no arcs (not a pruned DAG?)");
        qsort(cand, nc, sizeof(cand_t), cand_cmp);
        size_t keep = 0; double best_p = INFINITY;
        if (npool + nc > cappool) { while (npool + nc > cappool) cappool *= 2; pool = xrealloc(pool, sizeof(label_t) * cappool); }
        loff[si] = npool;
        for (size_t i = 0; i < nc; i++) {
            if (cand[i].p < best_p) {
                if (max_labels >= 0 && (long)keep >= max_labels) { exact = 0; break; }
                pool[npool++] = (label_t){cand[i].cost, cand[i].p, cand[i].prev, cand[i].x};
                best_p = cand[i].p; keep++;
            }
        }
        lcnt[si] = (uint32_t)keep;
        if (keep > biggest) biggest = (uint32_t)keep;
    }

    /* final block: vertices of (empty)*, added last in tau */
    int64_t s0i = ht_find(S0);
    int ns0 = na0 ? block_steps(bzero_(), a0, na0, steps) : 0;
    double best_c = INFINITY; size_t best = SIZE_MAX;
    for (uint32_t li = 0; li < lcnt[s0i]; li++) {
        size_t L = loff[s0i] + li;
        double c = pool[L].cost, p = pool[L].p;
        for (int s = 0; s < ns0; s++) {
            c += steps[s].a + p * steps[s].e;
            double q = p * steps[s].e * steps[s].k;
            p = q > 1.0 ? q : 1.0;
        }
        if (c < best_c) { best_c = c; best = L; }
    }

    /* sigma = a0 + blocks along the label chain; tau = reverse(sigma) */
    int sigma[NMAX], ls = 0;
    for (int i = 0; i < na0; i++) sigma[ls++] = a0[i];
    bs S = S0; size_t L = best;
    while (pool[L].x >= 0) {
        int x = pool[L].x;
        bs T = S, nbT = union_nin(S);
        bset(&T, x); nbT = bor(nbT, nin[x]);
        sigma[ls++] = x;
        int na = expand(&T, &nbT, added);
        for (int i = 0; i < na; i++) sigma[ls++] = added[i];
        S = T; L = pool[L].prev;
    }
    if (ls != n || !beq(S, full)) die("internal error: traceback");

    clock_gettime(CLOCK_MONOTONIC, &t1);
    double secs = (t1.tv_sec - t0.tv_sec) + 1e-9 * (t1.tv_nsec - t0.tv_nsec);
    printf("kopt: n=%d pw=%d nodes=%zu arcs=%zu labels_total=%zu max_labels=%u exact=%d cost=%.17g time=%.3f\n",
           n, pw, nnodes + 1, narcs, npool, biggest, exact, best_c, secs);
    if (!quiet) {
        printf("order:");
        for (int i = ls - 1; i >= 0; i--) printf(" %s", names[sigma[i]]);
        printf("\n");
    }
    return 0;
}
