/* kcw: exact cutwidth by a one-pass bucketed bottleneck search over prefix sets.
 *
 *   f(S)       = |E(S, V-S)|                (cut of a prefix set S)
 *   rank(S, v) = deg v - 2 |N(v) & S|       (= f(S+v) - f(S))
 *
 * cw(G) = min over orderings of max over prefixes of f, i.e. a minimum-
 * bottleneck path from {} to V in the lattice of prefix sets.  Reductions:
 *   - closure: any vertex of rank <= 0 is added at once (submodular greedy
 *     lemma, doc/other_widths.md sec. 2);
 *   - cover restriction (default; -C to disable): only vertices of a vertex
 *     cover C are chosen; before x in C, i vertices of
 *     Y = {u in N(x) - C - S : deg u odd, rank(S,u) = 1} are placed
 *     (Cygan, Lokshtanov, Pilipczuk, Pilipczuk, Saurabh, Algorithmica 68
 *     (2014), normal form).  States are then determined by S & C (<= 2^tau).
 * Search: level B rises from max ceil(deg/2); all states of bottleneck <= B
 * are expanded depth-first, skipped arcs > B are remembered by bucket, and the
 * first insertion of V ends the search with cw = B.  While level B is being
 * processed cw >= B is proved, so an interrupted run reports lb=B.
 *
 * Input: edge list (see edgelist.h).  Simple undirected graphs (parallel edges
 * merged with a warning; loops ignored).
 *
 * Twins (N[u]=N[v] or N(u)=N(v)) are interchangeable: a vertex is chosen only
 * after its smaller twins (-W disables this).
 *
 * Usage: kcw [-C] [-W] [-q] [-v] [-T seconds] [-M max_states] [file]
 * Build: cc -O3 -march=native -o kcw kcw.c
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "edgelist.h"

typedef uint64_t u64;

static double now(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + 1e-9 * t.tv_nsec;
}

/* ------------------------------------------------------------------ graph */
typedef struct {
    int n, m;
    int *as, *av;      /* CSR adjacency */
    int *deg;
} Graph;

/* ------------------------------------------------------------- options */
static int opt_nocover = 0, opt_verbose = 0;
static double opt_T = 0, t_start;
static size_t opt_M = 0;

/* ------------------------------------------------------ per-component state */
static Graph G;
static int *incov, *cidx, *cov, tau;   /* cover */
static int *tw_start, *tw_mem, *tw_cls; /* twin classes: members of class c are tw_mem[tw_start[c]..tw_start[c+1]) in increasing order */
static int opt_notwins = 0;
static int kw;                          /* key words */
static int nwN;                         /* words of an n-bit set */

static u64 *keys; static uint32_t *par; static int32_t *sx, *si;
static size_t ns, scap;
static uint32_t *ht; static size_t hmask;

static uint32_t *stack; static size_t sp, stcap;
typedef struct { uint32_t *v; size_t len, cap; } Vec;
static Vec *bucket; static int nbuckets;

/* work arrays */
static int *a;            /* a[u] = |N(u) & S| */
static u64 *inS;
static int sizeS, cutS;
static int *queued, *qbuf, qlen, qhead;
static int *added, nadded;
static int *Ybuf;
static u64 *keybuf;
static size_t expansions;

#define IN(s, v) ((s)[(v) >> 6] >> ((v) & 63) & 1)
#define SET(s, v) ((s)[(v) >> 6] |= 1ULL << ((v) & 63))
#define CLR(s, v) ((s)[(v) >> 6] &= ~(1ULL << ((v) & 63)))

static void vpush(Vec *b, uint32_t x) {
    if (b->len == b->cap) { b->cap = b->cap ? 2 * b->cap : 16; b->v = realloc(b->v, b->cap * sizeof *b->v); }
    b->v[b->len++] = x;
}
static void spush(uint32_t x) {
    if (sp == stcap) { stcap = stcap ? 2 * stcap : 1024; stack = realloc(stack, stcap * sizeof *stack); }
    stack[sp++] = x;
}

static inline uint64_t hkey(const u64 *k) {
    uint64_t h = 0x9E3779B97F4A7C15ULL;
    for (int i = 0; i < kw; i++) { h ^= k[i]; h *= 0xBF58476D1CE4E5B9ULL; h ^= h >> 31; }
    return h;
}

