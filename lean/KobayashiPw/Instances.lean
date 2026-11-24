import KobayashiPw.Greedy

/-!
# Instances: vertex separation (kpw) and cutwidth (kcw without the cover rule)

* `vsCost nin S = |N⁻(S) \ S|`, with `N⁻(S) = ⋃_{u ∈ S} nin u`, has diminishing
  returns; Kobayashi's rule 1 and Coudert–Mazauric–Nisse's rule 2 never raise it.
  Hence kpw's search (`-g` or not) returns the vertex separation number
  (`kpw_value`).
* `cutCost G S = Σ_{u ∈ S} |N(u) \ S| = |E(S, V \ S)|` has diminishing returns,
  with increment `|N(x) \ S| − |N(x) ∩ S|`; the rank rule `Δ ≤ 0` never raises it.
  Hence kcw's search *without* the vertex-cover restriction returns the cutwidth
  (`kcw_closure_value`).  The cover normal form and the twin rule are not yet
  formalised.
-/

namespace KPW

variable {V : Type*} [DecidableEq V]

/-! ### Vertex separation -/

section VS
variable (nin : V → Finset V)

/-- `N⁻(S) = ⋃_{u ∈ S} nin u` (kpw's `nb`). -/
def nbr (S : Finset V) : Finset V := S.biUnion nin

/-- The vertex-separation cost `|N⁻(S) \ S|`. -/
def vsCost (S : Finset V) : ℕ := (nbr nin S \ S).card

/-- Kobayashi's rule 1. -/
def rule1 (S : Finset V) (v : V) : Prop := nin v ⊆ S ∪ nbr nin S

/-- Coudert–Mazauric–Nisse's rule 2 (mirrored to in-neighbours). -/
def rule2 (S : Finset V) (v : V) : Prop :=
  v ∈ nbr nin S ∧ (nin v \ (S ∪ nbr nin S)).card = 1

variable {nin}

@[simp] theorem nbr_empty : nbr nin ∅ = ∅ := by simp [nbr]

theorem nbr_insert (v : V) (S : Finset V) : nbr nin (insert v S) = nin v ∪ nbr nin S := by
  simp [nbr, Finset.biUnion_insert]

theorem nbr_mono {A C : Finset V} (h : A ⊆ C) : nbr nin A ⊆ nbr nin C :=
  Finset.biUnion_subset_biUnion_of_subset_left _ h

@[simp] theorem vsCost_empty : vsCost nin ∅ = 0 := by simp [vsCost]

/-- `vsCost S + |S| = |N⁻(S) ∪ S|`. -/
theorem vsCost_add_card (S : Finset V) : vsCost nin S + S.card = (nbr nin S ∪ S).card :=
  Finset.card_sdiff_add_card _ _

/-- The increment of `vsCost` at `x ∉ C`, as an integer. -/
theorem vsCost_incr {C : Finset V} {x : V} (hx : x ∉ C) :
    (vsCost nin (insert x C) : ℤ) - vsCost nin C =
      (((nin x ∪ {x}) \ (nbr nin C ∪ C)).card : ℤ) - 1 := by
  have h1 := vsCost_add_card (nin := nin) (insert x C)
  have h2 := vsCost_add_card (nin := nin) C
  have h3 : (nbr nin (insert x C) ∪ insert x C) = (nin x ∪ {x}) ∪ (nbr nin C ∪ C) := by
    rw [nbr_insert]; ext y; simp only [Finset.mem_union, Finset.mem_insert, Finset.mem_singleton]
    tauto
  have h4 := Finset.card_sdiff_add_card (nin x ∪ {x}) (nbr nin C ∪ C)
  rw [h3] at h1
  rw [Finset.card_insert_of_notMem hx] at h1
  push_cast at h1 h2 h4 ⊢
  omega

theorem vsCost_DR : DR (vsCost nin) := by
  intro A C x hAC hxC
  have hxA : x ∉ A := fun h => hxC (hAC h)
  rw [vsCost_incr hxC, vsCost_incr hxA]
  have : ((nin x ∪ {x}) \ (nbr nin C ∪ C)).card ≤ ((nin x ∪ {x}) \ (nbr nin A ∪ A)).card :=
    Finset.card_le_card (Finset.sdiff_subset_sdiff (Finset.Subset.refl _)
      (Finset.union_subset_union (nbr_mono hAC) hAC))
  omega

theorem vs_greedy : Greedy (fun S v => rule1 nin S v ∨ rule2 nin S v) (vsCost nin) := by
  intro S v hvS hP
  unfold vsCost
  rw [nbr_insert]
  rcases hP with h1 | ⟨hv, h2⟩
  · apply Finset.card_le_card
    intro y hy
    simp only [Finset.mem_sdiff, Finset.mem_union, Finset.mem_insert, not_or] at hy ⊢
    obtain ⟨hy1 | hy1, hne, hyS⟩ := hy
    · have := h1 hy1
      simp only [Finset.mem_union] at this
      exact ⟨this.resolve_left hyS, hyS⟩
    · exact ⟨hy1, hyS⟩
  · have hsub : (nin v ∪ nbr nin S) \ insert v S ⊆
        ((nbr nin S \ S).erase v) ∪ (nin v \ (S ∪ nbr nin S)) := by
      intro y hy
      simp only [Finset.mem_sdiff, Finset.mem_union, Finset.mem_insert, not_or,
        Finset.mem_erase] at hy ⊢
      obtain ⟨hy1, hne, hyS⟩ := hy
      by_cases hyn : y ∈ nbr nin S
      · exact Or.inl ⟨hne, hyn, hyS⟩
      · exact Or.inr ⟨hy1.resolve_right hyn, hyS, hyn⟩
    have hvmem : v ∈ nbr nin S \ S := Finset.mem_sdiff.2 ⟨hv, hvS⟩
    have := (Finset.card_le_card hsub).trans (Finset.card_union_le _ _)
    rw [h2, Finset.card_erase_of_mem hvmem] at this
    have hpos : 0 < (nbr nin S \ S).card := Finset.card_pos.2 ⟨v, hvmem⟩
    omega

theorem vs_greedy1 : Greedy (rule1 nin) (vsCost nin) :=
  fun S v hvS h => vs_greedy S v hvS (Or.inl h)

variable [Fintype V]

/-- **kpw is correct** (rule 1 only, or rules 1 and 2): for any closure block `r` of
`∅`, the bound solved by the search is the vertex separation number. -/
theorem kpw_value (greedy2 : Bool) {r : List V}
    (hr : ValidSeq (fun S v => rule1 nin S v ∨ (greedy2 ∧ rule2 nin S v)) ∅ r)
    (hrc : Closed (fun S v => rule1 nin S v ∨ (greedy2 ∧ rule2 nin S v)) r.toFinset) (B : ℕ) :
    Solves (greedySystem (vsCost nin) (fun S v => rule1 nin S v ∨ (greedy2 ∧ rule2 nin S v)) r)
        (stepOf (vsCost nin)) B ↔ width (stepOf (vsCost nin)) ≤ B := by
  refine greedySystem_value vsCost_DR ?_ vsCost_empty hr hrc B
  intro S v hvS h
  rcases h with h | ⟨-, h⟩
  · exact vs_greedy S v hvS (Or.inl h)
  · exact vs_greedy S v hvS (Or.inr h)

end VS

/-! ### Cutwidth -/

section Cut
variable (G : SimpleGraph V) [DecidableRel G.Adj] [Fintype V]

/-- `|E(S, V \ S)|`, written as a sum over `S`. -/
def cutCost (S : Finset V) : ℕ := ∑ u ∈ S, (G.neighborFinset u \ S).card

/-- The rank rule `deg v − 2 |N(v) ∩ S| ≤ 0`. -/
def rankRule (S : Finset V) (v : V) : Prop :=
  (G.neighborFinset v \ S).card ≤ (G.neighborFinset v ∩ S).card

variable {G}

@[simp] theorem cutCost_empty : cutCost G ∅ = 0 := by simp [cutCost]

theorem card_sdiff_insert_add {A S : Finset V} {x : V} (hx : x ∉ S) :
    (A \ insert x S).card + (if x ∈ A then 1 else 0) = (A \ S).card := by
  rw [Finset.sdiff_insert]
  split_ifs with h
  · exact Finset.card_erase_add_one (Finset.mem_sdiff.2 ⟨h, hx⟩)
  · rw [Finset.erase_eq_of_notMem (fun h' => h (Finset.mem_sdiff.1 h').1)]; simp

