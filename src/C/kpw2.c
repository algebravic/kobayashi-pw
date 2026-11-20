/* kpw2.c -- kpw with four extensions (see doc/kpw2_design.md):
 *   1. n <= 64*W vertices (compile with -DW=k; default W=2, n <= 128)
 *   2. rule-1 expansion as a worklist over out-neighbours of the newly
 *      closed vertices (same sets as kpw; less work per expansion)
 *   3. -x : store only (key, arc label x, |parent|); recover a parent by a
 *      scan of the table during extraction (less memory, more time)
 *   4. -t N : N threads (pthreads) sharing each level; -t 0 = all cores
 *
 * Usage: kpw2 [-d] [-g] [-c [-o FILE]] [-x] [-t N] [-r] [-q] [FILE]
 *   -d directed ("u v" = arc u->v); -g second greedy rule (Coudert et al.);
 *   -c complete level pw and prune to the DAG of optimal orderings;
 *   -o FILE write that DAG (format KPWDAG3, doc/dag_format.md); -r print the ordering reversed
 *   (frontier-DP convention); -q do not print the ordering.
 * Input: edge list, at most 64W vertices: "u v [ignored...]" per line, vertex
 * names arbitrary strings, lone token = isolated vertex, '#' comment (see
 * edgelist.h for the numbering).  The ordering is printed with the input's
 * names and re-verified.
 *
 * Build: cc -O3 -march=native -pthread -o kpw2 kpw2.c      (n <= 128)
 *        cc -O3 -march=native -pthread -DW=1 -o kpw2_64 kpw2.c
 */
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sched.h>
#include <time.h>
#include "edgelist.h"

#ifndef W
#define W 2
#endif
#define NMAX (64 * W)
#define ROOT 255
#define MAXT 256
#define LOGNSH 8
#define NSH (1 << LOGNSH)

typedef uint64_t u64;
typedef struct { u64 w[W]; } bs;

/* ---------------- bit sets ---------------- */
static inline bs bzero_(void) { bs r; memset(&r, 0, sizeof r); return r; }
static inline bs bor(bs a, bs b) { for (int i = 0; i < W; i++) a.w[i] |= b.w[i]; return a; }
static inline bs band(bs a, bs b) { for (int i = 0; i < W; i++) a.w[i] &= b.w[i]; return a; }
static inline bs bandn(bs a, bs b) { for (int i = 0; i < W; i++) a.w[i] &= ~b.w[i]; return a; }
static inline int beq(bs a, bs b) { for (int i = 0; i < W; i++) if (a.w[i] != b.w[i]) return 0; return 1; }
static inline int bnone(bs a) { for (int i = 0; i < W; i++) if (a.w[i]) return 0; return 1; }
static inline int bpop(bs a) { int c = 0; for (int i = 0; i < W; i++) c += __builtin_popcountll(a.w[i]); return c; }
static inline int btest(bs a, int x) { return (a.w[x >> 6] >> (x & 63)) & 1; }
static inline void bset(bs *a, int x) { a->w[x >> 6] |= 1ULL << (x & 63); }
static inline void bclr(bs *a, int x) { a->w[x >> 6] &= ~(1ULL << (x & 63)); }
static inline bs bbit(int x) { bs r = bzero_(); bset(&r, x); return r; }
/* first set bit > x, or -1 */
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
static inline int bhigh(bs a) {
    for (int i = W - 1; i >= 0; i--) if (a.w[i]) return i * 64 + 63 - __builtin_clzll(a.w[i]);
    return -1;
}
#define FOR(x, m) for (int x = bnext((m), -1); x >= 0; x = bnext((m), x))
/* fast word-wise iteration; the body must not use break/continue */
#define FORW(x, m, ...) do { bs _M = (m); for (int _i = 0; _i < W; _i++) \
    for (u64 _w = _M.w[_i]; _w; _w &= _w - 1) { int x = _i * 64 + __builtin_ctzll(_w); __VA_ARGS__ } } while (0)
static inline size_t bhash(bs a) {
    u64 h = a.w[0];
    for (int i = 1; i < W; i++) h = (h ^ (h >> 31)) * 0x9e3779b97f4a7c15ULL ^ a.w[i];
    h ^= h >> 33; h *= 0xff51afd7ed558ccdULL; h ^= h >> 33;
    return (size_t)h;
}

