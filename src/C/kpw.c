/* kpw.c -- exact vertex separation (pathwidth) by a bucketed bottleneck search
 * over Kobayashi's relevant sets, n <= 64.  Same algorithm as
 * kobayashi_pw.core.pathwidth.
 *
 * Usage: kpw [options] [FILE]
 *   FILE   edge list, at most 64 vertices: "u v [ignored...]" per line, vertex
 *          names arbitrary strings; a lone token is an isolated vertex; '#'
 *          starts a comment (see edgelist.h for the numbering).  Default: stdin.
 *   -d     directed: "u v" is the arc u->v
 *   -g     also apply the second greedy rule of Coudert-Mazauric-Nisse (2014),
 *          Lemma 6: add v in N(U) when exactly one in-neighbour of v lies outside
 *          U u N(U).  This preserves the boundary size; it yields fewer sets but a
 *          smaller family of orderings in -c mode.
 *   -c     complete mode: after pw is found, finish level pw (instead of stopping
 *          at V), then keep only the sets from which V is reachable through arcs
 *          of cost <= pw.  Every path from (empty)* to V in the resulting DAG is a
 *          pw-optimal ordering.
 *   -o F   with -c: write the pruned DAG to F (format KPWDAG3, doc/dag_format.md)
 *   -r     print the ordering reversed, i.e. in the convention that counts the
 *          prefix vertices with a later neighbour (Kinnersley's V_L); for
 *          undirected graphs this is the frontier of a left-to-right frontier DP
 *   -q     do not print the ordering
 *
 * Output: "n=.. pw=.. sets=.. pairs=.. rescans=.." [+ "dag=.." with -c], then
 * "order: ..." with the input's vertex names.  The width of the printed
 * ordering is recomputed and checked.
 * Build: cc -O3 -march=native -o kpw kpw.c
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "edgelist.h"

typedef uint64_t u64;
static EdgeList el;
static int n, greedy2;
static u64 nin[64], full;

/* ---------- growable arrays ---------- */
typedef struct { u64 S, nb; int x; } Pair;
typedef struct { u64 S, nb; } Ent;
typedef struct { void *a; size_t len, cap, sz; } Vec;
static void push(Vec *v, const void *e) {
    if (v->len == v->cap) { v->cap = v->cap ? 2 * v->cap : 1024; v->a = realloc(v->a, v->cap * v->sz); }
    memcpy((char *)v->a + v->len++ * v->sz, e, v->sz);
}

/* ---------- hash map: set mask -> (parent mask, x, flag) ----------
 * key == 0 marks an empty slot; key = S+1.  The full set V is never stored
 * (it would overflow when n = 64); its parent link is kept in fullpar/fullx. */
typedef struct { u64 key, par; int x; int good; } Slot;
static Slot *tab; static size_t tcap, tlen;
static inline size_t hsh(u64 k) { k ^= k >> 33; k *= 0xff51afd7ed558ccdULL; k ^= k >> 33; return (size_t)k; }
static void rehash(void);
static Slot *find(u64 S) {
    u64 k = S + 1; size_t i = hsh(k) & (tcap - 1);
    while (tab[i].key && tab[i].key != k) i = (i + 1) & (tcap - 1);
    return &tab[i];
}
static int insert(u64 S, u64 par, int x) {      /* 1 if new */
    if (2 * (tlen + 1) > tcap) rehash();
    Slot *s = find(S);
    if (s->key) return 0;
    s->key = S + 1; s->par = par; s->x = x; s->good = 0; tlen++; return 1;
}
static void rehash(void) {
    Slot *old = tab; size_t oc = tcap;
    tcap = oc ? 2 * oc : 1 << 16; tab = calloc(tcap, sizeof(Slot)); tlen = 0;
    if (!tab) { fprintf(stderr, "out of memory\n"); exit(3); }
    for (size_t i = 0; i < oc; i++) if (old[i].key) { Slot *s = find(old[i].key - 1); *s = old[i]; tlen++; }
    free(old);
}

/* ---------- expansion ----------
 * Rule 1 (Kobayashi subsumption): add x with nin[x] <= U | N(U).
 * Rule 2 (-g; Coudert et al. Lemma 6, mirrored to in-neighbours): add x in N(U)
 *   with |nin[x] \ (U | N(U))| = 1.
 * Vertices are added one at a time; every prefix produced has boundary size at
 * most |N(U)| at entry.  Returns the number added; their order goes to added[]. */
