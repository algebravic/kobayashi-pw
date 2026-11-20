/* bab.c -- C port of the branch-and-bound algorithm for the vertex separation
 * (pathwidth) of Coudert, Mazauric and Nisse,
 *   D. Coudert, D. Mazauric, N. Nisse, "Experimental evaluation of a branch
 *   and bound algorithm for computing pathwidth", SEA 2014 / Inria RR-8470,
 * translated from SageMath's Cython implementation
 *   sage/graphs/graph_decompositions/vertex_separation.pyx
 *   (vertex_separation_BAB and vertex_separation_BAB_C; David Coudert, 2015-01).
 *
 * The translation keeps the algorithm step for step: the same greedy steps,
 * the same candidate order (sorted by (lower bound, vertex)), the same pruning,
 * and the same prefix-storage rule.  The only data-structure change is that
 * Sage's Python set of frozensets is replaced by a C hash set of bitsets.  With
 * vertices numbered as in Sage (list(G)), the search is identical, including
 * the number of stored prefixes and the ordering returned.
 *
 * Convention: as in Sage, the cost of a prefix P is |N+(P)|, the out-
 * neighbours of P outside P.  For undirected graphs this is the usual vertex
 * separation; for digraphs it is the vertex separation of the reversed digraph
 * in kpw's (in-neighbour) convention, which has the same value.
 *
 * Original module: Copyright (C) 2011 Nathann Cohen <nathann.cohen@gmail.com>;
 * BAB code by David Coudert.  This translation is distributed under the same
 * licence: GNU General Public License, version 2 or (at your option) any later
 * version, http://www.gnu.org/licenses/.  (The rest of this repository is not
 * derived from Sage.)
 *
 * Usage: bab [-d] [-k CUT_OFF] [-u UPPER_BOUND] [-l MAX_PREFIX_LENGTH]
 *            [-m MAX_PREFIX_NUMBER] [-r] [-q] [-v] [FILE]
 *   -d  directed ("u v" = arc u->v)
 *   -k  stop as soon as a solution of width <= CUT_OFF is found (Sage: cut_off; default 0)
 *   -u  search only for width < UPPER_BOUND (default n); prints pw=-1 if none
 *   -l  store prefixes of length <= MAX_PREFIX_LENGTH (default 20, as in Sage)
 *   -m  store at most MAX_PREFIX_NUMBER prefixes (default 1000000, as in Sage)
 *   -r  print the ordering reversed (frontier-DP convention for undirected graphs)
 *   -q  do not print the ordering;  -v  print each improved upper bound
 * Input: edge list as for kpw (see edgelist.h); any number of vertices.
 * Output: "n=.. pw=.. nodes=.. stored_prefixes=..", then "order: ..." (names).
 * Build: cc -O3 -march=native -o bab bab.c
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "edgelist.h"

typedef uint64_t u64;

static int n, nw;                 /* vertices, 64-bit words per bitset */
static u64 *H;                    /* H[j*nw ...]: out-neighbourhood of j */
static u64 *pool;                 /* 3n+2 bitsets, as Sage's bm_pool */
static int *prefix, *positions, *best_seq;
static int *delta_pool;           /* per level: up to n pairs (delta, vertex) */
static int cut_off, max_prefix_length, verbose;
static long max_prefix_number;
static long nodes;

#define ROW(base, i) ((base) + (size_t)(i) * nw)

/* ---- bitsets of nw words ---- */
static inline void bs_copy(u64 *d, const u64 *s) { memcpy(d, s, nw * sizeof(u64)); }
static inline void bs_add(u64 *b, int i) { b[i >> 6] |= 1ULL << (i & 63); }
static inline void bs_discard(u64 *b, int i) { b[i >> 6] &= ~(1ULL << (i & 63)); }
static inline int bs_in(const u64 *b, int i) { return (b[i >> 6] >> (i & 63)) & 1; }
static inline int bs_issubset(const u64 *a, const u64 *b) {
    for (int k = 0; k < nw; k++) if (a[k] & ~b[k]) return 0;
    return 1;
}
static inline void bs_union(u64 *d, const u64 *a, const u64 *b) { for (int k = 0; k < nw; k++) d[k] = a[k] | b[k]; }
static inline void bs_difference(u64 *d, const u64 *a, const u64 *b) { for (int k = 0; k < nw; k++) d[k] = a[k] & ~b[k]; }
static inline int bs_len(const u64 *b) { int c = 0; for (int k = 0; k < nw; k++) c += __builtin_popcountll(b[k]); return c; }
static inline int bs_first(const u64 *b) {
    for (int k = 0; k < nw; k++) if (b[k]) return k * 64 + __builtin_ctzll(b[k]);
    return -1;
}