/* ---------------- graph ---------------- */
static int n, greedy2, compact, nthreads = 1;
static bs nin[NMAX], nout[NMAX], full;

static bs unionnin(bs U) { bs r = bzero_(); FORW(u, U, r = bor(r, nin[u]);); return r; }
static bs nout_of(bs D) { bs r = bzero_(); FORW(y, D, r = bor(r, nout[y]);); return r; }

/* Expansion.  U, nb (= union of nin over U) are updated in place; the added
 * vertices go to added[] (may be NULL); cand = vertices whose rule-1 status
 * may have changed since U was last rule-1 closed (all vertices if unknown). */
static int expand(bs *U, bs *nb, int *added, bs cand) {
    int cnt = 0;
    bs closed = bor(*U, *nb);
    for (;;) {
        cand = bandn(cand, *U);
        int x;
        while ((x = bnext(cand, -1)) >= 0) {
            bclr(&cand, x);
            if (bnone(bandn(nin[x], closed))) {
                bs nc = bor(bor(closed, bbit(x)), nin[x]);
                bs delta = bandn(nc, closed);
                bset(U, x); *nb = bor(*nb, nin[x]); closed = nc;
                if (added) added[cnt] = x;
                cnt++;
                cand = bandn(bor(cand, nout_of(delta)), *U);
            }
        }
        if (!greedy2) return cnt;
        int hit = -1;
        bs bd = bandn(*nb, *U);
        FOR(y, bd) if (bpop(bandn(nin[y], closed)) == 1) { hit = y; break; }
        if (hit < 0) return cnt;
        bs nc = bor(bor(closed, bbit(hit)), nin[hit]);
        bs delta = bandn(nc, closed);
        bset(U, hit); *nb = bor(*nb, nin[hit]); closed = nc;
        if (added) added[cnt] = hit;
        cnt++;
        cand = nout_of(delta);
    }
}
/* expansion of P u {x} for a rule-1-closed P with nbP = unionnin(P) */
static int expand_from(bs P, bs nbP, int x, bs *T, bs *nbT, int *added) {
    bs delta = bandn(bor(bbit(x), nin[x]), bor(P, nbP));
    *T = bor(P, bbit(x)); *nbT = bor(nbP, nin[x]);
    return expand(T, nbT, added, nout_of(delta));
}

/* ---------------- growable arrays ---------------- */
typedef struct { bs S, nb, xs; } Item;   /* a set with the arc labels still to try */
typedef struct { bs S, nb; } Ent;
typedef struct { void *a; size_t len, cap, sz; } Vec;
static void push(Vec *v, const void *e) {
    if (v->len == v->cap) {
        v->cap = v->cap ? 2 * v->cap : 1024;
        v->a = realloc(v->a, v->cap * v->sz);
        if (!v->a) { fprintf(stderr, "out of memory\n"); exit(3); }
    }
    memcpy((char *)v->a + v->len++ * v->sz, e, v->sz);
}
static void vfree(Vec *v) { free(v->a); v->a = NULL; v->len = v->cap = 0; }

/* ---------------- sharded hash table ---------------- */
typedef struct { bs key; uint8_t used, good, x, psz; } Slot;
typedef struct { Slot *s; bs *par; size_t cap, len; atomic_flag mu; char pad[64]; } Shard;
static Shard sh[NSH];

