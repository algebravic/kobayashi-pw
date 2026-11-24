import KobayashiPw.MoveSystem

/-!
# The greedy lemma and greedy-closure move systems

`f : Finset V → ℕ` has *diminishing returns* (`DR f`, equivalent to submodularity)
if adding `x` to a larger set gains no more than adding it to a smaller one.  The
step cost is `w S v = f (insert v S)`.

* `greedy_front` : if `f (S + v) ≤ f S`, moving `v` to the front of a completion of
  `S` does not raise its bottleneck beyond `max (f S) (old bottleneck)`.
* `greedy_seq` : a whole sequence of such additions (a closure block) preserves the
  existence of a completion within `B`, and costs at most `f S`.
* `greedySystem_O0/O1/O2` : the move system "choose any `x ∉ S`, then close under a
  rule `P` with `P S v → f (S + v) ≤ f S`" satisfies O0–O2, hence (`value_iff`)
  its least solved bound is the width.  kpw (with or without rule 2) and kcw
  without the cover restriction are instances (`Instances.lean`).
-/

namespace KPW

variable {V : Type*} [DecidableEq V]

/-- Diminishing returns (submodularity), in `ℤ`. -/
def DR (f : Finset V → ℕ) : Prop :=
  ∀ A C x, A ⊆ C → x ∉ C → ((f (insert x C) : ℤ) - f C ≤ (f (insert x A) : ℤ) - f A)

/-- The step cost of a set function: `w S v = f (S ∪ {v})`. -/
def stepOf (f : Finset V → ℕ) : Finset V → V → ℕ := fun S v => f (insert v S)

variable {f : Finset V → ℕ}

theorem greedy_front (hf : DR f) {v : V} :
    ∀ {l : List V} {S : Finset V}, v ∉ S → v ∈ l → f (insert v S) ≤ f S →
      bw (stepOf f) S (v :: l.erase v) ≤ max (f S) (bw (stepOf f) S l) := by
  intro l
  induction l with
  | nil => intro S _ h; simp at h
  | cons u l ih =>
    intro S hvS hvl hv
    by_cases huv : u = v
    · subst huv
      simp
    · have hvl' : v ∈ l := by
        rcases List.mem_cons.1 hvl with h | h
        · exact absurd h.symm huv
        · exact h
      have hvuS : v ∉ insert u S := by
        simp only [Finset.mem_insert, not_or]; exact ⟨fun h => huv h.symm, hvS⟩
      have hv' : f (insert v (insert u S)) ≤ f (insert u S) := by
        have := hf S (insert u S) v (Finset.subset_insert u S) hvuS
        omega
      have ih' := ih hvuS hvl' hv'
      have herase : (u :: l).erase v = u :: l.erase v := by
        simp [List.erase_cons, huv]
      rw [herase]
      simp only [bw_cons, stepOf] at ih' ⊢
      rw [Finset.insert_comm u v S] at *
      omega

/-- A *closure block*: each vertex is new and satisfies the rule at its turn. -/
inductive ValidSeq (P : Finset V → V → Prop) : Finset V → List V → Prop
  | nil (S : Finset V) : ValidSeq P S []
  | cons {S : Finset V} {v : V} {c : List V} :
      v ∉ S → P S v → ValidSeq P (insert v S) c → ValidSeq P S (v :: c)

theorem ValidSeq.spec {P : Finset V → V → Prop} {S : Finset V} {c : List V}
    (h : ValidSeq P S c) : c.Nodup ∧ ∀ v ∈ c, v ∉ S := by
  induction h with
  | nil => simp
  | @cons S v c hv _ _ ih =>
    refine ⟨List.nodup_cons.2 ⟨fun hc => ih.2 v hc (Finset.mem_insert_self v S), ih.1⟩, ?_⟩
    intro u hu
    rcases List.mem_cons.1 hu with rfl | hu
    · exact hv
    · exact fun huS => ih.2 u hu (Finset.mem_insert_of_mem huS)

variable [Fintype V]

theorem IsCompletion.erase {S : Finset V} {l : List V} {v : V} (h : IsCompletion S l)
    (hvS : v ∉ S) : IsCompletion (insert v S) (l.erase v) ∧ v ∈ l := by
  obtain ⟨hn, hd, hc⟩ := h
  refine ⟨⟨hn.erase v, ?_, ?_⟩, hc v hvS⟩
  · intro u hu
    rw [hn.mem_erase_iff] at hu
    simp only [Finset.mem_insert, not_or]
    exact ⟨hu.1, hd u hu.2⟩
  · intro u hu
    simp only [Finset.mem_insert, not_or] at hu
    rw [hn.mem_erase_iff]
    exact ⟨hu.1, hc u hu.2⟩

