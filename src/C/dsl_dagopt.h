/* dsl_dagopt.h -- engine E2 (doc/dsl_secondary_design.md §A2, §A7) for DSL-generated ops.
 *
 * Included after dsl_engine.h when the generated ops define DSL_SECONDARY (secondary
 * clauses).  Runs engine E in complete mode, so that the table holds every state of
 * bottleneck <= B*, then minimises a secondary cost over the optimal move graph:
 *
 *   nodes in decreasing |S|, starting at V with the label (cost 0, p 1);
 *   for each arc S -> T (a move of cost <= B*, recomputed by the generated dag_arcs)
 *   and each label (c, p) of T, fold the τ-steps of the arc's block (sec_block):
 *       c += a + p e;  p = max(p e k, 1);
 *   keep the Pareto front of the candidates in (cost, p) -- exact by Theorem E2.1
 *   (e >= 0, e k >= 0); a node with no candidate is not co-reachable and stays empty.
 *
 * Ties are broken by generation order (moves in increasing x, then the target's labels in
 * front order), which is the order of the eager engine, orders.optimize and kopt.
 * A label is 24 bytes; all fronts are kept for the traceback.
 */

typedef struct {
    const double *vals;          /* runtime parameters, packed in Problem.params_decl order */
    long max_labels;             /* <= 0: no limit */
    int which;                   /* index of the secondary clause */
} SecParams;

typedef struct {
    double cost;                 /* the optimum (an upper bound if !exact) */
    double nodes, arcs, labels_total;
    int max_labels, exact;
    double search_seconds;       /* engine E in complete mode; the rest of R->seconds is E2 */
    double dead_nodes, dead_seconds;   /* states of the complete table that are not co-reachable
                                        * (the pruning pass of kpw -c happens here) */
} SecResult;

typedef struct { double cost, p; uint32_t prev; int32_t x; } Lab;               /* x = -1: none */
typedef struct { double cost, p; uint32_t prev; int32_t x; uint32_t seq; } Cand;

typedef struct {
    const Consts *K; const SecParams *SP; int B;
    const u64 *S;
    Lab **pool; size_t *npool, *cappool;
    size_t *loff; uint32_t *lcnt; int8_t *state;    /* state: 0 not processed, 1 processed */
    Cand *cand; size_t nc, capc;
    double (*steps)[3];
    double arcs;
    int oom;
} DagCtx;

static int cand_cmp(const void *A, const void *Bv) {
    const Cand *a = A, *b = Bv;
    if (a->cost != b->cost) return a->cost < b->cost ? -1 : 1;
    if (a->p != b->p) return a->p < b->p ? -1 : 1;
    return a->seq < b->seq ? -1 : (a->seq > b->seq);
}

static void dag_arc_cb(void *vctx, int x, long tid, const int *rec, int nr) {
    DagCtx *C = vctx;
    if (tid < 0 || !C->state[tid] || C->lcnt[tid] == 0) return;   /* target not co-reachable */
    C->arcs++;
    int ns = sec_block(C->SP->which, C->S, rec, nr, C->K, C->SP->vals, C->B, C->steps);
    size_t lo = C->loff[tid]; uint32_t lc = C->lcnt[tid];
    if (C->nc + lc > C->capc) {
        size_t nc = C->capc ? C->capc : 1024;
        while (C->nc + lc > nc) nc *= 2;
        Cand *c = realloc(C->cand, nc * sizeof(Cand));
        if (!c) { C->oom = 1; return; }
        C->cand = c; C->capc = nc;
    }
    const Lab *pool = *C->pool;
    for (uint32_t li = 0; li < lc; li++) {
        double c = pool[lo + li].cost, p = pool[lo + li].p;
        for (int s = 0; s < ns; s++) {
            c += C->steps[s][0] + p * C->steps[s][1];
            double q = p * C->steps[s][1] * C->steps[s][2];
            p = q > 1.0 ? q : 1.0;
        }
        C->cand[C->nc] = (Cand){c, p, (uint32_t)(lo + li), x, (uint32_t)C->nc};
        C->nc++;
    }
}