static void shard_init(void) {
    for (int i = 0; i < NSH; i++) {
        sh[i].cap = 64; sh[i].len = 0;
        sh[i].s = calloc(sh[i].cap, sizeof(Slot));
        sh[i].par = compact ? NULL : malloc(sh[i].cap * sizeof(bs));
        atomic_flag_clear(&sh[i].mu);
    }
}
static inline Shard *shard_of(size_t h) { return &sh[h >> (8 * sizeof(size_t) - LOGNSH)]; }
static inline size_t slot_of(Shard *s, bs key, size_t h) {
    size_t i = h & (s->cap - 1);
    while (s->s[i].used && !beq(s->s[i].key, key)) i = (i + 1) & (s->cap - 1);
    return i;
}
static void shard_grow(Shard *s) {
    Slot *os = s->s; bs *op = s->par; size_t oc = s->cap;
    s->cap = oc * 2;
    s->s = calloc(s->cap, sizeof(Slot));
    s->par = compact ? NULL : malloc(s->cap * sizeof(bs));
    if (!s->s || (!compact && !s->par)) { fprintf(stderr, "out of memory\n"); exit(3); }
    for (size_t i = 0; i < oc; i++) if (os[i].used) {
        size_t j = slot_of(s, os[i].key, bhash(os[i].key));
        s->s[j] = os[i];
        if (!compact) s->par[j] = op[i];
    }
    free(os); free(op);
}
/* per-shard spin lock; taken only with more than one thread */
static inline void spin_lock(atomic_flag *f) {
    int k = 0;
    while (atomic_flag_test_and_set_explicit(f, memory_order_acquire))
        if (++k > 64) { sched_yield(); k = 0; }
}
static inline void lk(Shard *s) { if (nthreads > 1) spin_lock(&s->mu); }
static inline void ulk(Shard *s) {
    if (nthreads > 1) atomic_flag_clear_explicit(&s->mu, memory_order_release);
}
static int tab_insert(bs S, bs par, int x, int psz) {
    size_t h = bhash(S); Shard *s = shard_of(h); int isnew = 0;
    lk(s);
    if (2 * (s->len + 1) > s->cap) shard_grow(s);
    size_t i = slot_of(s, S, h);
    if (!s->s[i].used) {
        s->s[i].key = S; s->s[i].used = 1; s->s[i].good = 0;
        s->s[i].x = (uint8_t)x; s->s[i].psz = (uint8_t)psz;
        if (!compact) s->par[i] = par;
        s->len++; isnew = 1;
    }
    ulk(s);
    return isnew;
}
static int tab_get(bs S, int *x, int *psz, bs *par, int *good) {
    size_t h = bhash(S); Shard *s = shard_of(h); int found = 0;
    lk(s);
    size_t i = slot_of(s, S, h);
    if (s->s[i].used) {
        found = 1;
        if (x) *x = s->s[i].x;
        if (psz) *psz = s->s[i].psz;
        if (par && !compact) *par = s->par[i];
        if (good) *good = s->s[i].good;
    }
    ulk(s);
    return found;
}
static inline int tab_has(bs S) {
    size_t h = bhash(S); Shard *s = shard_of(h);
    lk(s); int r = s->s[slot_of(s, S, h)].used; ulk(s);
    return r;
}
static void tab_set_good(bs S) {
    size_t h = bhash(S); Shard *s = shard_of(h);
    lk(s); size_t i = slot_of(s, S, h); if (s->s[i].used) s->s[i].good = 1; ulk(s);
}
static size_t tab_len(void) { size_t t = 0; for (int i = 0; i < NSH; i++) t += sh[i].len; return t; }
static size_t tab_mem(void) {
    size_t t = 0;
    for (int i = 0; i < NSH; i++) t += sh[i].cap * (sizeof(Slot) + (compact ? 0 : sizeof(bs)));
    return t;
}

/* ---------------- search state ---------------- */
typedef struct {
    Vec stack;                 /* Item */
    Vec bk[NMAX + 2];          /* Ent, per level */
    long sets, pairs, rescans;
    atomic_flag smu;           /* guards stack when nthreads > 1 (owner vs thieves) */
    char pad[64];
} Ctx;
static Ctx *ctx;
static atomic_int found;
static int complete;
static bs fullpar; static int fullx = -2, fullpsz;
static pthread_mutex_t fullmu = PTHREAD_MUTEX_INITIALIZER;

static atomic_long pending;          /* pairs pushed but not yet fully processed */
static inline void slock(Ctx *C) { if (nthreads > 1) spin_lock(&C->smu); }
static inline void sunlock(Ctx *C) {
    if (nthreads > 1) atomic_flag_clear_explicit(&C->smu, memory_order_release);
}
static void scan(Ctx *C, bs S, bs nb, int lo, int c) {
    int nxt = n + 1, k = 0;
    Item it = {S, nb, bzero_()};
    bs rest = bandn(full, S);
    FORW(x, rest, {
        bs Tx = S; bset(&Tx, x);
        int w = bpop(bandn(bor(nb, nin[x]), Tx));
        if (w <= c) { if (w > lo) { bset(&it.xs, x); k++; } }
        else if (w < nxt) nxt = w;
    });
    if (k) {
        if (nthreads > 1) atomic_fetch_add(&pending, k);
        slock(C);
        push(&C->stack, &it);
        sunlock(C);
    }
    if (nxt <= n) { Ent e = {S, nb}; push(&C->bk[nxt], &e); }
}

