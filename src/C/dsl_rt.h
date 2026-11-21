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

/* ---- state table: keys (W words), parent id, label x ---- */
typedef struct { uint32_t id; int lo; } Item;

#ifndef DSL_CARRY_WORDS
#define DSL_CARRY_WORDS 0
#endif
#define CW (DSL_CARRY_WORDS * W)     /* carried words per state (maintained sets) */

typedef struct {
    const Consts *K;
    u64 *keys; uint32_t *par; int32_t *lab; size_t ns, cap;
    u64 *cm;                          /* CW words per state, when DSL_CARRY_WORDS > 0 */
    uint32_t *ht; size_t hmask;
    Item *stack; size_t sp, scap;
    Item **bk; size_t *blen, *bcap; int nb;
    long done;                   /* id of V, or -1 */
    int oom;
} Eng;

static inline uint64_t hkey(const u64 *k) {
    uint64_t h = 0x9E3779B97F4A7C15ULL;
    for (int i = 0; i < W; i++) { h ^= k[i]; h *= 0xBF58476D1CE4E5B9ULL; h ^= h >> 31; }
    return h;
}

static int eng_rehash(Eng *E, size_t size) {
    uint32_t *nt = calloc(size, sizeof *nt);
    if (!nt) { E->oom = 1; return 0; }
    free(E->ht); E->ht = nt; E->hmask = size - 1;
    for (size_t id = 0; id < E->ns; id++) {
        size_t h = hkey(E->keys + id * W) & E->hmask;
        while (E->ht[h]) h = (h + 1) & E->hmask;
        E->ht[h] = (uint32_t)id + 1;
    }
    return 1;
}

static inline long eng_find(Eng *E, const u64 *key, size_t *slot) {
    size_t h = hkey(key) & E->hmask;
    while (E->ht[h]) {
        uint32_t id = E->ht[h] - 1;
        if (!memcmp(E->keys + (size_t)id * W, key, W * sizeof(u64))) { if (slot) *slot = h; return id; }
        h = (h + 1) & E->hmask;
    }
    if (slot) *slot = h;
    return -1;
}

static inline int eng_lookup(Eng *E, const u64 *key) { return eng_find(E, key, NULL) >= 0; }

static inline void eng_push(Eng *E, uint32_t id, int lo) {
    if (E->sp == E->scap) {
        size_t nc = E->scap ? 2 * E->scap : 4096;
        Item *s = realloc(E->stack, nc * sizeof *s);
        if (!s) { E->oom = 1; return; }
        E->stack = s; E->scap = nc;
    }
    E->stack[E->sp].id = id; E->stack[E->sp].lo = lo; E->sp++;
}

static long eng_insert(Eng *E, const u64 *key, uint32_t parent, int x, const u64 *cm) {   /* new id, or -1 */
    size_t slot;
    if (eng_find(E, key, &slot) >= 0) return -1;
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
    uint32_t id = (uint32_t)E->ns++;
    memcpy(E->keys + (size_t)id * W, key, W * sizeof(u64));
    E->par[id] = parent; E->lab[id] = x;
#if DSL_CARRY_WORDS
    memcpy(E->cm + (size_t)id * CW, cm, CW * sizeof(u64));
#else
    (void)cm;
#endif
    E->ht[slot] = id + 1;
    if (2 * E->ns > E->hmask + 1) eng_rehash(E, 2 * (E->hmask + 1));
    return id;
}

/* called by generated expand(): returns 1 when V has been reached */
static inline int eng_offer(Eng *E, const u64 *key, uint32_t parent, int x, int full, const u64 *cm) {
    long id = eng_insert(E, key, parent, x, cm);
    if (id < 0) return 0;
    if (full) { E->done = id; return 1; }
    eng_push(E, (uint32_t)id, -1);
    return 0;
}