/-- Increment of the cut: `cut(S + x) + |N(x) ∩ S| = cut(S) + |N(x) \ S|`. -/
theorem cutCost_insert {S : Finset V} {x : V} (hx : x ∉ S) :
    cutCost G (insert x S) + (G.neighborFinset x ∩ S).card =
      cutCost G S + (G.neighborFinset x \ S).card := by
  unfold cutCost
  rw [Finset.sum_insert hx]
  have hxx : G.neighborFinset x \ insert x S = G.neighborFinset x \ S := by
    ext y
    simp only [Finset.mem_sdiff, Finset.mem_insert, SimpleGraph.mem_neighborFinset, not_or]
    constructor
    · exact fun h => ⟨h.1, h.2.2⟩
    · exact fun h => ⟨h.1, G.ne_of_adj h.1 |>.symm, h.2⟩
  have hterm : ∀ u ∈ S, (G.neighborFinset u \ insert x S).card +
      (if x ∈ G.neighborFinset u then 1 else 0) = (G.neighborFinset u \ S).card :=
    fun u _ => card_sdiff_insert_add hx
  have hsum := Finset.sum_congr rfl hterm
  rw [Finset.sum_add_distrib] at hsum
  have hcount : (∑ u ∈ S, if x ∈ G.neighborFinset u then 1 else 0) =
      (G.neighborFinset x ∩ S).card := by
    rw [Finset.sum_boole, Nat.cast_id]
    congr 1
    ext u
    simp only [Finset.mem_filter, Finset.mem_inter, SimpleGraph.mem_neighborFinset]
    exact ⟨fun h => ⟨h.2.symm, h.1⟩, fun h => ⟨h.2, h.1.symm⟩⟩
  rw [hcount] at hsum
  rw [hxx]
  omega

