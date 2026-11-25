/* dsl_engine.h -- engine E (doc/dsl_design.md §1.2) for DSL-generated ops.
 *
 * Bucketed one-pass bottleneck search: level B rises; every state reachable
 * with bottleneck <= B is expanded depth-first; a state that skipped moves of
 * cost > B goes into the bucket of the smallest such cost, remembering B so
 * that its rescan offers only moves with cost in (B_old, B_new] (window).
 * Theorem E: the first insertion of V happens at B = width; an interrupted
 * run has width >= B.
 */
static volatile int dsl_stop_flag = 0;
void dsl_stop(void) { dsl_stop_flag = 1; }

static double now_s(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + 1e-9 * t.tv_nsec; }

static void decode(Eng *E, uint32_t id, u64 *S, Mt *mt) {
    const Consts *K = E->K;
    memcpy(S, E->keys + (size_t)id * W, W * sizeof(u64));
#if DSL_CARRY_WORDS
    memcpy(MT_CARRY_PTR(mt), E->cm + (size_t)id * CW, CW * sizeof(u64));   /* carried, not recomputed */
#else
    mt_init(S, mt, K);
#endif
#if !KEY_IDENTITY
    u64 cand[W];
    for (int w = 0; w < W; w++) cand[w] = K->FULLW[w] & ~S[w];
    closure(S, mt, K, cand, NULL, 0);
#endif
}

static void bucket_add(Eng *E, int c, uint32_t id, int lo) {
    if (c >= E->nb) {
        int nn = c + 64;
        E->bk = realloc(E->bk, nn * sizeof *E->bk);
        E->blen = realloc(E->blen, nn * sizeof *E->blen);
        E->bcap = realloc(E->bcap, nn * sizeof *E->bcap);
        for (int i = E->nb; i < nn; i++) { E->bk[i] = NULL; E->blen[i] = E->bcap[i] = 0; }
        E->nb = nn;
    }
    if (E->blen[c] == E->bcap[c]) {
        E->bcap[c] = E->bcap[c] ? 2 * E->bcap[c] : 64;
        E->bk[c] = realloc(E->bk[c], E->bcap[c] * sizeof(Item));
        if (!E->bk[c]) { E->oom = 1; return; }
    }
    E->bk[c][E->blen[c]].id = id; E->bk[c][E->blen[c]].lo = lo; E->blen[c]++;
}

/* The search of Theorem E.  On return (status 0) E->done is the id of V and *Bp the width.
 * With E->complete set, level B* is finished: the table then holds every state of
 * bottleneck <= B* (Theorem E.1), as needed for the optimal move graph (dsl_dagopt.h).
 * rec[0..*nroot) receives the root block, closure(∅) in closure order. */
static int eng_run(Eng *E, const Params *P, int *rec, int *nroot, int *Bp, double *expansions, double t0) {
    const Consts *K = E->K;
    if (!part_init(E)) return 3;
    E->cx = malloc((K->n + 1) * sizeof(int)); E->ch = malloc((K->n + 1) * sizeof(uint64_t));
    u64 S[W], key[W], cand[W]; Mt mt;
    memset(&mt, 0, sizeof mt);
    for (int w = 0; w < W; w++) { S[w] = 0; cand[w] = K->FULLW[w]; }
    mt_init(S, &mt, K);
    *nroot = closure(S, &mt, K, cand, rec, 0);    /* root = closure(empty) */
    make_key(S, key, K);
    eng_insert(E, key, UINT32_MAX, -1, MT_CARRY_PTR(&mt));
    int B = 0;
    *Bp = 0;
    if (is_full(S, K)) E->done = 0;
    else eng_push(E, 0, -1);
    for (;;) {
        while (E->sp > 0 && (E->complete || E->done < 0)) {
            Item it = E->stack[--E->sp];
            decode(E, it.id, S, &mt);
            int nx = expand(E, it.id, S, &mt, it.lo, B);
            (*expansions)++;
            if (nx >= 0 && nx != INT_MAX) bucket_add(E, nx, it.id, B);
            if (E->oom) return 3;
            if (((long)*expansions & 1023) == 0) {
                if (dsl_stop_flag) return 2;
                if (P->time_limit > 0 && now_s() - t0 > P->time_limit) return 1;
                if (P->max_states > 0 && (double)E->ns > P->max_states) return 1;
            }
        }
        if (E->done >= 0) break;                       /* complete mode: level B* finished */
        int b = B + 1;
        while (b < E->nb && E->blen[b] == 0) b++;
        if (b >= E->nb) return 4;                       /* V unreachable: a spec error */
        B = b; *Bp = B;
        for (size_t k = E->blen[B]; k-- > 0;) eng_push(E, E->bk[B][k].id, E->bk[B][k].lo);
        free(E->bk[B]); E->bk[B] = NULL; E->blen[B] = E->bcap[B] = 0;
    }
    *Bp = B;
    return 0;
}

static void eng_free(Eng *E) {
    free(E->keys); free(E->par); free(E->lab); free(E->cm); free(E->stack); free(E->cx); free(E->ch);
    for (unsigned p = 0; p < NPART; p++) free(E->part[p].slot);
    for (int i = 0; i < E->nb; i++) free(E->bk[i]);
    free(E->bk); free(E->blen); free(E->bcap);
}

int dsl_solve(const Consts *K, const Params *P, Result *R) {
    Eng E; memset(&E, 0, sizeof E);
    E.K = K; E.done = -1;
    dsl_stop_flag = 0;
    double t0 = now_s();
    int n = K->n;
    int *rec = malloc((n + 1) * sizeof(int)), nroot = 0;
    u64 S[W]; Mt mt;
    memset(&mt, 0, sizeof mt);
    int B = 0;
    double expansions = 0;
    int status = eng_run(&E, P, rec, &nroot, &B, &expansions, t0);
    if (status == 0) {                                  /* reconstruct */
        size_t len = 0; uint32_t *chain = malloc((E.ns + 1) * sizeof(uint32_t));
        for (uint32_t id = (uint32_t)E.done; id != UINT32_MAX; id = E.par[id]) chain[len++] = id;
        int pos = 0;
        for (int k = 0; k < nroot; k++) R->order[pos++] = rec[k];
        for (size_t c = len - 1; c-- > 0;) {
            uint32_t id = chain[c];
            decode(&E, E.par[id], S, &mt);
            int m = replay(S, &mt, E.lab[id], rec, K);
            for (int k = 0; k < m; k++) R->order[pos++] = rec[k];
        }
        free(chain);
        if (pos != n) status = 5;                      /* replay mismatch: an O4 failure */
        R->width = B;
    }
    R->status = status;
    R->lower_bound = B;
    R->states = (double)E.ns;
    R->expansions = expansions;
    R->seconds = now_s() - t0;
    free(rec);
    eng_free(&E);
    return status;
}
