import KobayashiPw.Width

/-!
# Move systems and their obligations (`doc/dsl_design.md` §1)

A move system has states, each carrying a prefix set, a root block, and arcs
`s —blk→ t` that add the vertices of `blk` in order, with a cost.  Its value at
a bound `B` is: can `V` be reached from the root with every arc cost ≤ `B`?

* **O0** (root): the root block has no repeats and spells the root's set.
* **O1** (exact arc cost): an arc adds new vertices only, `set t = set s ∪ blk`,
  and its cost is the bottleneck of `blk` placed after `set s`.
* **O2** (completeness): every feasible bound is achieved by some path.

`value_iff` : under O0–O2, a bound is achieved iff it is at least the width.
O3 (keys) and O4 (replay) concern the implementation; see `Engine.lean`.
-/

namespace KPW

variable {V : Type*} [DecidableEq V]

structure MoveSystem (V σ : Type*) [DecidableEq V] where
  set : σ → Finset V
  root : σ
  rootBlock : List V
  arc : σ → List V → σ → Prop
  cost : σ → List V → ℕ

variable {σ : Type*} (M : MoveSystem V σ)

/-- Paths whose every arc costs at most `B`; `blks` is the concatenated blocks. -/
inductive Path (B : ℕ) : σ → σ → List V → Prop
  | refl (s : σ) : Path B s s []
  | cons {s t u : σ} {blk rest : List V} :
      M.arc s blk t → M.cost s blk ≤ B → Path B t u rest → Path B s u (blk ++ rest)

variable (w : Finset V → V → ℕ)

def O0 : Prop := M.rootBlock.Nodup ∧ M.set M.root = M.rootBlock.toFinset

def O1 : Prop :=
  ∀ s blk t, M.arc s blk t →
    blk.Nodup ∧ (∀ v ∈ blk, v ∉ M.set s) ∧ M.set t = M.set s ∪ blk.toFinset ∧
      M.cost s blk = bw w (M.set s) blk

variable [Fintype V]

/-- The bound `B` is achieved: the root block costs ≤ `B` and `V` is reachable. -/
def Solves (B : ℕ) : Prop :=
  bw w ∅ M.rootBlock ≤ B ∧ ∃ t blks, Path M B M.root t blks ∧ M.set t = Finset.univ

def O2 : Prop := ∀ B, Feasible w B → Solves M w B

variable {M w}

theorem Path.spec (h1 : O1 M w) {B : ℕ} {s t : σ} {blks : List V} (p : Path M B s t blks) :
    blks.Nodup ∧ (∀ v ∈ blks, v ∉ M.set s) ∧ M.set t = M.set s ∪ blks.toFinset ∧
      bw w (M.set s) blks ≤ B := by
  induction p with
  | refl s => simp
  | @cons s t u blk rest ha hc _ ih =>
    obtain ⟨hn, hd, hs, hcost⟩ := h1 s blk t ha
    obtain ⟨ihn, ihd, ihs, ihb⟩ := ih
    refine ⟨?_, ?_, ?_, ?_⟩
    · refine List.Nodup.append hn ihn ?_
      intro v hv hv'
      exact ihd v hv' (by rw [hs]; exact Finset.mem_union_right _ (List.mem_toFinset.2 hv))
    · intro v hv
      rcases List.mem_append.1 hv with hv | hv
      · exact hd v hv
      · intro hvs
        exact ihd v hv (by rw [hs]; exact Finset.mem_union_left _ hvs)
    · rw [ihs, hs, List.toFinset_append, Finset.union_assoc]
    · rw [bw_append, ← hs]
      exact max_le (hcost ▸ hc) ihb

/-- Soundness (O0, O1): a solved bound is feasible. -/
theorem Solves.feasible (h0 : O0 M) (h1 : O1 M w) {B : ℕ} (h : Solves M w B) : Feasible w B := by
  obtain ⟨hroot, t, blks, p, ht⟩ := h
  obtain ⟨hn, hd, hs, hb⟩ := p.spec h1
  refine ⟨M.rootBlock ++ blks, ⟨?_, ?_⟩, ?_⟩
  · refine List.Nodup.append h0.1 hn ?_
    intro v hv hv'
    exact hd v hv' (by rw [h0.2]; exact List.mem_toFinset.2 hv)
  · intro v
    have : v ∈ M.set t := by rw [ht]; exact Finset.mem_univ v
    rw [hs, h0.2, Finset.mem_union, List.mem_toFinset, List.mem_toFinset] at this
    exact List.mem_append.2 this
  · rw [bw_append, Finset.empty_union, ← h0.2]
    exact max_le hroot hb

/-- **Value theorem.** Under O0–O2 a bound is achieved iff it is ≥ the width; so the
least achieved bound — what engine E returns — is the width. -/
theorem value_iff (h0 : O0 M) (h1 : O1 M w) (h2 : O2 M w) (B : ℕ) :
    Solves M w B ↔ width w ≤ B :=
  ⟨fun h => width_le (h.feasible h0 h1), fun h => h2 B ((feasible_iff_width_le w B).2 h)⟩

end KPW