theorem IsCompletion.tail {S : Finset V} {x : V} {l : List V} (h : IsCompletion S (x :: l)) :
    IsCompletion (insert x S) l := by
  have := (h.erase (h.2.1 x (List.mem_cons_self))).1
  simpa using this

variable (P : Finset V → V → Prop)

/-- The rule never raises `f`. -/
def Greedy (f : Finset V → ℕ) : Prop := ∀ S v, v ∉ S → P S v → f (insert v S) ≤ f S

variable {P}

theorem greedy_seq (hf : DR f) (hP : Greedy P f) {S : Finset V} {c : List V}
    (hc : ValidSeq P S c) {B : ℕ} {l : List V} (hl : IsCompletion S l)
    (hb : bw (stepOf f) S l ≤ B) (hfS : f S ≤ B) :
    bw (stepOf f) S c ≤ f S ∧ f (S ∪ c.toFinset) ≤ f S ∧
      ∃ l', IsCompletion (S ∪ c.toFinset) l' ∧ bw (stepOf f) (S ∪ c.toFinset) l' ≤ B := by
  induction hc generalizing l with
  | nil S => exact ⟨by simp, by simp, l, by simpa using hl, by simpa using hb⟩
  | @cons S v c hvS hPv _ ih =>
    have hv := hP S v hvS hPv
    obtain ⟨hl', hvl⟩ := hl.erase hvS
    have hfront := greedy_front hf hvS hvl hv
    simp only [bw_cons, stepOf] at hfront
    have hb' : bw (stepOf f) (insert v S) (l.erase v) ≤ B := by omega
    obtain ⟨h1, h2, l'', h3, h4⟩ := ih hl' hb' (hv.trans hfS)
    have hset : insert v S ∪ c.toFinset = S ∪ (v :: c).toFinset := by
      rw [List.toFinset_cons, Finset.union_insert, Finset.insert_union]
    rw [hset] at h2 h3 h4
    refine ⟨?_, h2.trans hv, l'', h3, h4⟩
    simp only [bw_cons, stepOf]
    exact max_le hv (h1.trans hv)

/-- `T` is closed: the rule adds nothing more. -/
def Closed (P : Finset V → V → Prop) (T : Finset V) : Prop := ∀ v, v ∉ T → ¬ P T v

/-- Every set has a closure block (the rule is applied until it stops). -/
theorem closure_exists (P : Finset V → V → Prop) (T : Finset V) :
    ∃ c, ValidSeq P T c ∧ Closed P (T ∪ c.toFinset) := by
  classical
  induction h : (Finset.univ \ T).card using Nat.strong_induction_on generalizing T with
  | _ n ih =>
    by_cases hcl : Closed P T
    · exact ⟨[], ValidSeq.nil T, by simpa using hcl⟩
    · simp only [Closed, not_forall, not_not] at hcl
      obtain ⟨v, hvT, hPv⟩ := hcl
      have hlt : (Finset.univ \ insert v T).card < n := by
        rw [← h]
        apply Finset.card_lt_card
        refine ⟨Finset.sdiff_subset_sdiff (Finset.Subset.refl _) (Finset.subset_insert v T), ?_⟩
        intro hsub
        have : v ∈ Finset.univ \ T := by simp [hvT]
        have := hsub this
        simp at this
      obtain ⟨c, hc, hcl⟩ := ih _ hlt (insert v T) rfl
      refine ⟨v :: c, ValidSeq.cons hvT hPv hc, ?_⟩
      rwa [List.toFinset_cons, Finset.union_insert, ← Finset.insert_union]

variable (f P)

/-- The greedy-closure move system: states are prefix sets; an arc chooses any
`x ∉ S` and then applies a closure block, ending at a closed set. -/
def greedySystem (rootBlock : List V) : MoveSystem V (Finset V) where
  set := id
  root := rootBlock.toFinset
  rootBlock := rootBlock
  arc S blk T := ∃ x c, blk = x :: c ∧ x ∉ S ∧ ValidSeq P (insert x S) c ∧
    T = S ∪ blk.toFinset ∧ Closed P T
  cost S blk := bw (stepOf f) S blk

variable {f P}

theorem greedySystem_O0 {r : List V} (hr : ValidSeq P ∅ r) : O0 (greedySystem f P r) :=
  ⟨hr.spec.1, rfl⟩