static int expand(u64 *U, u64 *nb, int *added) {
    int cnt = 0;
    for (;;) {
        int changed = 1;
        while (changed) {
            changed = 0;
            u64 closed = *U | *nb;
            for (u64 m = full & ~*U; m; m &= m - 1) {
                int x = __builtin_ctzll(m);
                if (!(nin[x] & ~closed)) {
                    *U |= 1ULL << x; *nb |= nin[x]; closed = *U | *nb;
                    if (added) added[cnt] = x;
                    cnt++; changed = 1;
                }
            }
        }
        if (!greedy2) return cnt;
        u64 closed = *U | *nb; int hit = -1;
        for (u64 m = *nb & ~*U; m; m &= m - 1) {
            int x = __builtin_ctzll(m);
            if (__builtin_popcountll(nin[x] & ~closed) == 1) { hit = x; break; }
        }
        if (hit < 0) return cnt;
        *U |= 1ULL << hit; *nb |= nin[hit];
        if (added) added[cnt] = hit;
        cnt++;
    }
}

static Vec stack = {0, 0, 0, sizeof(Pair)}, buckets[66];
static long sets, pairs, rescans;
static u64 fullpar; static int fullx = -2;   /* parent link of V */

static void scan(u64 S, u64 nb, int lo, int c) {
    int nxt = n + 1;
    for (u64 m = full & ~S; m; m &= m - 1) {
        int x = __builtin_ctzll(m);
        int w = __builtin_popcountll((nb | nin[x]) & ~(S | (1ULL << x)));
        if (w <= c) { if (w > lo) { Pair p = {S, nb, x}; push(&stack, &p); } }
        else if (w < nxt) nxt = w;
    }
    if (nxt <= n) { Ent e = {S, nb}; push(&buckets[nxt], &e); }
}

static u64 unionnin(u64 U) { u64 r = 0; for (; U; U &= U - 1) r |= nin[__builtin_ctzll(U)]; return r; }

/* ---------- complete mode: backward co-reachability ---------- */
static int cmp_pop_desc(const void *a, const void *b) {
    int pa = __builtin_popcountll(*(const u64 *)a), pb = __builtin_popcountll(*(const u64 *)b);
    return pb - pa;
}
static u64 *dagsets; static size_t ndag;
static void prune(int pw) {
    u64 *all = malloc((tlen ? tlen : 1) * sizeof(u64)); size_t m = 0;
    for (size_t i = 0; i < tcap; i++) if (tab[i].key) all[m++] = tab[i].key - 1;
    qsort(all, m, sizeof(u64), cmp_pop_desc);
    dagsets = malloc((m + 1) * sizeof(u64)); ndag = 0;
    for (size_t i = 0; i < m; i++) {
        u64 S = all[i], nb = unionnin(S); int ok = 0;
        for (u64 mm = full & ~S; mm && !ok; mm &= mm - 1) {
            int x = __builtin_ctzll(mm);
            if (__builtin_popcountll((nb | nin[x]) & ~(S | (1ULL << x))) > pw) continue;
            u64 T = S | (1ULL << x), nbT = nb | nin[x];
            expand(&T, &nbT, NULL);
            if (T == full) ok = 1;
            else { Slot *s = find(T); ok = s->key && s->good; }
        }
        if (ok) { find(S)->good = 1; dagsets[ndag++] = S; }
    }
    free(all);
}

/* DAG file, format KPWDAG3 (doc/dag_format.md): "KPWDAG3\n", int32 n, pw,
 * greedy2, W (= 1 here), uint64 nin[n], uint64 count, uint64 sets[count] (by
 * decreasing size; V not included), then the vertex names.  Arcs are not
 * stored: from S they are the x with |N(S u {x})| <= pw whose expansion is V
 * or a listed set. */
static void dump_dag(const char *fn, int pw) {
    FILE *f = fopen(fn, "wb"); if (!f) { perror(fn); exit(1); }
    int32_t hdr[4] = {n, pw, greedy2, 1}; u64 cnt = ndag;
    fwrite("KPWDAG3\n", 1, 8, f); fwrite(hdr, 4, 4, f);
    fwrite(nin, 8, n, f); fwrite(&cnt, 8, 1, f); fwrite(dagsets, 8, ndag, f);
    el_write_names(f, &el);
    fclose(f);
}