static void rehash(size_t newsize) {
    free(ht);
    ht = calloc(newsize, sizeof *ht); hmask = newsize - 1;
    if (!ht) { fprintf(stderr, "out of memory (hash)\n"); exit(3); }
    for (size_t id = 0; id < ns; id++) {
        size_t h = hkey(keys + id * kw) & hmask;
        while (ht[h]) h = (h + 1) & hmask;
        ht[h] = (uint32_t)id + 1;
    }
}

/* returns id; *isnew set if inserted */
static uint32_t insert(const u64 *k, uint32_t p, int x, int i, int *isnew) {
    size_t h = hkey(k) & hmask;
    while (ht[h]) {
        uint32_t id = ht[h] - 1;
        if (!memcmp(keys + (size_t)id * kw, k, kw * sizeof(u64))) { *isnew = 0; return id; }
        h = (h + 1) & hmask;
    }
    if (ns == scap) {
        scap = scap ? 2 * scap : 1 << 16;
        keys = realloc(keys, scap * kw * sizeof(u64));
        par = realloc(par, scap * sizeof *par); sx = realloc(sx, scap * sizeof *sx); si = realloc(si, scap * sizeof *si);
        if (!keys || !par || !sx || !si) { fprintf(stderr, "out of memory (states)\n"); exit(3); }
    }
    uint32_t id = (uint32_t)ns++;
    memcpy(keys + (size_t)id * kw, k, kw * sizeof(u64));
    par[id] = p; sx[id] = x; si[id] = i;
    ht[h] = id + 1;
    if (2 * ns > hmask + 1) rehash(2 * (hmask + 1));
    *isnew = 1;
    return id;
}

static inline int rank_(int v) { return G.deg[v] - 2 * a[v]; }

/* add v to S (in place), queue neighbours that reach rank <= 0 */
static void add_v(int v) {
    cutS += rank_(v);
    SET(inS, v); sizeS++;
    added[nadded++] = v;
    for (int e = G.as[v]; e < G.as[v + 1]; e++) {
        int u = G.av[e];
        a[u]++;
        if (!IN(inS, u) && !queued[u] && rank_(u) <= 0) { queued[u] = 1; qbuf[qlen++] = u; }
    }
}

static void closure(void) {
    while (qhead < qlen) {
        int u = qbuf[qhead++];
        if (!IN(inS, u)) add_v(u);
    }
}

static void undo(void) {
    while (nadded > 0) {
        int v = added[--nadded];
        CLR(inS, v); sizeS--;
        for (int e = G.as[v]; e < G.as[v + 1]; e++) a[G.av[e]]--;
    }
    for (int k = 0; k < qlen; k++) queued[qbuf[k]] = 0;
    qlen = qhead = 0;
}

/* decode a state's key into inS, a[], sizeS, cutS */
static void decode(uint32_t id) {
    const u64 *k = keys + (size_t)id * kw;
    memset(inS, 0, nwN * sizeof(u64));
    memset(a, 0, G.n * sizeof(int));
    sizeS = 0;
    if (opt_nocover) {
        for (int v = 0; v < G.n; v++) if (IN(k, v)) { SET(inS, v); sizeS++; }
    } else {
        for (int j = 0; j < tau; j++) if (IN(k, j)) { SET(inS, cov[j]); sizeS++; }
    }
    for (int v = 0; v < G.n; v++) if (IN(inS, v))
        for (int e = G.as[v]; e < G.as[v + 1]; e++) a[G.av[e]]++;
    if (!opt_nocover) {
        /* non-cover vertices of rank <= 0; they are independent, so adding one
         * changes only a[] of cover vertices */
        for (int v = 0; v < G.n; v++) if (!incov[v] && !IN(inS, v) && rank_(v) <= 0) {
            SET(inS, v); sizeS++;
            for (int e = G.as[v]; e < G.as[v + 1]; e++) a[G.av[e]]++;
        }
    }
    cutS = 0;
    for (int v = 0; v < G.n; v++) if (IN(inS, v)) cutS += G.deg[v] - a[v];
}

