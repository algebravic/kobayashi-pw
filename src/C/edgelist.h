/* edgelist.h -- read an edge list with arbitrary vertex names.
 *
 * Format (as networkx's read_edgelist): one edge per line, "u v [data...]",
 * whitespace separated; anything after the first two tokens is ignored (e.g.
 * "{}" or a weight).  A line with a single token declares an isolated vertex.
 * '#' starts a comment.  Names are arbitrary non-blank strings.
 *
 * Vertices are numbered 0..n-1 for processing:
 *   - if every name is an integer (optional '-', then digits) and no two names
 *     have the same value, in increasing numeric order;
 *   - otherwise in order of first appearance.
 * This is the same rule as kobayashi_pw.io.read_edge_list, so the C programs
 * and the Python package number vertices identically.
 */
#ifndef EDGELIST_H
#define EDGELIST_H

#include <stdio.h>
#include <sys/types.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    int n;            /* number of vertices */
    char **names;     /* names[i] = name of vertex i */
    int m;            /* number of edge lines (self-loops included) */
    int (*e)[2];      /* e[k] = {u, v} in vertex numbers */
} EdgeList;

static inline int el_is_int(const char *s) {
    if (*s == '-') s++;
    if (!*s) return 0;
    for (; *s; s++) if (*s < '0' || *s > '9') return 0;
    return 1;
}

static inline int el_intern(EdgeList *el, int *cap, const char *tok, int maxn) {
    for (int i = 0; i < el->n; i++) if (!strcmp(el->names[i], tok)) return i;
    if (el->n >= maxn) return -1;
    if (el->n == *cap) { *cap = *cap ? 2 * *cap : 64; el->names = realloc(el->names, *cap * sizeof(char *)); }
    el->names[el->n] = strdup(tok);
    return el->n++;
}

static inline int el_cmp_val(const void *a, const void *b, void *vals) {
    long long x = ((long long *)vals)[*(const int *)a], y = ((long long *)vals)[*(const int *)b];
    return (x > y) - (x < y);
}
/* portable qsort with context: insertion sort is enough for n <= a few hundred */
static inline void el_sort_idx(int *idx, int n, long long *vals) {
    for (int i = 1; i < n; i++) {
        int t = idx[i], j = i - 1;
        while (j >= 0 && el_cmp_val(&idx[j], &t, vals) > 0) { idx[j + 1] = idx[j]; j--; }
        idx[j + 1] = t;
    }
}

/* Returns 0 on success; on error writes a message to err and returns -1. */
static inline int el_read(FILE *f, int maxn, EdgeList *el, char *err, size_t errlen) {
    memset(el, 0, sizeof *el);
    int ncap = 0, ecap = 0;
    char *line = NULL; size_t lcap = 0; ssize_t len;
    long lineno = 0;
    while ((len = getline(&line, &lcap, f)) >= 0) {
        lineno++;
        char *h = strchr(line, '#'); if (h) *h = 0;
        char *save = NULL;
        char *t1 = strtok_r(line, " \t\r\n\v\f", &save);
        if (!t1) continue;
        char *t2 = strtok_r(NULL, " \t\r\n\v\f", &save);
        int u = el_intern(el, &ncap, t1, maxn), v = -1;
        if (u >= 0 && t2) v = el_intern(el, &ncap, t2, maxn);
        if (u < 0 || (t2 && v < 0)) {
            snprintf(err, errlen, "line %ld: more than %d vertices", lineno, maxn);
            free(line); return -1;
        }
        if (t2) {
            if (el->m == ecap) { ecap = ecap ? 2 * ecap : 256; el->e = realloc(el->e, ecap * sizeof *el->e); }
            el->e[el->m][0] = u; el->e[el->m][1] = v; el->m++;
        }
    }
    free(line);
    /* numeric names: renumber in increasing value */
    int numeric = el->n > 0;
    for (int i = 0; i < el->n && numeric; i++) numeric = el_is_int(el->names[i]);
    if (numeric) {
        long long *val = malloc(el->n * sizeof *val);
        int *idx = malloc(el->n * sizeof *idx), *pos = malloc(el->n * sizeof *pos);
        for (int i = 0; i < el->n; i++) { val[i] = strtoll(el->names[i], NULL, 10); idx[i] = i; }
        el_sort_idx(idx, el->n, val);
        int distinct = 1;
        for (int i = 1; i < el->n; i++) if (val[idx[i]] == val[idx[i - 1]]) distinct = 0;
        if (distinct) {
            char **nm = malloc(el->n * sizeof *nm);
            for (int i = 0; i < el->n; i++) { nm[i] = el->names[idx[i]]; pos[idx[i]] = i; }
            free(el->names); el->names = nm;
            for (int k = 0; k < el->m; k++) { el->e[k][0] = pos[el->e[k][0]]; el->e[k][1] = pos[el->e[k][1]]; }
        }
        free(val); free(idx); free(pos);
    }
    return 0;
}

/* names section of a DAG file: uint64 byte count, then n NUL-terminated names */
static inline void el_write_names(FILE *f, const EdgeList *el) {
    unsigned long long bytes = 0;
    for (int i = 0; i < el->n; i++) bytes += strlen(el->names[i]) + 1;
    fwrite(&bytes, 8, 1, f);
    for (int i = 0; i < el->n; i++) fwrite(el->names[i], 1, strlen(el->names[i]) + 1, f);
}

#endif