theorem cutCost_DR : DR (cutCost G) := by
  intro A C x hAC hxC
  have hxA : x ∉ A := fun h => hxC (hAC h)
  have e1 := cutCost_insert (G := G) hxC
  have e2 := cutCost_insert (G := G) hxA
  have m1 : (G.neighborFinset x \ C).card ≤ (G.neighborFinset x \ A).card :=
    Finset.card_le_card (Finset.sdiff_subset_sdiff (Finset.Subset.refl _) hAC)
  have m2 : (G.neighborFinset x ∩ A).card ≤ (G.neighborFinset x ∩ C).card :=
    Finset.card_le_card (Finset.inter_subset_inter (Finset.Subset.refl _) hAC)
  push_cast
  omega

theorem cut_greedy : Greedy (rankRule G) (cutCost G) := by
  intro S v hvS h
  have := cutCost_insert (G := G) hvS
  unfold rankRule at h
  omega

/-- **kcw without the cover restriction is correct**: the bound solved by the search
with the rank closure is the cutwidth. -/
theorem kcw_closure_value {r : List V} (hr : ValidSeq (rankRule G) ∅ r)
    (hrc : Closed (rankRule G) r.toFinset) (B : ℕ) :
    Solves (greedySystem (cutCost G) (rankRule G) r) (stepOf (cutCost G)) B ↔
      width (stepOf (cutCost G)) ≤ B :=
  greedySystem_value cutCost_DR cut_greedy cutCost_empty hr hrc B

end Cut

end KPW