/* Y list for x at the current S; returns |Y| */
static int ylist(int x) {
    int ny = 0;
    if (opt_nocover) return 0;
    for (int e = G.as[x]; e < G.as[x + 1]; e++) {
        int u = G.av[e];
        if (!IN(inS, u) && !incov[u] && (G.deg[u] & 1) && rank_(u) == 1) Ybuf[ny++] = u;
    }
    return ny;
}

static inline int best_i(int dx, int ny) {
    int i = dx > 0 ? dx / 2 : 0;
    return i < ny ? i : ny;
}

/* apply child (x, i) to the current decoded S, in place */
static void apply_child(int x, int i) {
    ylist(x);
    for (int k = 0; k < i; k++) add_v(Ybuf[k]);
    add_v(x);
    closure();
}

static void make_key(u64 *k) {
    memset(k, 0, kw * sizeof(u64));
    if (opt_nocover) { memcpy(k, inS, kw * sizeof(u64)); return; }
    for (int j = 0; j < tau; j++) if (IN(inS, cov[j])) SET(k, j);
}


/* twin classes (true: N[u]=N[v]; false: N(u)=N(v)); swapping twins is an
 * automorphism, so a vertex is chosen only if its smaller twins are placed */
static const Graph *tw_g; static int tw_closed;
static int tw_cmp(const void *x, const void *y) {
    int u = *(const int *)x, v = *(const int *)y;
    const Graph *g = tw_g;
    int du = g->deg[u] + tw_closed, dv = g->deg[v] + tw_closed;
    if (du != dv) return du - dv;
    /* compare sorted (closed) neighbour lists; CSR lists are sorted */
    int i = g->as[u], j = g->as[v], iu = 0, jv = 0; /* merge in u / v themselves when closed */
    for (int k = 0; k < du; k++) {
        int a1, b1;
        if (tw_closed && !iu && (i == g->as[u + 1] || g->av[i] > u)) { a1 = u; iu = 1; } else a1 = g->av[i++];
        if (tw_closed && !jv && (j == g->as[v + 1] || g->av[j] > v)) { b1 = v; jv = 1; } else b1 = g->av[j++];
        if (a1 != b1) return a1 - b1;
    }
    return u - v;
}
static int tw_same(int u, int v) {
    int x = u, y = v;
    const Graph *g = tw_g;
    int du = g->deg[x] + tw_closed, dv = g->deg[y] + tw_closed;
    if (du != dv) return 0;
    int i = g->as[x], j = g->as[y], iu = 0, jv = 0;
    for (int k = 0; k < du; k++) {
        int a1, b1;
        if (tw_closed && !iu && (i == g->as[x + 1] || g->av[i] > x)) { a1 = x; iu = 1; } else a1 = g->av[i++];
        if (tw_closed && !jv && (j == g->as[y + 1] || g->av[j] > y)) { b1 = y; jv = 1; } else b1 = g->av[j++];
        if (a1 != b1) return 0;
    }
    return 1;
}
static void twins(void) {
    int n = G.n;
    int *cls = malloc(n * sizeof(int)), *ord = malloc(n * sizeof(int)), nc = 0;
    for (int v = 0; v < n; v++) cls[v] = -1;
    tw_g = &G;
    for (tw_closed = 1; tw_closed >= 0; tw_closed--) {
        for (int v = 0; v < n; v++) ord[v] = v;
        qsort(ord, n, sizeof(int), tw_cmp);
        for (int k = 0; k < n; ) {
            int l = k + 1;
            while (l < n && tw_same(ord[k], ord[l])) l++;
            if (l - k > 1) {
                int fresh = 1;
                for (int t = k; t < l; t++) if (cls[ord[t]] >= 0) fresh = 0;
                if (fresh) { for (int t = k; t < l; t++) cls[ord[t]] = nc; nc++; }
            }
            k = l;
        }
    }
    for (int v = 0; v < n; v++) if (cls[v] < 0 || opt_notwins) cls[v] = -1;
    /* renumber classes, members in increasing order */
    tw_cls = malloc(n * sizeof(int)); tw_start = calloc(nc + 2, sizeof(int)); tw_mem = malloc((n + 1) * sizeof(int));
    for (int v = 0; v < n; v++) { tw_cls[v] = cls[v]; if (cls[v] >= 0) tw_start[cls[v] + 1]++; }
    for (int c = 0; c < nc; c++) tw_start[c + 1] += tw_start[c];
    int *fill = calloc(nc + 1, sizeof(int));
    for (int v = 0; v < n; v++) if (cls[v] >= 0) tw_mem[tw_start[cls[v]] + fill[cls[v]]++] = v;
    free(fill); free(cls); free(ord);
}
static inline int twin_blocked(int x) {
    int c = tw_cls[x];
    if (c < 0) return 0;
    for (int k = tw_start[c]; k < tw_start[c + 1] && tw_mem[k] < x; k++) if (!IN(inS, tw_mem[k])) return 1;
    return 0;
}

