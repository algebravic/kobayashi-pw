# The state table and the memory hierarchy (analysis and plan, before implementation)

## 1. The searches contain exactly this reduction

Every engine (kpw, kpw2, kcw, and the DSL's `dsl_engine.h`) keeps a table of states. Each move offers a pair (k, v):

- **the key** k is the state's key: S for kpw, S ∩ C for kcw;
- **the value** v is what the output mode needs to keep;
- **the operator** ⋆ combines the values offered for the same key.

| output mode | value v | ⋆ |
|---|---|---|
| width + one ordering (default) | (parent, label) | keep the first |
| complete DAG (`kpw -c`) | in-arcs | union |
| secondary costs (Pareto labels) | label set | Pareto merge |
| k-best orderings | top-k list | merge, keep k |

All four operators are associative, and the last three are also commutative. So the search's table is an instance of your reduction problem, and its implementation is your first attempt:
- open addressing on H(k), at load ≤ 1/2;
- 32-bit ids in the slots, with the keys in a dense array beside them;
- a global rehash on doubling.

## 2. How much it costs today (measured, 2-core x86-64 container)

**The table layout alone** (`/tmp/eng_instr/hbench*.c`): half the lookups hit and half miss, over N random keys with the engine's layout.

| W | N | table | lookup | lookup with a 32-bit fingerprint in the slot |
|---|---|---|---|---|
| 1 | 10⁵ | 2 MB | 13.7 ns | — |
| 1 | 4·10⁷ | 0.9 GB | 49.4 ns | 36.4 ns |
| 5 | 10⁵ | 5 MB | 29.9 ns | — |
| 5 | 4·10⁷ | 2.1 GB | 129.3 ns | 71.4 ns |

A lookup costs 3.6–4.3× more once the table leaves the cache. Transparent huge pages are already on in this container, so the large-table numbers are dominated by cache misses, not TLB misses. Batching a group of 16 lookups and prefetching their slots gained only about 10% more.

**In real runs** (instrumented engine, counting every table probe):

| run | states | probes per state | total time | probe cost (estimated) |
|---|---|---|---|---|
| vertex separation gnp_n60_d4_s0 (W = 1) | 3.0 M | 10.2 | 3.8 s | ≈ 1.1 s (≈ 30%) |
| vertex separation sq63 | 0.37 M | 89 | 0.26 s | table in cache |
| cutwidth Grid15x15 (W = 4) | 12.5 M | 3.8 | 52.5 s | ≈ 5 s (≈ 10%) |
| cutwidth Grid12x27 (W = 6) | 3.1 M | 3.2 | 15.4 s | ≈ 1 s (≈ 6%) |
| cutwidth fs_680_1 (W = 11) | 0.56 M | 3.3 | 5.8 s | ≈ 2% |

The estimates multiply the probe count by the microbenchmark latency at the matching table size, so they are approximate.

**Reading the numbers:**
- **Vertex separation** has cheap moves (one popcount for the cost, a short closure). The table is a substantial share of its time, and the share grows with the number of states.
- **Cutwidth** has expensive moves (the Y prefix, the closure worklist, a counter update per added vertex), about 1 µs each. It is compute-bound, and the hierarchy matters little at today's sizes.
- **Your point (1), the empty slots, is minor here.** The slots hold 4-byte ids, while the keys take 8W bytes. But the **global rehash on doubling** is a real cost at large N: it touches every key in random order, and peak memory is 1.5× the table.

## 3. What is different from a pure streaming reduction

**(a) The consumer needs the answer at once.** A depth-first search must know whether a child is new before it can decide to expand it. A streaming reduction never waits for its answer. Deferring the answer is *allowed* here:
- Within a level, the order of expansion is irrelevant to the result. This is `closed_eq_reach` in `lean/KobayashiPw/Engine.lean`: the table at an empty stack is the B-reachable set, whatever the order of expansion.
- But deferral changes the order, and that loses the depth-first search's early exit on the final level. Measured with kpw, exploring the whole final level (`-c`) instead of stopping at V costs:

| graph | states (stop at V) | states (whole final level) | ratio |
|---|---|---|---|
| sq59 | 250 k | 763 k | 3.1× |
| sq61 | 596 k | 1665 k | 2.8× |
| sq63 | 365 k | 1044 k | 2.9× |
| gnp_n60_d3_s0 | 919 k | 2382 k | 2.6× |
| gnp_n60_d4_s0 | 3020 k | 7797 k | 2.6× |
| gnp_n60_d5_s1 | 1194 k | 2799 k | 2.3× |

So a fully deferred scheme (§4, R2) is about 2.3–3.1× more work for the width alone. It costs nothing extra for the modes that must exhaust the final level anyway: the complete DAG, Pareto labels and k-best.

**(b) The key space is graded.** Every move adds at least one vertex, so all arcs go from |S| = k to sizes > k. Partitioning the table by *layer* |S| gives a perfect "duplicate-detection scope" in the sense of Zhou and Hansen:
- When layer k is about to be processed, no further candidates for it can arrive.
- So its candidates can be collected in buffers, deduplicated once (by sort or by a cache-sized partitioned hash), and then expanded.

This is your third attempt, with |S| playing the role of the high bits of H(k). It is also Korf's *delayed duplicate detection*, sorting-based (2004) or hash-based (2008), used for disk-based breadth-first search.

## 4. Plan

### R1: keep the depth-first search, fix the table (small, low risk)

1. **Fingerprints in the slots.** Each slot holds 32-bit id + 32-bit fingerprint in 8 bytes, so a probe of the wrong slot rarely touches `keys[]`. This was measured at 1.4–1.8× on large-table lookups.
2. **Batched probes per expansion, the per-expansion version of your pre-buffer.** `expand` already generates all the children of S together. It would compute all their keys, prefetch their slots, then probe and insert. The order in which children are offered is unchanged, so state counts are unchanged.
3. **A partitioned table, in the style of extendible hashing.** The top b bits of H(k) select a sub-table; each sub-table doubles on its own. This avoids the global random rehash and bounds the extra memory during growth to one partition. It also gives one lock per partition for kpw2-style threading.
4. **Cache and page parameters as data-layer annotations** in the DSL, e.g. `table hash(fingerprint=32, partitions=2^b, prefetch=batch)`, instead of constants. On your Apple-silicon iMac the base page is 16 KB and there is no transparent huge-page support for malloc, so TLB reach is smaller than here. The partition size should be tuned on that machine.

**Expected effect:** about 10–25% on large vertex-separation runs and a few percent on cutwidth, with no change in states, widths or orderings. This is an estimate from the measurements above, to be confirmed by measurement after implementation.

### R2: layered delayed duplicate detection (an alternative engine, `table layered-ddd`)

At level B, process the layers k = 0, 1, …, n in turn:

1. Deduplicate layer k's candidate buffer (append-only runs) by sorting, or by partitioning on high hash bits into cache-sized pieces.
2. Merge the result into layer k's sorted store. Candidates already present are dropped (⋆ keeps the first value); the new ones are the layer's frontier.
3. Expand the frontier, appending each child to the buffer of its layer |T| > k.
4. States that skipped arcs of cost > B go into the bucket of the smallest such cost, as in engine E. At the next level the sweep restarts from the lowest layer that has rescans.

**Properties:**
- **Sequential access.** All accesses are sequential: buffer appends, sorts of runs that fit in cache, and merges.
- **Memory.** The store is sorted runs with no empty slots, and it can spill to disk, since runs are streamed.
- **Parents.** Parent pointers are not stored. They are recovered, as in kpw2 `-x`, by scanning the previous layers for a predecessor at reconstruction time.
- **Parallelism.** Layer partitions are independent: one partition per thread, with no locks.
- **Correctness.** At the end of a sweep the table is closed at B, so `closed_eq_reach` and `width_eq_of_first` apply unchanged. The new proof obligation is only that a sweep in layer order leaves the table closed, which holds because arcs go up in |S|.
- **Cost.** It exhausts the final level, 2.3–3.1× the states for the width alone.

**When it wins:**
- state counts beyond RAM;
- the complete-DAG, Pareto and k-best modes, which exhaust the final level anyway;
- many-core parallel runs.

A **hybrid** is natural: run the depth-first engine with R1 while the table fits in a memory budget, and switch to R2 for the remaining levels when it does not.

### Measurement before and after

The comparison uses:
- the instrumented probe counts above;
- wall time on the gnp_n60, sq, grid and Harwell–Boeing sets;
- runs on your iMac as well as here, since the cache sizes and page size differ.

## 5. Tier 1: implementation notes (written before the code)

**Table layout** (`src/C/dsl_rt.h`; the same scheme in kcw):
- **Hash.** One 64-bit hash h(k). The top `KPW_TABLE_PART_BITS` bits select a partition (default 8, so 256 partitions).
- **Slots.** A slot is a u64 holding `fp << 32 | (id + 1)`, where `fp` is the low 32 bits of h. The probe index within a partition is `fp & mask`.
- **Probing.** A probe compares fingerprints first and reads `keys[id]` only when the fingerprints match.
- **Growth.** Each partition doubles on its own when its load exceeds 1/2. The rehash moves slots by their stored fingerprints, so it never reads keys and touches only that partition's slots.
- **Prefetch.** The prefetch target of a key is `&part[h >> (64-b)].slot[fp & mask]`.

**Order-preserving prefetch** (`KPW_PREFETCH`, default 1). Widths, state counts and orderings must be unchanged.
- **Probe-before-closure** (kpw's probe of S + x before closing it): the moves of an expansion are processed in two passes. Pass 1 filters by cost, hashes S + x and prefetches its slot. Pass 2 probes and applies in the same order. Probes see exactly the same table state as before, because the inserts happen in pass 2 in the original order.
- **Offering children** is pipelined one deep: after child i is built, its slot is prefetched and child i − 1 is offered. The offer order is unchanged.
- **kpw.c** (keys inline in 24-byte slots, so fingerprints do not apply): when a pair is popped, the slot of the next pair on the stack is prefetched. The table is partitioned in the same way, so growth is per partition.

**Parameters.** They are read from `machine.yaml`, in the same flat `KEY: value` format as the hamiltonian repo:
- keys: `KPW_TABLE_PART_BITS`, `KPW_PREFETCH`;
- lookup order: `$KPW_MACHINE_YAML`, then `./machine.yaml`, then the repo root;
- the values become `-D` flags, so they are part of the compile-cache key;
- the hand-written C programs take the same `-D` flags at build time.

## 6. Tier 1: results (2-core x86-64 container; best of 2 runs; old and new run back to back)

In every case below, widths, state counts and orderings are **identical** to the previous version. That was the design requirement, and it was checked for kpw (stats line plus the ordering's md5), kcw (stats line) and the DSL (states).

**DSL engine** (generated code):

| run | old | new | speedup |
|---|---|---|---|
| vertex separation gnp_n60_d4_s0 | 3.83 s | 2.72 s | 1.41× |
| vertex separation gnp_n60_d3_s0 | 1.10 s | 0.88 s | 1.24× |
| vertex separation gnp_n60_d5_s1 | 1.55 s | 1.21 s | 1.28× |
| vertex separation sq63 | 0.26 s | 0.19 s | 1.37× |
| vertex separation `-g` gnp_n60_d4_s0 | 0.73 s | 0.70 s | 1.04× |
| cutwidth Grid12x27 | 16.4 s | 14.3 s | 1.15× |
| cutwidth Grid15x15 | 55.1 s | 43.9 s | 1.25× |
| cutwidth fs_680_1 | 6.06 s | 6.06 s | 1.00× |

**Ablation** (DSL, gnp_n60_d4_s0 / Grid15x15):

| partition bits | prefetch | time (s) |
|---|---|---|
| 8 | on | 2.77 / 46.3 |
| 8 | off | 3.79 / 53.1 |
| 0 | on | 2.87 / 45.1 |
| 0 | off | 3.41 / 49.6 |

The gain comes from the **pipelined prefetch**, together with the fingerprints, which are always on. Partitioning makes no measurable time difference at these sizes. Its purpose is bounded growth: no global rehash, and no 1.5× peak.

**kcw** (hand-written): Grid12x27 18.1 → 15.7 s (1.15×), Grid15x15 67.0 → 57.1 s (1.17×), sq59 4.86 → 4.28 s (1.14×), fs_680_1 6.72 → 6.42 s (1.05×), bcsstk01 1.05×. Peak memory on Grid15x15 *rose*, 623 → 709 MB, because 8-byte fingerprint slots replace 4-byte ids. Fingerprints trade memory for speed; a 16-bit fingerprint in a 6-byte slot would recover most of it.

**kpw** (hand-written): within ±5% of before, on both sides of even, so this is noise. Two variants were tried: prefetching the next pair on the stack, and prefetching at push time (kept). kpw keeps keys inline in 24-byte slots, so a probe is already a single miss, and its time goes to `scan`/`expand` rather than the table. Peak memory fell by 1–7% (1028 → 1016 MB; with `-c`, 1430 → 1337 MB), because the global rehash is gone. With `-c`, the DAG file now lists sets of equal size in increasing order, so it no longer depends on the table layout. Its contents are unchanged.

**Why the DSL engine gains more than kpw.** The engine closes each child as it generates it and offers it at once. Each offer is a dependent random lookup into a table of up to GBs, which is the pattern prefetch helps. kpw defers closure to pop time and probes once per popped pair.

**A bug found by testing the parameter range.** `KPW_TABLE_PART_BITS = 0` made the partition index a shift by 64, which is undefined behaviour; it is now written as `(h >> 1) >> (63 − b)`. The parameter is checked to lie in [0, 16] at compile time, and the initial allocation is 2¹⁶ slots in total (at least 16 per partition). Every setting in {0, 1, 8, 16} passes ASan/UBSan runs and gives identical results.

### Parameters

`machine.example.yaml` documents the keys. Copy it to `machine.yaml` in the working directory or the repository root, or point `$KPW_MACHINE_YAML` at a file.
- **The DSL** reads `KPW_TABLE_PART_BITS` and `KPW_PREFETCH` from the file. Environment variables of the same name override it.
- **The hand-written programs** take the same names as `-D` flags at build time.

There is no tuner yet. The values above are this container's; your Apple-silicon iMac (16 KB pages, a different cache hierarchy) should be measured with the same A/B before changing the defaults.
