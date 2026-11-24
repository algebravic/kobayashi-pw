/* dsl_rt.h -- runtime types and the state table for DSL-generated searches.
 * Included first by generated code (kobayashi_pw.dsl.jit), with W defined:
 *     #define W <words>
 *     #include "dsl_rt.h"
 *     <generated ops: Mt, mt_init, st_add, closure, make_key, expand, replay>
 *     #include "dsl_engine.h"
 */
#include <limits.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef uint64_t u64;

typedef struct {
    int n;
    const u64 *FULLW;            /* W words: the vertex set V */
    const u64 *NB, *NIN, *NOUT;  /* n*W words: N, N_in, N_out rows */
    const int *DEG;              /* n */
    const u64 *const *CS;        /* constant sets, W words each */
    const u64 *const *VF;        /* vertex -> set constants, n*W words each */
} Consts;

typedef struct {
    double time_limit;           /* seconds, <= 0: none */
    double max_states;           /* <= 0: none */
} Params;

typedef struct {
    int status;                  /* 0 solved, 1 limit reached, 2 stopped, 3 out of memory */
    int width, lower_bound;
    double states, expansions, seconds;
    int *order;                  /* n entries, filled when status == 0 */
} Result;

static inline int fdiv(int a, int b) { int q = a / b; if ((a % b != 0) && ((a < 0) != (b < 0))) q--; return q; }

static inline int is_full(const u64 *T, const Consts *K) {
    for (int w = 0; w < W; w++) if (T[w] != K->FULLW[w]) return 0;
    return 1;
}

/* ---- state table: keys (W words), parent id, label x ----
 * Partitioned open addressing (doc/memory_hierarchy.md §5).  The top PART_BITS
 * bits of the 64-bit hash pick a partition; a slot holds fp << 32 | (id + 1)
 * with fp = low 32 bits of the hash; the probe index is fp & mask.  A probe
 * reads keys[id] only on a fingerprint match, and a partition grows on its
 * own by moving slots by their fingerprints (keys are never read). */
#ifndef KPW_TABLE_PART_BITS
#define KPW_TABLE_PART_BITS 8
#endif
#ifndef KPW_PREFETCH
#define KPW_PREFETCH 1
#endif
#if KPW_TABLE_PART_BITS < 0 || KPW_TABLE_PART_BITS > 16
#error "KPW_TABLE_PART_BITS must be in [0, 16]"
#endif
#define NPART (1u << KPW_TABLE_PART_BITS)
#define PART0 ((65536u >> KPW_TABLE_PART_BITS) < 16u ? 16u : (65536u >> KPW_TABLE_PART_BITS))   /* initial slots per partition */

typedef struct { uint32_t id; int lo; } Item;
typedef struct { u64 *slot; uint32_t mask, count; } Part;

#ifndef DSL_CARRY_WORDS
#define DSL_CARRY_WORDS 0
#endif
#define CW (DSL_CARRY_WORDS * W)     /* carried words per state (maintained sets) */

typedef struct {
    const Consts *K;
    u64 *keys; uint32_t *par; int32_t *lab; size_t ns, cap;
    u64 *cm;                          /* CW words per state, when DSL_CARRY_WORDS > 0 */
    Part part[NPART];
    Item *stack; size_t sp, scap;
    Item **bk; size_t *blen, *bcap; int nb;
    int *cx; uint64_t *ch;            /* per-expansion candidate buffers (n entries) */
    long done;                        /* id of V, or -1 */
    int oom;
} Eng;

static inline uint64_t hkey(const u64 *k) {
    uint64_t h = 0x9E3779B97F4A7C15ULL;
    for (int i = 0; i < W; i++) { h ^= k[i]; h *= 0xBF58476D1CE4E5B9ULL; h ^= h >> 31; }
    h ^= h >> 29; h *= 0x94D049BB133111EBULL; h ^= h >> 32;
    return h;
}
#define HPART(h) ((uint32_t)(((h) >> 1) >> (63 - KPW_TABLE_PART_BITS)))   /* top bits; 0 when PART_BITS = 0 (no shift by 64) */
#define HFP(h) ((uint32_t)(h))

static inline void eng_prefetch(Eng *E, uint64_t h) {
#if KPW_PREFETCH
    Part *P = &E->part[HPART(h)];
    __builtin_prefetch(&P->slot[HFP(h) & P->mask]);
#else
    (void)E; (void)h;
#endif
}

static int part_init(Eng *E) {
    for (unsigned p = 0; p < NPART; p++) {
        E->part[p].slot = calloc(PART0, sizeof(u64));
        if (!E->part[p].slot) { E->oom = 1; return 0; }
        E->part[p].mask = PART0 - 1; E->part[p].count = 0;
    }
    return 1;
}