static int done_id = -1;

static void expand(uint32_t id, int B) {
    decode(id);
    expansions++;
    int c = cutS, minw = INT32_MAX;
    for (int x = 0; x < G.n; x++) {
        if (IN(inS, x) || (!opt_nocover && !incov[x]) || twin_blocked(x)) continue;
        int dx = rank_(x);
        int ny = ylist(x);
        int i = best_i(dx, ny);
        int w = c + (i > dx - i ? i : dx - i);
        if (w > B) { if (w < minw) minw = w; continue; }
        apply_child(x, i);
        make_key(keybuf);
        int full = sizeS == G.n, isnew;
        undo();
        uint32_t cid = insert(keybuf, id, x, i, &isnew);
        if (isnew) {
            if (full) { done_id = (int)cid; return; }
            spush(cid);
        }
    }
    if (minw != INT32_MAX) {
        if (minw >= nbuckets) { fprintf(stderr, "internal: bucket overflow\n"); exit(4); }
        vpush(&bucket[minw], id);
    }
}

static int *km_mate, *km_vis, km_stamp;
static int kuhn(int v) {
    for (int e = G.as[v]; e < G.as[v + 1]; e++) {
        int u = G.av[e];
        if (km_vis[u] == km_stamp) continue;
        km_vis[u] = km_stamp;
        if (km_mate[u] < 0 || kuhn(km_mate[u])) { km_mate[u] = v; km_mate[v] = u; return 1; }
    }
    return 0;
}

/* solve one connected graph; returns cw (or -1 and *lb if a limit was hit);
 * fills order[] (local vertex numbers) */