/* take the next pair (S, nb, x) from the top item; 0 if the stack is empty */
static inline int pop_pair(Ctx *C, bs *S, bs *nb, int *x) {
    int got = 0;
    slock(C);
    if (C->stack.len) {
        Item *it = (Item *)C->stack.a + C->stack.len - 1;
        *x = bhigh(it->xs); bclr(&it->xs, *x);
        *S = it->S; *nb = it->nb;
        if (bnone(it->xs)) C->stack.len--;
        got = 1;
    }
    sunlock(C);
    return got;
}
typedef struct { bs S, nb; int x; } Pair;
/* process one pair; returns 1 if V was reached */
static int process(Ctx *C, Pair p, int c) {
    C->pairs++;
    bs T0 = bor(p.S, bbit(p.x));
    if (!beq(T0, full) && tab_has(T0)) return 0;
    bs T, nbT;
    expand_from(p.S, p.nb, p.x, &T, &nbT, NULL);
    if (beq(T, full)) {
        pthread_mutex_lock(&fullmu);
        if (fullx == -2) { fullpar = p.S; fullx = p.x; fullpsz = bpop(p.S); C->sets++; }
        pthread_mutex_unlock(&fullmu);
        atomic_store(&found, 1);
        return 1;
    }
    if (!tab_insert(T, p.S, p.x, bpop(p.S))) return 0;
    C->sets++;
    scan(C, T, nbT, -1, c);
    return 0;
}

/* ---------------- parallel machinery ---------------- */
typedef struct { int tid, c, kind; } Job;   /* kind 0: rescan, 1: round, 2: prune layer */
static Vec gwork;                /* Ent (rescan) or Pair (round) shared input */
static atomic_size_t gidx;
static bs *layer_sets; static size_t layer_lo, layer_hi; static int prune_pw;
static Vec dagv;                 /* bs */
static pthread_mutex_t dagmu = PTHREAD_MUTEX_INITIALIZER;

static int prune_one(bs S, int pw);

static void *worker(void *arg) {
    Job *j = arg; Ctx *C = &ctx[j->tid];
    if (j->kind == 0) {
        size_t i;
        while ((i = atomic_fetch_add(&gidx, 1)) < gwork.len) {
            Ent e = ((Ent *)gwork.a)[i];
            C->rescans++;
            scan(C, e.S, e.nb, j->c - 1, j->c);
        }
    } else if (j->kind == 1) {
        /* drain own stack depth first; when empty, steal half of another's */
        unsigned seed = 2654435761u * (unsigned)(j->tid + 1);
        int fails = 0;
        for (;;) {
            if (atomic_load(&found) && !complete) break;
            Pair p; int got = pop_pair(C, &p.S, &p.nb, &p.x);
            if (got) {
                process(C, p, j->c);
                atomic_fetch_sub(&pending, 1);
                continue;
            }
            if (atomic_load(&pending) == 0) break;
            if (fails > 2) { sched_yield(); }
            seed = seed * 1103515245u + 12345u;
            int v = (int)(seed % (unsigned)nthreads);
            for (int k = 0; k < nthreads && !got; k++, v = (v + 1) % nthreads) {
                if (v == j->tid) continue;
                Ctx *V = &ctx[v];
                if (!__atomic_load_n(&V->stack.len, __ATOMIC_RELAXED)) continue;
                slock(V);
                size_t len = V->stack.len;
                if (len >= 2) {
                    size_t take = len / 2;
                    Item *src = (Item *)V->stack.a;   /* take the oldest half */
                    slock(C);
                    for (size_t i = 0; i < take; i++) push(&C->stack, &src[i]);
                    sunlock(C);
                    memmove(src, src + take, (len - take) * sizeof(Item));
                    V->stack.len = len - take;
                    got = 1;
                } else if (len == 1) {
                    Item q = ((Item *)V->stack.a)[0]; V->stack.len = 0;
                    slock(C); push(&C->stack, &q); sunlock(C);
                    got = 1;
                }
                sunlock(V);
            }
            fails = got ? 0 : fails + 1;
        }
    } else {
        size_t i;
        while ((i = layer_lo + atomic_fetch_add(&gidx, 1)) < layer_hi) {
            bs S = layer_sets[i];
            if (prune_one(S, prune_pw)) {
                tab_set_good(S);
                pthread_mutex_lock(&dagmu); push(&dagv, &S); pthread_mutex_unlock(&dagmu);
            }
        }
    }
    return NULL;
}
static void run_parallel(int kind, int c) {
    pthread_t th[MAXT]; Job jobs[MAXT];
    atomic_store(&gidx, 0);
    for (int t = 0; t < nthreads; t++) {
        jobs[t] = (Job){t, c, kind};
        if (t) pthread_create(&th[t], NULL, worker, &jobs[t]);
    }
    worker(&jobs[0]);
    for (int t = 1; t < nthreads; t++) pthread_join(th[t], NULL);
}