int main(int argc, char **argv) {
    int directed = 0, complete = 0, reverse = 0, quiet = 0; const char *path = NULL, *dagfile = NULL;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-d")) directed = 1;
        else if (!strcmp(argv[i], "-g")) greedy2 = 1;
        else if (!strcmp(argv[i], "-c")) complete = 1;
        else if (!strcmp(argv[i], "-r")) reverse = 1;
        else if (!strcmp(argv[i], "-q")) quiet = 1;
        else if (!strcmp(argv[i], "-o") && i + 1 < argc) dagfile = argv[++i];
        else if (argv[i][0] == '-') { fprintf(stderr, "unknown option %s\n", argv[i]); return 1; }
        else path = argv[i];
    }
    if (dagfile && !complete) { fprintf(stderr, "-o requires -c\n"); return 1; }
    FILE *f = path ? fopen(path, "r") : stdin;
    if (!f) { perror(path); return 1; }
    char err[200];
    if (el_read(f, 64, &el, err, sizeof err)) { fprintf(stderr, "%s (kpw handles n <= 64; use kpw2)\n", err); return 1; }
    if (f != stdin) fclose(f);
    n = el.n;
    for (int k = 0; k < el.m; k++) {
        int u = el.e[k][0], v = el.e[k][1];
        if (u != v) { nin[v] |= 1ULL << u; if (!directed) nin[u] |= 1ULL << v; }
    }
    for (int i = 0; i < 66; i++) buckets[i].sz = sizeof(Ent);
    full = n == 64 ? ~0ULL : (1ULL << n) - 1;
    rehash();

    u64 S0 = 0, nb0 = 0; expand(&S0, &nb0, NULL);
    if (S0 == full) fullx = -1; else insert(S0, ~0ULL, -1);
    sets = 1;
    int c = 0, found = (S0 == full);
    if (!found) scan(S0, nb0, -1, 0);
    while (!found || (complete && stack.len)) {
        while (stack.len) {
            Pair p = ((Pair *)stack.a)[--stack.len]; pairs++;
            u64 T = p.S | (1ULL << p.x);
            if (T != full && find(T)->key) continue;
            u64 nbT = p.nb | nin[p.x];
            expand(&T, &nbT, NULL);
            if (T == full) {
                if (!found) { fullpar = p.S; fullx = p.x; sets++; found = 1; }
                if (!complete) break;
                continue;
            }
            if (!insert(T, p.S, p.x)) continue;
            sets++;
            scan(T, nbT, -1, c);
        }
        if (found) break;
        c++;
        Ent *e = buckets[c].a;
        for (size_t i = 0; i < buckets[c].len; i++) { rescans++; scan(e[i].S, e[i].nb, c - 1, c); }
        free(buckets[c].a); buckets[c].a = NULL; buckets[c].len = buckets[c].cap = 0;
    }
    if (complete) { prune(c); if (dagfile) dump_dag(dagfile, c); }

    /* extract ordering and verify its width */
    int order[64], segbuf[64], nseg = 0, segstart[65], tmp[64], pos = 0;
    u64 S = full;
    while (1) {                                   /* collect segments back to front in tmp */
        Slot tmpslot, *s; int cnt;
        if (S == full) { tmpslot.par = fullpar; tmpslot.x = fullx; s = &tmpslot; }
        else s = find(S);
        segstart[nseg] = pos;
        if (s->x < 0) { u64 U = 0, nb = 0; cnt = expand(&U, &nb, segbuf); memcpy(tmp + pos, segbuf, cnt * sizeof(int)); pos += cnt; nseg++; break; }
        u64 U = s->par | (1ULL << s->x), nb = unionnin(s->par) | nin[s->x];
        cnt = expand(&U, &nb, segbuf);
        tmp[pos++] = s->x; memcpy(tmp + pos, segbuf, cnt * sizeof(int)); pos += cnt; nseg++;
        S = s->par;
    }
    segstart[nseg] = pos;
    int m = 0;
    for (int i = nseg - 1; i >= 0; i--) for (int j = segstart[i]; j < segstart[i + 1]; j++) order[m++] = tmp[j];
    u64 U = 0, nb = 0; int wmax = 0;
    for (int i = 0; i < m; i++) { U |= 1ULL << order[i]; nb |= nin[order[i]]; int w = __builtin_popcountll(nb & ~U); if (w > wmax) wmax = w; }
    if (m != n || wmax != c) { fprintf(stderr, "VERIFY FAILED m=%d wmax=%d c=%d\n", m, wmax, c); return 2; }
    printf("n=%d pw=%d sets=%ld pairs=%ld rescans=%ld", n, c, sets, pairs, rescans);
    if (complete) printf(" dag=%zu", ndag + 1);   /* + V itself */
    printf("\n");
    if (!quiet) {
        printf("order:");
        for (int i = 0; i < m; i++) printf(" %s", el.names[order[reverse ? m - 1 - i : i]]);
        printf("\n");
    }
    return 0;
}