/* ---- prefix storage: hash set of bitsets (replaces Python set of frozensets) ---- */
static u64 *st_keys; static unsigned char *st_used; static size_t st_cap, st_len;
static size_t st_hash(const u64 *b) {
    u64 h = 0x9e3779b97f4a7c15ULL;
    for (int k = 0; k < nw; k++) { h ^= b[k]; h *= 0xff51afd7ed558ccdULL; h ^= h >> 32; }
    return (size_t)h;
}
static size_t st_slot(const u64 *b) {
    size_t i = st_hash(b) & (st_cap - 1);
    while (st_used[i] && memcmp(ROW(st_keys, i), b, nw * sizeof(u64))) i = (i + 1) & (st_cap - 1);
    return i;
}
static int st_contains(const u64 *b) { return st_cap && st_used[st_slot(b)]; }
static void st_add(const u64 *b) {
    if (2 * (st_len + 1) > st_cap) {
        u64 *ok = st_keys; unsigned char *ou = st_used; size_t oc = st_cap;
        st_cap = oc ? 2 * oc : 1024;
        st_keys = malloc(st_cap * nw * sizeof(u64)); st_used = calloc(st_cap, 1);
        if (!st_keys || !st_used) { fprintf(stderr, "out of memory\n"); exit(3); }
        st_len = 0;
        for (size_t i = 0; i < oc; i++) if (ou[i]) {
            size_t j = st_slot(ROW(ok, i));
            memcpy(ROW(st_keys, j), ROW(ok, i), nw * sizeof(u64)); st_used[j] = 1; st_len++;
        }
        free(ok); free(ou);
    }
    size_t i = st_slot(b);
    if (!st_used[i]) { memcpy(ROW(st_keys, i), b, nw * sizeof(u64)); st_used[i] = 1; st_len++; }
}

static inline void invert_positions(int pos_a, int pos_b) {      /* _my_invert_positions */
    if (pos_a != pos_b) {
        int a = prefix[pos_a], b = prefix[pos_b];
        int t = positions[a]; positions[a] = positions[b]; positions[b] = t;
        prefix[pos_a] = b; prefix[pos_b] = a;
    }
}

static int cmp_pair(const void *x, const void *y) {              /* Python tuple order */
    const int *a = x, *b = y;
    if (a[0] != b[0]) return a[0] < b[0] ? -1 : 1;
    return (a[1] > b[1]) - (a[1] < b[1]);
}

/* vertex_separation_BAB_C */
static int bab(int level, const u64 *b_prefix, const u64 *b_prefix_and_neighborhood,
               int upper_bound, int current_cost) {
    nodes++;
    if (level == n) {
        if (current_cost < upper_bound) {
            memcpy(best_seq, prefix, n * sizeof(int));
            if (verbose) printf("New upper bound: %d\n", current_cost);
        }
        return current_cost;
    }
    int loc_level = level;
    u64 *loc_b_prefix = ROW(pool, 3 * level);
    u64 *loc_b_pref_and_neigh = ROW(pool, 3 * level + 1);
    u64 *b_tmp = ROW(pool, 3 * level + 2);
    bs_copy(loc_b_prefix, b_prefix);
    bs_copy(loc_b_pref_and_neigh, b_prefix_and_neighborhood);

    /* ==> Greedy steps: (i) all out-neighbours of j in prefix or its
     * out-neighbourhood; (ii) j is an out-neighbour of the prefix and all but
     * one of its out-neighbours are in the prefix or its out-neighbourhood. */
    int select_it = 0, i = loc_level;
    while (i < n) {
        int j = prefix[i];
        if (bs_issubset(ROW(H, j), loc_b_pref_and_neigh)) {
            bs_add(loc_b_pref_and_neigh, j);
            select_it = 1;
        } else if (bs_in(loc_b_pref_and_neigh, j) && !bs_in(loc_b_prefix, j)) {
            bs_difference(b_tmp, ROW(H, j), loc_b_pref_and_neigh);
            if (bs_len(b_tmp) == 1) {
                bs_add(loc_b_pref_and_neigh, bs_first(b_tmp));
                select_it = 1;
            }
        }
        if (select_it) {
            invert_positions(i, loc_level);
            loc_level++;
            bs_add(loc_b_prefix, j);
            select_it = 0;
            i = loc_level;
        } else {
            i++;
        }
    }
    if (loc_level == n) {
        if (current_cost < upper_bound) {
            memcpy(best_seq, prefix, n * sizeof(int));
            if (verbose) printf("New upper bound: %d\n", current_cost);
        }
        return current_cost;
    }

    /* ==> Prefix storage test */
    if (loc_level <= max_prefix_length && st_contains(loc_b_prefix))
        return upper_bound;

    /* ==> Sort and prune: lower bound for each extension */
    int *delta = delta_pool + (size_t)2 * n * level, nd = 0;
    for (i = loc_level; i < n; i++) {
        int j = prefix[i];
        bs_union(b_tmp, loc_b_pref_and_neigh, ROW(H, j));
        bs_difference(b_tmp, b_tmp, loc_b_prefix);
        bs_discard(b_tmp, j);
        int delta_i = bs_len(b_tmp);
        if (delta_i < upper_bound) { delta[2 * nd] = delta_i; delta[2 * nd + 1] = j; nd++; }
    }
    qsort(delta, nd, 2 * sizeof(int), cmp_pair);

    /* ==> Recursion */
    for (int k = 0; k < nd; k++) {
        int delta_i = delta[2 * k] > current_cost ? delta[2 * k] : current_cost;
        int v = delta[2 * k + 1];
        if (delta_i >= upper_bound) break;
        bs_union(b_tmp, loc_b_pref_and_neigh, ROW(H, v));
        bs_discard(b_tmp, v);
        invert_positions(positions[v], loc_level);
        bs_add(loc_b_prefix, v);
        int cost_i = bab(loc_level + 1, loc_b_prefix, b_tmp, upper_bound, delta_i);
        bs_discard(loc_b_prefix, v);
        if (cost_i < upper_bound) {
            upper_bound = cost_i;
            if (upper_bound <= cut_off) break;
        }
    }

    /* ==> Update prefix storage */
    if (loc_level <= max_prefix_length && current_cost < upper_bound
            && (long)st_len < max_prefix_number)
        st_add(loc_b_prefix);
    return upper_bound;
}

