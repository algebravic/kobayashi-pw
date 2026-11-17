/* kpw.c -- bucketed bottleneck search over Kobayashi relevant sets. 
 * n <= 64.  Same algorithm as kobayashi_pw.core.pathwidth (written for timing
 * comparison).  Input: edge list of integer labels 0..n-1 ("u v" per line, a
 * lone token = isolated vertex).  Flag -d: lines are arcs u->v.
 * Build: cc -O3 -march=native -o kpw kpw.c
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint64_t u64;
static int n;
static u64 nin[64], full;

/* ---------- growable arrays ---------- */
typedef struct { u64 S, nb; int x; } Pair;
typedef struct { u64 S, nb; } Ent;
typedef struct { void *a; size_t len, cap, sz; } Vec;
static void push(Vec *v, const void *e) {
    if (v->len == v->cap) { v->cap = v->cap ? 2 * v->cap : 1024; v->a = realloc(v->a, v->cap * v->sz); }
    memcpy((char *)v->a + v->len++ * v->sz, e, v->sz);
}

/* ---------- hash map: set mask -> (parent mask, x) ---------- */
typedef struct { u64 key, par; int x; } Slot;   /* key==0 empty; key = S+1.  S = V is never
                                                   stored (it ends the search), so no overflow. */
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
    s->key = S + 1; s->par = par; s->x = x; tlen++; return 1;
}
static void rehash(void) {
    Slot *old = tab; size_t oc = tcap;
    tcap = oc ? 2 * oc : 1 << 16; tab = calloc(tcap, sizeof(Slot)); tlen = 0;
    for (size_t i = 0; i < oc; i++) if (old[i].key) { Slot *s = find(old[i].key - 1); *s = old[i]; tlen++; }
    free(old);
}

/* ---------- algorithm ---------- */
static int expand(u64 *U, u64 *nb, int *added) {  /* returns #added */
    int cnt = 0, changed = 1;
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
    return cnt;
}

static Vec stack = {0, 0, 0, sizeof(Pair)}, buckets[66];
static long sets, pairs, rescans;
static u64 fullpar; static int fullx = -2;   /* parent link of V, kept outside the table */

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

int main(int argc, char **argv) {
    int directed = 0; const char *path = NULL;
    for (int i = 1; i < argc; i++) { if (!strcmp(argv[i], "-d")) directed = 1; else path = argv[i]; }
    FILE *f = path ? fopen(path, "r") : stdin;
    if (!f) { perror(path); return 1; }
    char line[256];
    while (fgets(line, sizeof line, f)) {
        char *h = strchr(line, '#'); if (h) *h = 0;
        int u, v, k = sscanf(line, "%d %d", &u, &v);
        if (k >= 1 && u + 1 > n) n = u + 1;
        if (k == 2) {
            if (v + 1 > n) n = v + 1;
            if (n > 64) { fprintf(stderr, "n > 64\n"); return 1; }
            if (u != v) { nin[v] |= 1ULL << u; if (!directed) nin[u] |= 1ULL << v; }
        }
    }
    for (int i = 0; i < 66; i++) buckets[i].sz = sizeof(Ent);
    full = n == 64 ? ~0ULL : (1ULL << n) - 1;

    u64 S0 = 0, nb0 = 0; expand(&S0, &nb0, NULL);
    if (S0 == full) fullx = -1; else insert(S0, ~0ULL, -1);
    sets = 1;
    int c = 0, found = (S0 == full);
    if (!found) scan(S0, nb0, -1, 0);
    while (!found) {
        while (stack.len) {
            Pair p = ((Pair *)stack.a)[--stack.len]; pairs++;
            u64 T = p.S | (1ULL << p.x);
            if (find(T)->key) continue;
            u64 nbT = p.nb | nin[p.x];
            expand(&T, &nbT, NULL);
            if (T == full) { fullpar = p.S; fullx = p.x; sets++; found = 1; break; }
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

    /* extract ordering and verify its width */
    int order[64], segbuf[64], nseg = 0, segstart[65], tmp[64], pos = 0;
    u64 S = full;
    while (1) {                                   /* collect segments back to front in tmp */
        Slot tmpslot, *s; int cnt;
        if (S == full && fullx != -2) { tmpslot.par = fullpar; tmpslot.x = fullx; s = &tmpslot; }
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
    printf("n=%d pw=%d sets=%ld pairs=%ld rescans=%ld\norder:", n, c, sets, pairs, rescans);
    for (int i = 0; i < m; i++) printf(" %d", order[i]);
    printf("\n");
    return 0;
}