static int solve(int *order, int *lb, size_t *states_out) {
    int n = G.n;
    nwN = (n + 63) / 64;
    /* ---- vertex cover */
    incov = calloc(n, sizeof(int)); cidx = malloc(n * sizeof(int)); cov = malloc(n * sizeof(int));
    {
        int *col = malloc(n * sizeof(int)), *q = malloc(n * sizeof(int)), bip = 1;
        for (int v = 0; v < n; v++) col[v] = -1;
        for (int s = 0; s < n; s++) if (col[s] < 0) {
            int h = 0, t = 0; q[t++] = s; col[s] = 0;
            while (h < t) { int v = q[h++];
                for (int e = G.as[v]; e < G.as[v + 1]; e++) { int u = G.av[e];
                    if (col[u] < 0) { col[u] = 1 - col[v]; q[t++] = u; } else if (col[u] == col[v]) bip = 0; } }
        }
        if (bip) {   /* Konig: max matching L=col0 -> R=col1, then alternating reachability */
            km_mate = malloc(n * sizeof(int)); km_vis = calloc(n, sizeof(int)); km_stamp = 0;
            int *mate = km_mate;
            for (int v = 0; v < n; v++) mate[v] = -1;
            for (int s = 0; s < n; s++) if (col[s] == 0) { km_stamp++; kuhn(s); }
            /* Z: reachable from unmatched L by alternating paths */
            int *Z = calloc(n, sizeof(int)); int h = 0, t = 0;
            for (int v = 0; v < n; v++) if (col[v] == 0 && mate[v] < 0) { Z[v] = 1; q[t++] = v; }
            while (h < t) { int v = q[h++];
                for (int e = G.as[v]; e < G.as[v + 1]; e++) { int u = G.av[e];
                    if (!Z[u] && mate[v] != u) { Z[u] = 1; if (mate[u] >= 0 && !Z[mate[u]]) { Z[mate[u]] = 1; q[t++] = mate[u]; } } } }
            for (int v = 0; v < n; v++) incov[v] = col[v] == 0 ? !Z[v] : Z[v];
            free(km_mate); free(km_vis); free(Z);
        } else {     /* greedy max degree, then drop redundant vertices */
            int *d = malloc(n * sizeof(int));
            for (int v = 0; v < n; v++) d[v] = G.deg[v];
            for (;;) {
                int best = -1;
                for (int v = 0; v < n; v++) if (!incov[v] && d[v] > 0 && (best < 0 || d[v] > d[best])) best = v;
                if (best < 0) break;
                incov[best] = 1;
                for (int e = G.as[best]; e < G.as[best + 1]; e++) d[G.av[e]]--;
                d[best] = 0;
            }
            for (int v = 0; v < n; v++) if (incov[v]) {
                int red = 1;
                for (int e = G.as[v]; e < G.as[v + 1]; e++) if (!incov[G.av[e]]) { red = 0; break; }
                if (red) incov[v] = 0;
            }
            free(d);
        }
        free(col); free(q);
    }
    if (opt_nocover) for (int v = 0; v < n; v++) incov[v] = 1;
    twins();
    /* make the cover twin-closed, so that twin swaps preserve it */
    for (int v = 0; v < n; v++) if (incov[v] && tw_cls[v] >= 0)
        for (int k = tw_start[tw_cls[v]]; k < tw_start[tw_cls[v] + 1]; k++) incov[tw_mem[k]] = 1;
    tau = 0;
    for (int v = 0; v < n; v++) { cidx[v] = incov[v] ? tau : -1; if (incov[v]) cov[tau++] = v; }
    /* check cover */
    for (int v = 0; v < n; v++) for (int e = G.as[v]; e < G.as[v + 1]; e++)
        if (!incov[v] && !incov[G.av[e]]) { fprintf(stderr, "internal: not a vertex cover\n"); exit(4); }
    kw = opt_nocover ? nwN : (tau + 63) / 64; if (kw == 0) kw = 1;

    /* ---- work arrays */
    a = calloc(n, sizeof(int)); inS = calloc(nwN, sizeof(u64));
    queued = calloc(n, sizeof(int)); qbuf = malloc((n + 1) * sizeof(int));
    added = malloc((n + 1) * sizeof(int)); Ybuf = malloc((n + 1) * sizeof(int));
    keybuf = calloc(kw, sizeof(u64));
    ns = 0; scap = 0; keys = NULL; par = NULL; sx = NULL; si = NULL;
    ht = NULL; rehash(1 << 16);
    sp = 0;
    nbuckets = G.m + 2;
    bucket = calloc(nbuckets, sizeof(Vec));
    done_id = -1;

    /* ---- root: closure of {} */
    nadded = 0; qlen = qhead = 0; sizeS = 0; cutS = 0;
    for (int v = 0; v < n; v++) if (rank_(v) <= 0) { queued[v] = 1; qbuf[qlen++] = v; }
    closure();
    make_key(keybuf);
    int full0 = sizeS == n, isnew;
    undo();
    uint32_t root = insert(keybuf, UINT32_MAX, -1, 0, &isnew);
    int B = 0;
    for (int v = 0; v < n; v++) { int h = (G.deg[v] + 1) / 2; if (h > B) B = h; }
    int result = -1;
    if (full0) { done_id = (int)root; B = 0; }
    else spush(root);
    while (done_id < 0) {
        while (sp > 0 && done_id < 0) {
            expand(stack[--sp], B);
            if ((expansions & 1023) == 0) {
                if ((opt_T > 0 && now() - t_start > opt_T) || (opt_M > 0 && ns > opt_M)) goto out;
            }
        }
        if (done_id >= 0) break;
        int b = B + 1;
        while (b < nbuckets && bucket[b].len == 0) b++;
        if (b >= nbuckets) { fprintf(stderr, "internal: search exhausted\n"); exit(4); }
        B = b;
        if (opt_verbose) fprintf(stderr, "  level %d: states=%zu expansions=%zu rescan=%zu t=%.2f\n",
                                 B, ns, expansions, bucket[B].len, now() - t_start);
        for (size_t k = bucket[B].len; k-- > 0;) spush(bucket[B].v[k]);
        free(bucket[B].v); bucket[B].v = NULL; bucket[B].len = bucket[B].cap = 0;
    }
    result = B;
    /* ---- reconstruct */
    {
        size_t len = 0; uint32_t *chain = malloc((ns + 1) * sizeof(uint32_t));
        for (uint32_t id = (uint32_t)done_id; id != UINT32_MAX; id = par[id]) chain[len++] = id;
        int pos = 0;
        /* root closure */
        memset(inS, 0, nwN * sizeof(u64)); memset(a, 0, n * sizeof(int)); sizeS = 0; cutS = 0;
        nadded = 0; qlen = qhead = 0;
        for (int v = 0; v < n; v++) if (rank_(v) <= 0) { queued[v] = 1; qbuf[qlen++] = v; }
        closure();
        for (int k = 0; k < nadded; k++) order[pos++] = added[k];
        undo();
        for (size_t c = len - 1; c-- > 0;) {
            uint32_t id = chain[c];
            decode(par[id]);
            nadded = 0;
            apply_child(sx[id], si[id]);
            /* the decoded parent is a set; the order inside it was output already */
            for (int k = 0; k < nadded; k++) order[pos++] = added[k];
            undo();
        }
        free(chain);
        if (pos != n) { fprintf(stderr, "internal: reconstructed %d of %d vertices\n", pos, n); exit(4); }
    }
out:
    if (result < 0) *lb = B;
    *states_out = ns;
    for (int b = 0; b < nbuckets; b++) free(bucket[b].v);
    free(bucket); free(keys); free(par); free(sx); free(si); free(ht); ht = NULL;
    free(a); free(inS); free(queued); free(qbuf); free(added); free(Ybuf); free(keybuf);
    free(incov); free(cidx); free(cov); free(tw_cls); free(tw_start); free(tw_mem);
    return result;
}