/* ---------------- complete mode: prune ---------------- */
static int prune_one(bs S, int pw) {
    bs nb = unionnin(S), rest = bandn(full, S);
    FOR(x, rest) {
        if (bpop(bandn(bor(nb, nin[x]), bor(S, bbit(x)))) > pw) continue;
        bs T, nbT;
        expand_from(S, nb, x, &T, &nbT, NULL);
        if (beq(T, full)) return 1;
        int good;
        if (tab_get(T, NULL, NULL, NULL, &good) && good) return 1;
    }
    return 0;
}
static int cmp_pop_desc(const void *a, const void *b) {
    return bpop(*(const bs *)b) - bpop(*(const bs *)a);
}
static void prune(int pw) {
    size_t m = 0, tot = tab_len();
    bs *all = malloc((tot ? tot : 1) * sizeof(bs));
    for (int i = 0; i < NSH; i++)
        for (size_t j = 0; j < sh[i].cap; j++) if (sh[i].s[j].used) all[m++] = sh[i].s[j].key;
    qsort(all, m, sizeof(bs), cmp_pop_desc);
    dagv.sz = sizeof(bs);
    layer_sets = all; prune_pw = pw;
    size_t i = 0;
    while (i < m) {
        size_t j = i; int p = bpop(all[i]);
        while (j < m && bpop(all[j]) == p) j++;
        if (nthreads > 1 && j - i > 64) {
            layer_lo = i; layer_hi = j; run_parallel(2, 0);
        } else {
            for (size_t k = i; k < j; k++)
                if (prune_one(all[k], pw)) { tab_set_good(all[k]); push(&dagv, &all[k]); }
        }
        i = j;
    }
    qsort(dagv.a, dagv.len, sizeof(bs), cmp_pop_desc);
    free(all);
}
static EdgeList el;
/* format KPWDAG3 (doc/dag_format.md) */
static void dump_dag(const char *fn, int pw) {
    FILE *f = fopen(fn, "wb"); if (!f) { perror(fn); exit(1); }
    int32_t hdr[4] = {n, pw, greedy2, W}; u64 cnt = dagv.len;
    fwrite("KPWDAG3\n", 1, 8, f); fwrite(hdr, 4, 4, f);
    for (int v = 0; v < n; v++) fwrite(nin[v].w, 8, W, f);
    fwrite(&cnt, 8, 1, f);
    for (size_t i = 0; i < dagv.len; i++) fwrite(((bs *)dagv.a)[i].w, 8, W, f);
    el_write_names(f, &el);
    fclose(f);
}

/* ---------------- -x: parent recovery by table scan ----------------
 * Any stored P with |P| = psz, P subset of T \ {x}, |N(P u {x})| <= pw and
 * expansion(P u {x}) = T is a valid predecessor: P has bottleneck <= pw and the
 * arc costs <= pw.  The recorded parent qualifies, so the scan always succeeds.
 * Cost: one pass over the table per extraction step (at most n steps). */