int main(int argc, char **argv) {
    int directed = 0, reverse = 0, quiet = 0, upper_bound = -1;
    const char *path = NULL;
    max_prefix_length = 20; max_prefix_number = 1000000; cut_off = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-d")) directed = 1;
        else if (!strcmp(argv[i], "-r")) reverse = 1;
        else if (!strcmp(argv[i], "-q")) quiet = 1;
        else if (!strcmp(argv[i], "-v")) verbose = 1;
        else if (!strcmp(argv[i], "-k") && i + 1 < argc) cut_off = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-u") && i + 1 < argc) upper_bound = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-l") && i + 1 < argc) max_prefix_length = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-m") && i + 1 < argc) max_prefix_number = atol(argv[++i]);
        else if (argv[i][0] == '-') { fprintf(stderr, "unknown option %s\n", argv[i]); return 1; }
        else path = argv[i];
    }
    FILE *f = path ? fopen(path, "r") : stdin;
    if (!f) { perror(path); return 1; }
    EdgeList el; char err[200];
    if (el_read(f, 1 << 20, &el, err, sizeof err)) { fprintf(stderr, "%s\n", err); return 1; }
    if (f != stdin) fclose(f);
    n = el.n;
    if (n == 0) { printf("n=0 pw=0 nodes=0 stored_prefixes=0\n"); if (!quiet) printf("order:\n"); return 0; }
    if (upper_bound < 0) upper_bound = n;
    if (upper_bound < 1) { fprintf(stderr, "the input upper bound must be at least 1\n"); return 1; }
    nw = (n + 63) / 64;
    H = calloc((size_t)n * nw, sizeof(u64));
    pool = calloc((size_t)(3 * n + 2) * nw, sizeof(u64));
    prefix = malloc(n * sizeof(int)); positions = malloc(n * sizeof(int)); best_seq = malloc(n * sizeof(int));
    delta_pool = malloc((size_t)2 * n * (n + 1) * sizeof(int));
    if (!H || !pool || !prefix || !positions || !best_seq || !delta_pool) { fprintf(stderr, "out of memory\n"); return 3; }
    for (int k = 0; k < el.m; k++) {               /* dense_graph_init: H[u] = out-neighbours */
        int u = el.e[k][0], v = el.e[k][1];
        if (u == v) continue;
        bs_add(ROW(H, u), v);
        if (!directed) bs_add(ROW(H, v), u);
    }
    for (int i = 0; i < n; i++) { prefix[i] = i; positions[i] = i; best_seq[i] = i; }

    int width = bab(0, ROW(pool, 3 * n), ROW(pool, 3 * n + 1), upper_bound, 0);
    if (width >= upper_bound) width = -1;

    /* verify: max over prefixes of |N+(prefix)| */
    if (width >= 0) {
        u64 *P = calloc(nw, sizeof(u64)), *PN = calloc(nw, sizeof(u64)), *T = calloc(nw, sizeof(u64));
        int w = 0;
        for (int i = 0; i < n; i++) {
            int v = best_seq[i];
            bs_add(P, v); bs_union(PN, PN, ROW(H, v));
            bs_difference(T, PN, P);
            int c = bs_len(T); if (c > w) w = c;
        }
        if (w != width) { fprintf(stderr, "VERIFY FAILED: ordering has width %d, reported %d\n", w, width); return 2; }
    }
    printf("n=%d pw=%d nodes=%ld stored_prefixes=%zu\n", n, width, nodes, st_len);
    if (!quiet && width >= 0) {
        printf("order:");
        for (int i = 0; i < n; i++) printf(" %s", el.names[best_seq[reverse ? n - 1 - i : i]]);
        printf("\n");
    }
    return 0;
}
