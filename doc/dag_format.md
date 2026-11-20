# The DAG file written by `kpw -c -o FILE` and `kpw2 -c -o FILE`

## What the file represents

Let D be the input graph: an undirected edge u–v is a pair of arcs, and a line "u v" with `-d` is the arc u → v. Let pw = vs(D) be the vertex separation number. Write N(U) for the in-neighbours of U that lie outside U.

- **The graph Γ.** Its nodes are V together with every relevant set S (S\* = S) of bottleneck ≤ pw from which V can be reached by arcs of cost ≤ pw.
- **Arcs.** An arc goes S → T, labelled x, whenever x ∉ S, |N(S ∪ {x})| ≤ pw, and the expansion of S ∪ {x} (below) is T, where T is V or another node.
- **Paths and orderings.** Every path from the start node S₀ = expansion(∅) to V is a pw-optimal ordering. Different paths give different orderings. This is Proposition 20 in `doc/pathwidth.tex`.

The file stores **only the node set**. Arcs are recomputed from the rule above, which is why the file is small. `OrderDAG.load` does this.

## Expansion procedure

The procedure must be reproduced exactly; header field `greedy2` says which version was used.

- **Rule 1 (always).** Add a vertex x ∉ U with N⁻(x) ⊆ U ∪ N(U), until none is left. The result is unique, whatever the order.
- **Rule 2 (`greedy2 = 1`; options `-g`, `--greedy2`).** After each rule-1 fixpoint, take the lowest-numbered vertex v ∈ N(U) with exactly one in-neighbour outside U ∪ N(U). If there is one, add it and return to rule 1.

## Orderings from a path

Along the path, output x, then the vertices that the expansion of S ∪ {x} adds, in the order it adds them. Any order in which each vertex satisfies a rule at the moment it is added is valid. The vertices of S₀ come first, in their expansion order.

The result σ is in **kpw's convention**, where the width is max_i |N(σ₁…σᵢ)|. For a left-to-right frontier DP on an undirected graph, use the reverse of σ.

## Binary layout, format 3 (`KPWDAG3`, current)

All integers are little-endian.

| field | size | contents |
|---|---|---|
| magic | 8 bytes | `KPWDAG3\n` |
| n | int32 | number of vertices |
| pw | int32 | vertex separation number |
| greedy2 | int32 | 0 or 1: the expansion rules used |
| W | int32 | 64-bit words per vertex set (1 for kpw; the compile-time W for kpw2) |
| nin | n × W × uint64 | `nin[v]`: the in-neighbour set of vertex v |
| count | uint64 | number of stored sets |
| sets | count × W × uint64 | the nodes of Γ other than V, in decreasing size (order within a size is unspecified) |
| names_bytes | uint64 | length of the names section |
| names | names_bytes bytes | n NUL-terminated strings; the i-th is the input name of vertex i |

**Vertex sets.** A vertex set is W words, and vertex i is bit (i mod 64) of word ⌊i / 64⌋. **V is not stored**: it is the set of all n vertices. S₀ is stored unless S₀ = V.

**Vertex numbering.** Vertex i is the i-th input vertex in the numbering of `src/C/edgelist.h`:
- if every name is an integer (optional `-`, then ASCII digits) and no two names have the same value, the numbering is by increasing value;
- otherwise it is by order of first appearance.

`kobayashi_pw.io.read_edge_list` uses the same rule. `OrderDAG.load` turns the names into labels, as ints when the integer rule applies and as strings otherwise.

## Older formats (still read by `OrderDAG.load`)

- **`KPWDAG1`** (old kpw): the same layout with W = 1. The fourth header field is padding, and there is no names section, so the labels are the bit indices.
- **`KPWDAG2`** (old kpw2): the same layout as format 3 without the names section. The labels are the bit indices.

Both older formats came from programs that required integer labels 0..n−1, and the bit index was the label. A file made from input labelled 1..n therefore also contains the unused vertex 0, isolated.

## Reading a file

Two ways in Python:

```python
from kobayashi_pw.orders import OrderDAG
dag = OrderDAG.load("g.dag")      # arcs recomputed; dag.g.labels holds the names
dag.num_orderings(); dag.sample(k=10)                # frontier-DP (reversed) orderings
```

Or, minimally, by hand:

```python
import struct
with open("g.dag", "rb") as f:
    assert f.read(8) == b"KPWDAG3\n"
    n, pw, greedy2, W = struct.unpack("<4i", f.read(16))
    rd = lambda k: struct.unpack(f"<{k * W}Q", f.read(8 * k * W))
    to_int = lambda ws: sum(w << (64 * j) for j, w in enumerate(ws))
    raw = rd(n); nin = [to_int(raw[i * W:(i + 1) * W]) for i in range(n)]
    (count,) = struct.unpack("<Q", f.read(8))
    raw = rd(count); sets = [to_int(raw[i * W:(i + 1) * W]) for i in range(count)]
    (nb,) = struct.unpack("<Q", f.read(8))
    names = [s.decode() for s in f.read(nb).split(b"\0")[:n]]
```