static int ordering_cutwidth(const Graph *g, const int *order) {
    int *pos = malloc(g->n * sizeof(int)), cut = 0, w = 0;
    for (int i = 0; i < g->n; i++) pos[order[i]] = i;
    for (int i = 0; i < g->n; i++) {
        int v = order[i];
        for (int e = g->as[v]; e < g->as[v + 1]; e++) cut += pos[g->av[e]] > i ? 1 : -1;
        if (cut > w) w = cut;
    }
    free(pos);
    return w;
}

static int cmp_ll(const void *x, const void *y) { long long p = *(const long long *)x, q = *(const long long *)y; return (p > q) - (p < q); }
static int cmp_int(const void *x, const void *y) { return *(const int *)x - *(const int *)y; }

int main(int argc, char **argv) {
    int quiet = 0; const char *path = NULL;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-C")) opt_nocover = 1;
        else if (!strcmp(argv[i], "-W")) opt_notwins = 1;
        else if (!strcmp(argv[i], "-q")) quiet = 1;
        else if (!strcmp(argv[i], "-v")) opt_verbose = 1;
        else if (!strcmp(argv[i], "-T") && i + 1 < argc) opt_T = atof(argv[++i]);
        else if (!strcmp(argv[i], "-M") && i + 1 < argc) opt_M = strtoull(argv[++i], NULL, 10);
        else if (argv[i][0] == '-' && argv[i][1]) { fprintf(stderr, "unknown option %s\n", argv[i]); return 1; }
        else path = argv[i];
    }
    FILE *f = path ? fopen(path, "r") : stdin;
    if (!f) { perror(path); return 1; }
    EdgeList el; char err[200];
    if (el_read(f, 1 << 24, &el, err, sizeof err)) { fprintf(stderr, "%s\n", err); return 1; }
    if (f != stdin) fclose(f);
    t_start = now();
    int n = el.n;

    /* simple graph in CSR (merge parallel edges, drop loops) */
    int *eu = malloc((2 * (size_t)el.m + 1) * sizeof(int)), *ev = malloc((2 * (size_t)el.m + 1) * sizeof(int));
    size_t me = 0; int dup = 0;
    for (int k = 0; k < el.m; k++) {
        int u = el.e[k][0], v = el.e[k][1];
        if (u == v) continue;
        eu[me] = u; ev[me++] = v; eu[me] = v; ev[me++] = u;
    }
    /* sort directed pairs to dedupe */
    {
        long long *key = malloc((me + 1) * sizeof(long long));
        for (size_t k = 0; k < me; k++) key[k] = (long long)eu[k] * n + ev[k];
        qsort(key, me, sizeof *key, cmp_ll);
        size_t w = 0;
        for (size_t k = 0; k < me; k++) if (k == 0 || key[k] != key[k - 1]) key[w++] = key[k]; else dup++;
        me = w;
        for (size_t k = 0; k < me; k++) { eu[k] = (int)(key[k] / n); ev[k] = (int)(key[k] % n); }
        free(key);
    }
    if (dup) fprintf(stderr, "warning: %d parallel edges merged\n", dup / 2);
    Graph full = { n, (int)(me / 2), malloc((n + 1) * sizeof(int)), malloc((me + 1) * sizeof(int)), calloc(n + 1, sizeof(int)) };
    for (size_t k = 0; k < me; k++) full.deg[eu[k]]++;
    full.as[0] = 0;
    for (int v = 0; v < n; v++) full.as[v + 1] = full.as[v] + full.deg[v];
    for (size_t k = 0; k < me; k++) full.av[k] = ev[k];      /* already sorted by eu */

    /* components */
    int *comp = malloc((n + 1) * sizeof(int)), *q = malloc((n + 1) * sizeof(int)), ncomp = 0;
    for (int v = 0; v < n; v++) comp[v] = -1;
    int *gorder = malloc((n + 1) * sizeof(int)), gpos = 0;
    int cw = 0, lb = 0, solved = 1; size_t states = 0;
    int maxtau = 0;
    int *loc = malloc((n + 1) * sizeof(int));
    for (int s = 0; s < n; s++) if (comp[s] < 0) {
        int h = 0, t = 0; q[t++] = s; comp[s] = ncomp;
        while (h < t) { int v = q[h++];
            for (int e = full.as[v]; e < full.as[v + 1]; e++) { int u = full.av[e]; if (comp[u] < 0) { comp[u] = ncomp; q[t++] = u; } } }
        ncomp++;
        int cn = t;
        if (cn == 1) { gorder[gpos++] = s; continue; }
        /* local graph; vertices in increasing global number for determinism */
        qsort(q, cn, sizeof(int), cmp_int);
        for (int k = 0; k < cn; k++) loc[q[k]] = k;
        int cm2 = 0; for (int k = 0; k < cn; k++) cm2 += full.deg[q[k]];
        G.n = cn; G.m = cm2 / 2;
        G.as = malloc((cn + 1) * sizeof(int)); G.av = malloc((cm2 + 1) * sizeof(int)); G.deg = malloc(cn * sizeof(int));
        G.as[0] = 0;
        for (int k = 0; k < cn; k++) {
            int v = q[k]; G.deg[k] = full.deg[v];
            for (int e = full.as[v]; e < full.as[v + 1]; e++) G.av[G.as[k] + e - full.as[v]] = loc[full.av[e]];
            G.as[k + 1] = G.as[k] + full.deg[v];
        }
        int *lorder = malloc(cn * sizeof(int)), clb = 0; size_t cst = 0;
        int r = solve(lorder, &clb, &cst);
        if (tau > maxtau) maxtau = tau;
        states += cst;
        if (r < 0) { solved = 0; if (clb > lb) lb = clb; }
        else {
            int chk = ordering_cutwidth(&G, lorder);
            if (chk != r) { fprintf(stderr, "internal: ordering has width %d, search said %d\n", chk, r); return 4; }
            if (r > cw) cw = r;
            for (int k = 0; k < cn; k++) gorder[gpos++] = q[lorder[k]];
        }
        free(lorder); free(G.as); free(G.av); free(G.deg);
        if (!solved) break;
    }
    double t = now() - t_start;
    if (solved) {
        int chk = ordering_cutwidth(&full, gorder);
        if (chk != cw) { fprintf(stderr, "internal: final width %d != %d\n", chk, cw); return 4; }
        printf("n=%d m=%d tau=%d cw=%d states=%zu expansions=%zu time=%.3f\n", n, full.m, maxtau, cw, states, expansions, t);
        if (!quiet) {
            printf("order:");
            for (int k = 0; k < n; k++) printf(" %s", el.names[gorder[k]]);
            printf("\n");
        }
        return 0;
    }
    if (cw > lb) lb = cw;
    printf("n=%d m=%d tau=%d cw=? lb=%d states=%zu expansions=%zu time=%.3f\n", n, full.m, maxtau, lb, states, expansions, t);
    return 2;
}