int dsl_dagopt(const Consts *K, const Params *P, const SecParams *SP, Result *R, SecResult *SR) {
    Eng E; memset(&E, 0, sizeof E);
    E.K = K; E.done = -1; E.complete = 1;
    dsl_stop_flag = 0;
    double t0 = now_s();
    int n = K->n;
    int *rec = malloc((n + 1) * sizeof(int)), nroot = 0;
    int B = 0;
    double expansions = 0;
    memset(SR, 0, sizeof *SR);
    int status = eng_run(&E, P, rec, &nroot, &B, &expansions, t0);
    SR->search_seconds = now_s() - t0;
    Lab *pool = NULL; size_t npool = 0, cappool = 0;
    size_t *loff = NULL; uint32_t *lcnt = NULL, *order = NULL, *sz = NULL; int8_t *state = NULL;
    double (*steps)[3] = NULL;
    DagCtx C; memset(&C, 0, sizeof C);
    if (status != 0) goto out;

    size_t ns = E.ns;
    loff = calloc(ns, sizeof *loff); lcnt = calloc(ns, sizeof *lcnt);
    state = calloc(ns, 1); sz = malloc(ns * sizeof *sz); order = malloc(ns * sizeof *order);
    steps = malloc((size_t)(n + 1) * sizeof *steps);
    cappool = 1 << 16; pool = malloc(cappool * sizeof(Lab));
    if (!loff || !lcnt || !state || !sz || !order || !steps || !pool) { status = 3; goto out; }

    /* nodes in decreasing |S| (counting sort; ties in id order) */
    {
        u64 S[W]; Mt mt; memset(&mt, 0, sizeof mt);
        size_t *cnt = calloc(n + 2, sizeof(size_t));
        if (!cnt) { status = 3; goto out; }
        for (size_t id = 0; id < ns; id++) {
            decode(&E, (uint32_t)id, S, &mt);
            int c = 0; for (int w = 0; w < W; w++) c += __builtin_popcountll(S[w]);
            sz[id] = (uint32_t)c; cnt[n - c]++;
        }
        size_t acc = 0;
        for (int i = 0; i <= n; i++) { size_t t = cnt[i]; cnt[i] = acc; acc += t; }
        for (size_t id = 0; id < ns; id++) order[cnt[n - sz[id]]++] = (uint32_t)id;
        free(cnt);
    }

    C.K = K; C.SP = SP; C.B = B; C.pool = &pool; C.npool = &npool; C.cappool = &cappool;
    C.loff = loff; C.lcnt = lcnt; C.state = state; C.steps = steps;
    /* V: the empty τ-prefix */
    loff[E.done] = 0; lcnt[E.done] = 1; state[E.done] = 1;
    pool[npool++] = (Lab){0.0, 1.0, UINT32_MAX, -1};
    uint32_t biggest = 1; int exact = 1;
    {
        u64 S[W]; Mt mt; memset(&mt, 0, sizeof mt);
        for (size_t oi = 0; oi < ns; oi++) {
            uint32_t id = order[oi];
            if ((long)id == E.done) continue;
            double tn = now_s();
            decode(&E, id, S, &mt);
            C.S = S; C.nc = 0;
            dag_arcs(&E, S, &mt, B, dag_arc_cb, &C);
            if (C.oom) { status = 3; goto out; }
            state[id] = 1;
            loff[id] = npool; lcnt[id] = 0;
            if (C.nc == 0) {                                 /* not co-reachable */
                SR->dead_nodes++; SR->dead_seconds += now_s() - tn;
                continue;
            }
            qsort(C.cand, C.nc, sizeof(Cand), cand_cmp);
            if (npool + C.nc > cappool) {
                while (npool + C.nc > cappool) cappool *= 2;
                Lab *np = realloc(pool, cappool * sizeof(Lab));
                if (!np) { status = 3; goto out; }
                pool = np;
            }
            uint32_t keep = 0; double best_p = INFINITY;
            for (size_t i = 0; i < C.nc; i++) {
                if (C.cand[i].p < best_p) {
                    if (SP->max_labels > 0 && (long)keep >= SP->max_labels) { exact = 0; break; }
                    pool[npool++] = (Lab){C.cand[i].cost, C.cand[i].p, C.cand[i].prev, C.cand[i].x};
                    best_p = C.cand[i].p; keep++;
                }
            }
            lcnt[id] = keep;
            if (keep > biggest) biggest = keep;
            SR->nodes++;
            if (((oi & 1023) == 0) && dsl_stop_flag) { status = 2; goto out; }
        }
    }

    /* root block (τ ends with closure(∅)); the root is id 0 */
    {
        u64 Z[W]; for (int w = 0; w < W; w++) Z[w] = 0;
        int ns0 = nroot ? sec_block(SP->which, Z, rec, nroot, K, SP->vals, B, steps) : 0;
        double best_c = INFINITY; size_t best = SIZE_MAX;
        for (uint32_t li = 0; li < lcnt[0]; li++) {
            size_t L = loff[0] + li;
            double c = pool[L].cost, p = pool[L].p;
            for (int s = 0; s < ns0; s++) {
                c += steps[s][0] + p * steps[s][1];
                double q = p * steps[s][1] * steps[s][2];
                p = q > 1.0 ? q : 1.0;
            }
            if (c < best_c) { best_c = c; best = L; }
        }
        if (best == SIZE_MAX) { status = 6; goto out; }    /* no path: internal error */
        /* σ = root block + blocks along the label chain; τ = reverse(σ) */
        int *sigma = malloc((n + 1) * sizeof(int)), ls = 0;
        int *blk = malloc((64 * W + 1) * sizeof(int));
        for (int k = 0; k < nroot; k++) sigma[ls++] = rec[k];
        u64 S[W]; Mt mt; memset(&mt, 0, sizeof mt);
        decode(&E, 0, S, &mt);
        size_t L = best;
        while (pool[L].x >= 0 && ls <= n) {
            int m = replay(S, &mt, pool[L].x, blk, K);
            for (int k = 0; k < m && ls < n + 1; k++) { sigma[ls++] = blk[k]; S[blk[k] >> 6] |= 1ULL << (blk[k] & 63); }
            mt_init(S, &mt, K);
            L = pool[L].prev;
        }
        if (ls != n) status = 5;
        else for (int i = 0; i < n; i++) R->order[i] = sigma[n - 1 - i];
        free(sigma); free(blk);
        SR->cost = best_c;
    }
    SR->max_labels = (int)biggest; SR->exact = exact;
    SR->labels_total = (double)npool; SR->arcs = C.arcs; SR->nodes += 1;   /* + V */
    R->width = B;
out:
    R->status = status;
    R->lower_bound = B;
    R->states = (double)E.ns;
    R->expansions = expansions;
    R->seconds = now_s() - t0;
    free(rec); free(pool); free(loff); free(lcnt); free(state); free(sz); free(order); free(steps); free(C.cand);
    eng_free(&E);
    return status;
}