theorem greedySystem_O1 (r : List V) : O1 (greedySystem f P r) (stepOf f) := by
  rintro S blk T ⟨x, c, rfl, hx, hc, rfl, -⟩
  obtain ⟨hn, hd⟩ := hc.spec
  refine ⟨List.nodup_cons.2 ⟨fun h => hd x h (Finset.mem_insert_self x S), hn⟩, ?_, rfl, rfl⟩
  intro u hu
  rcases List.mem_cons.1 hu with rfl | hu
  · exact hx
  · exact fun huS => hd u hu (Finset.mem_insert_of_mem huS)

/-- Completeness from any closed state with a completion within `B`. -/
theorem greedySystem_reach (hf : DR f) (hP : Greedy P f) (r : List V) (B : ℕ) :
    ∀ (S : Finset V) (l : List V), Closed P S → IsCompletion S l →
      bw (stepOf f) S l ≤ B → f S ≤ B →
      ∃ blks, Path (greedySystem f P r) B S Finset.univ blks := by
  classical
  intro S
  induction h : (Finset.univ \ S).card using Nat.strong_induction_on generalizing S with
  | _ n ih =>
    intro l hcl hl hb hfS
    cases l with
    | nil =>
      have : S = Finset.univ := by
        ext v; simp only [Finset.mem_univ, iff_true]
        by_contra hv; exact List.not_mem_nil (hl.2.2 v hv)
      subst this; exact ⟨[], Path.refl _⟩
    | cons x l =>
      have hxS : x ∉ S := hl.2.1 x List.mem_cons_self
      have hl1 := hl.tail
      simp only [bw_cons, stepOf] at hb
      obtain ⟨c, hc, hclT⟩ := closure_exists P (insert x S)
      obtain ⟨hcb, hcf, l', hl', hb'⟩ :=
        greedy_seq (B := B) hf hP hc hl1 (by omega) (by omega)
      set T := insert x S ∪ c.toFinset with hT
      have hTset : T = S ∪ (x :: c).toFinset := by
        rw [hT, List.toFinset_cons, Finset.union_insert, Finset.insert_union]
      have harc : (greedySystem f P r).arc S (x :: c) T :=
        ⟨x, c, rfl, hxS, hc, hTset, hclT⟩
      have hcost : (greedySystem f P r).cost S (x :: c) ≤ B := by
        show bw (stepOf f) S (x :: c) ≤ B
        simp only [bw_cons, stepOf]
        exact max_le (by omega) (hcb.trans (by omega))
      have hlt : (Finset.univ \ T).card < n := by
        rw [← h]
        apply Finset.card_lt_card
        refine ⟨Finset.sdiff_subset_sdiff (Finset.Subset.refl _) ?_, ?_⟩
        · rw [hTset]; exact Finset.subset_union_left
        · intro hsub
          have hx : x ∈ Finset.univ \ S := by simp [hxS]
          have := hsub hx
          simp [hTset] at this
      obtain ⟨blks, p⟩ := ih _ hlt T rfl l' hclT hl' hb' (hcf.trans (by omega))
      exact ⟨_, Path.cons harc hcost p⟩

/-- **O2 for greedy-closure systems** (with `f ∅ = 0`, true for cut and boundary costs). -/
theorem greedySystem_O2 (hf : DR f) (hP : Greedy P f) (hf0 : f ∅ = 0) {r : List V}
    (hr : ValidSeq P ∅ r) (hrc : Closed P r.toFinset) : O2 (greedySystem f P r) (stepOf f) := by
  intro B ⟨l, hl, hb⟩
  have hl0 : IsCompletion ∅ l := (isCompletion_empty l).2 hl
  obtain ⟨hrb, hrf, l', hl', hb'⟩ := greedy_seq hf hP hr hl0 hb (by omega)
  simp only [Finset.empty_union] at hrf hl' hb'
  refine ⟨show bw (stepOf f) ∅ r ≤ B by omega, ?_⟩
  obtain ⟨blks, p⟩ := greedySystem_reach hf hP r B r.toFinset l' hrc hl' hb' (by omega)
  exact ⟨Finset.univ, blks, p, rfl⟩

/-- **Main theorem for greedy-closure systems.** The least bound solved by the
search (what engine E returns) is the width. -/
theorem greedySystem_value (hf : DR f) (hP : Greedy P f) (hf0 : f ∅ = 0) {r : List V}
    (hr : ValidSeq P ∅ r) (hrc : Closed P r.toFinset) (B : ℕ) :
    Solves (greedySystem f P r) (stepOf f) B ↔ width (stepOf f) ≤ B :=
  value_iff (greedySystem_O0 hr) (greedySystem_O1 r) (greedySystem_O2 hf hP hf0 hr hrc) B

end KPW