static long scan_checked;
static bs find_parent(bs T, int x, int psz, int pw) {
    bs Tm = T; bclr(&Tm, x);
    for (int i = 0; i < NSH; i++) {
        Shard *s = &sh[i];
        for (size_t j = 0; j < s->cap; j++) {
            if (!s->s[j].used) continue;
            bs P = s->s[j].key;
            if (bpop(P) != psz || !bnone(bandn(P, Tm))) continue;
            scan_checked++;
            bs nbP = unionnin(P);
            if (bpop(bandn(bor(nbP, nin[x]), bor(P, bbit(x)))) > pw) continue;
            bs T2, nb2;
            expand_from(P, nbP, x, &T2, &nb2, NULL);
            if (beq(T2, T)) return P;
        }
    }
    fprintf(stderr, "parent recovery failed (internal error)\n"); exit(4);
}

/* ---------------- main ---------------- */
int main(int argc, char **argv) {
    int directed = 0, reverse = 0, quiet = 0;
    const char *path = NULL, *dagfile = NULL;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-d")) directed = 1;
        else if (!strcmp(argv[i], "-g")) greedy2 = 1;
        else if (!strcmp(argv[i], "-c")) complete = 1;
        else if (!strcmp(argv[i], "-x")) compact = 1;
        else if (!strcmp(argv[i], "-r")) reverse = 1;
        else if (!strcmp(argv[i], "-q")) quiet = 1;
        else if (!strcmp(argv[i], "-o") && i + 1 < argc) dagfile = argv[++i];
        else if (!strcmp(argv[i], "-t") && i + 1 < argc) nthreads = atoi(argv[++i]);
        else if (argv[i][0] == '-') { fprintf(stderr, "unknown option %s\n", argv[i]); return 1; }
        else path = argv[i];
    }
    if (dagfile && !complete) { fprintf(stderr, "-o requires -c\n"); return 1; }
    if (nthreads <= 0) nthreads = (int)sysconf(_SC_NPROCESSORS_ONLN);
    if (nthreads < 1) nthreads = 1;
    if (nthreads > MAXT) nthreads = MAXT;
    FILE *f = path ? fopen(path, "r") : stdin;
    if (!f) { perror(path); return 1; }
    char err[200];
    if (el_read(f, NMAX, &el, err, sizeof err)) {
        fprintf(stderr, "%s (rebuild with a larger -DW)\n", err); return 1;
    }
    if (f != stdin) fclose(f);
    n = el.n;
    for (int k = 0; k < el.m; k++) {
        int u = el.e[k][0], v = el.e[k][1];
        if (u != v) {
            bset(&nin[v], u); bset(&nout[u], v);
            if (!directed) { bset(&nin[u], v); bset(&nout[v], u); }
        }
    }
    full = bzero_();
    for (int v = 0; v < n; v++) bset(&full, v);
    shard_init();
    ctx = calloc(nthreads, sizeof(Ctx));
    for (int t = 0; t < nthreads; t++) {
        atomic_flag_clear(&ctx[t].smu);
        ctx[t].stack.sz = sizeof(Item);
        for (int l = 0; l < NMAX + 2; l++) ctx[t].bk[l].sz = sizeof(Ent);
    }

    bs S0 = bzero_(), nb0 = bzero_();
    expand(&S0, &nb0, NULL, full);
    if (beq(S0, full)) fullx = ROOT; else tab_insert(S0, bzero_(), ROOT, 0);
    ctx[0].sets = 1;
    int c = 0;
    if (beq(S0, full)) atomic_store(&found, 1); else scan(&ctx[0], S0, nb0, -1, 0);

    if (nthreads == 1) {                         /* exact sequential loop of kpw */
        Ctx *C = &ctx[0];
        while (!atomic_load(&found) || (complete && C->stack.len)) {
            Pair p;
            while (pop_pair(C, &p.S, &p.nb, &p.x))
                if (process(C, p, c) && !complete) break;
            if (atomic_load(&found)) break;
            c++;
            Ent *e = C->bk[c].a;
            for (size_t i = 0; i < C->bk[c].len; i++) { C->rescans++; scan(C, e[i].S, e[i].nb, c - 1, c); }
            vfree(&C->bk[c]);
        }
    } else {
        for (;;) {
            /* level c: all pending pairs are in the threads' stacks */
            long tot = 0;
            for (int t = 0; t < nthreads; t++)
                for (size_t i = 0; i < ctx[t].stack.len; i++) tot += bpop(((Item *)ctx[t].stack.a)[i].xs);
            atomic_store(&pending, tot);
#ifdef LEVEL_TIMING
            struct timespec t0, t1; clock_gettime(CLOCK_MONOTONIC, &t0);
#endif
            if (tot) run_parallel(1, c);
#ifdef LEVEL_TIMING
            clock_gettime(CLOCK_MONOTONIC, &t1);
            fprintf(stderr, "level %d: start pairs %ld, %.3f s\n", c, tot, (t1.tv_sec - t0.tv_sec) + 1e-9 * (t1.tv_nsec - t0.tv_nsec));
#endif
            if (atomic_load(&found)) break;
            c++;
            Vec ents = {0, 0, 0, sizeof(Ent)};
            for (int t = 0; t < nthreads; t++) {
                Vec *b = &ctx[t].bk[c];
                for (size_t i = 0; i < b->len; i++) push(&ents, (Ent *)b->a + i);
                vfree(b);
            }
            gwork = ents;
#ifdef LEVEL_TIMING
            struct timespec r0, r1; clock_gettime(CLOCK_MONOTONIC, &r0);
#endif
            run_parallel(0, c);          /* rescans push into the threads' stacks */
#ifdef LEVEL_TIMING
            clock_gettime(CLOCK_MONOTONIC, &r1);
            fprintf(stderr, "  rescan level %d: %zu entries, %.3f s\n", c, gwork.len, (r1.tv_sec - r0.tv_sec) + 1e-9 * (r1.tv_nsec - r0.tv_nsec));
#endif
            vfree(&gwork);
        }
    }
    long sets = 0, pairs = 0, rescans = 0;
    for (int t = 0; t < nthreads; t++) { sets += ctx[t].sets; pairs += ctx[t].pairs; rescans += ctx[t].rescans; }
    if (complete) { prune(c); if (dagfile) dump_dag(dagfile, c); }
    size_t mem = tab_mem();
    for (int t = 0; t < nthreads; t++) vfree(&ctx[t].stack);

    /* extract and verify */
    int order[NMAX], seg[NMAX], nseg = 0, segstart[NMAX + 1], tmp[NMAX], pos = 0;
    bs S = full;
    for (;;) {
        int x = -1, psz = 0; bs par = bzero_();
        if (beq(S, full)) { x = fullx; psz = fullpsz; par = fullpar; }
        else tab_get(S, &x, &psz, &par, NULL);
        segstart[nseg] = pos;
        if (x == ROOT) {
            bs U = bzero_(), nb = bzero_();
            int cnt = expand(&U, &nb, seg, full);
            memcpy(tmp + pos, seg, cnt * sizeof(int)); pos += cnt; nseg++;
            break;
        }
        bs P = compact ? find_parent(S, x, psz, c) : par;
        bs T, nbT;
        int cnt = expand_from(P, unionnin(P), x, &T, &nbT, seg);
        if (!beq(T, S)) { fprintf(stderr, "extraction mismatch (internal error)\n"); return 4; }
        tmp[pos++] = x; memcpy(tmp + pos, seg, cnt * sizeof(int)); pos += cnt; nseg++;
        S = P;
    }
    segstart[nseg] = pos;
    int m = 0;
    for (int i = nseg - 1; i >= 0; i--) for (int j = segstart[i]; j < segstart[i + 1]; j++) order[m++] = tmp[j];
    bs U = bzero_(), nb = bzero_(); int wmax = 0;
    for (int i = 0; i < m; i++) {
        bset(&U, order[i]); nb = bor(nb, nin[order[i]]);
        int w = bpop(bandn(nb, U)); if (w > wmax) wmax = w;
    }
    if (m != n || wmax != c) { fprintf(stderr, "VERIFY FAILED m=%d wmax=%d c=%d\n", m, wmax, c); return 2; }
    printf("n=%d pw=%d sets=%ld pairs=%ld rescans=%ld", n, c, sets, pairs, rescans);
    if (complete) printf(" dag=%zu", dagv.len + 1);
    printf(" table_MB=%.1f threads=%d", mem / 1048576.0, nthreads);
    if (compact) printf(" recovery_candidates=%ld", scan_checked);
    printf("\n");
    if (!quiet) {
        printf("order:");
        for (int i = 0; i < m; i++) printf(" %s", el.names[order[reverse ? m - 1 - i : i]]);
        printf("\n");
    }
    return 0;
}