static int part_grow(Eng *E, Part *P) {
    uint32_t nsz = 2 * (P->mask + 1), nm = nsz - 1;
    u64 *ns = calloc(nsz, sizeof(u64));
    if (!ns) { E->oom = 1; return 0; }
    for (uint32_t i = 0; i <= P->mask; i++) {
        u64 v = P->slot[i];
        if (!v) continue;
        uint32_t j = (uint32_t)(v >> 32) & nm;
        while (ns[j]) j = (j + 1) & nm;
        ns[j] = v;
    }
    free(P->slot); P->slot = ns; P->mask = nm;
    return 1;
}

/* id of key, or -1; *slot gets the free slot index on a miss */
static inline long eng_find_h(Eng *E, const u64 *key, uint64_t h, uint32_t *slot) {
    Part *P = &E->part[HPART(h)];
    uint32_t fp = HFP(h), i = fp & P->mask;
    for (;;) {
        u64 v = P->slot[i];
        if (!v) { if (slot) *slot = i; return -1; }
        if ((uint32_t)(v >> 32) == fp) {
            uint32_t id = (uint32_t)v - 1;
            if (!memcmp(E->keys + (size_t)id * W, key, W * sizeof(u64))) return id;
        }
        i = (i + 1) & P->mask;
    }
}

static inline int eng_lookup_h(Eng *E, const u64 *key, uint64_t h) { return eng_find_h(E, key, h, NULL) >= 0; }
static inline int eng_lookup(Eng *E, const u64 *key) { return eng_lookup_h(E, key, hkey(key)); }

static inline void eng_push(Eng *E, uint32_t id, int lo) {
    if (E->sp == E->scap) {
        size_t nc = E->scap ? 2 * E->scap : 4096;
        Item *s = realloc(E->stack, nc * sizeof *s);
        if (!s) { E->oom = 1; return; }
        E->stack = s; E->scap = nc;
    }
    E->stack[E->sp].id = id; E->stack[E->sp].lo = lo; E->sp++;
}

static long eng_insert_h(Eng *E, const u64 *key, uint64_t h, uint32_t parent, int x, const u64 *cm) {
    uint32_t slot;
    if (eng_find_h(E, key, h, &slot) >= 0) return -1;
    if (E->ns == E->cap) {
        size_t nc = E->cap ? 2 * E->cap : 1 << 16;
        u64 *k = realloc(E->keys, nc * W * sizeof(u64));
        uint32_t *p = realloc(E->par, nc * sizeof(uint32_t));
        int32_t *l = realloc(E->lab, nc * sizeof(int32_t));
        if (!k || !p || !l) { E->oom = 1; if (k) E->keys = k; if (p) E->par = p; if (l) E->lab = l; return -1; }
        E->keys = k; E->par = p; E->lab = l; E->cap = nc;
#if DSL_CARRY_WORDS
        u64 *c = realloc(E->cm, nc * CW * sizeof(u64));
        if (!c) { E->oom = 1; return -1; }
        E->cm = c;
#endif
    }
    if (E->ns >= 0xFFFFFFFFu) { E->oom = 1; return -1; }
    uint32_t id = (uint32_t)E->ns++;
    memcpy(E->keys + (size_t)id * W, key, W * sizeof(u64));
    E->par[id] = parent; E->lab[id] = x;
#if DSL_CARRY_WORDS
    memcpy(E->cm + (size_t)id * CW, cm, CW * sizeof(u64));
#else
    (void)cm;
#endif
    Part *P = &E->part[HPART(h)];
    P->slot[slot] = ((u64)HFP(h) << 32) | (u64)(id + 1);
    if (2 * (size_t)++P->count > (size_t)P->mask + 1) part_grow(E, P);
    return id;
}

static long eng_insert(Eng *E, const u64 *key, uint32_t parent, int x, const u64 *cm) {
    return eng_insert_h(E, key, hkey(key), parent, x, cm);
}

/* called by generated expand(): returns 1 when V has been reached */
static inline int eng_offer_h(Eng *E, const u64 *key, uint64_t h, uint32_t parent, int x, int full, const u64 *cm) {
    long id = eng_insert_h(E, key, h, parent, x, cm);
    if (id < 0) return 0;
    if (full) { E->done = id; return 1; }
    eng_push(E, (uint32_t)id, -1);
    return 0;
}

static inline int eng_offer(Eng *E, const u64 *key, uint32_t parent, int x, int full, const u64 *cm) {
    long id = eng_insert(E, key, parent, x, cm);
    if (id < 0) return 0;
    if (full) { E->done = id; return 1; }
    eng_push(E, (uint32_t)id, -1);
    return 0;
}
