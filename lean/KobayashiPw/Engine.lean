import KobayashiPw.MoveSystem

/-!
# Engine E (`doc/dsl_design.md` §1.2): the invariants behind its correctness

The C engine keeps a table `T` of states.  At level `B` it expands states depth
first; a state that skipped arcs of cost `> B` is bucketed by the smallest such
cost and rescanned when the level reaches it, offering only arcs with cost in
`(lo, B]` (window), where `lo` is the level of its previous scan.

We do not model the C data structures; we prove the facts that the engine's
invariants yield, as stated in Theorem E:

* `closed_eq_reach` : when the stack is empty at level `B`, the table is exactly
  the set of states reachable with bottleneck ≤ `B`;
* `skip_levels` : the jump from `B` to the smallest bucketed cost `b` is safe —
  no state becomes reachable at levels strictly between;
* `width_eq_of_first` : the first level at which `V` appears is the width;
* `width_ge_of_interrupted` : if level `B` was entered (levels `< B` complete
  without `V`), then `width ≥ B` — the certified lower bound `lb=B`;
* `window` : the windowed rescan offers exactly the arcs not offered before;
* `key_table` (O3) : a table keyed by an injective key is a table of states.
-/

namespace KPW

variable {V σ : Type*} [DecidableEq V] {M : MoveSystem V σ}

/-- States reachable from the root with every arc cost ≤ `B`. -/
def Reach (M : MoveSystem V σ) (B : ℕ) (s : σ) : Prop := ∃ blks, Path M B M.root s blks

theorem Path.mono {B C : ℕ} (hBC : B ≤ C) {s t : σ} {blks : List V} (p : Path M B s t blks) :
    Path M C s t blks := by
  induction p with
  | refl s => exact Path.refl s
  | cons ha hc _ ih => exact Path.cons ha (hc.trans hBC) ih

theorem Reach.mono {B C : ℕ} (hBC : B ≤ C) {s : σ} (h : Reach M B s) : Reach M C s :=
  let ⟨blks, p⟩ := h; ⟨blks, p.mono hBC⟩

theorem Path.append {B : ℕ} {s t u : σ} {b₁ b₂ : List V} (p : Path M B s t b₁)
    (q : Path M B t u b₂) : Path M B s u (b₁ ++ b₂) := by
  induction p with
  | refl s => simpa using q
  | cons ha hc _ ih => rw [List.append_assoc]; exact Path.cons ha hc (ih q)

/-- The table is closed at level `B`: every arc of cost ≤ `B` out of a table state
ends in the table.  This is what an empty stack at level `B` guarantees. -/
def ClosedAt (M : MoveSystem V σ) (T : Set σ) (B : ℕ) : Prop :=
  ∀ s ∈ T, ∀ blk t, M.arc s blk t → M.cost s blk ≤ B → t ∈ T

/-- Empty stack at level `B` ⇒ the table is exactly the `B`-reachable set. -/
theorem closed_eq_reach {T : Set σ} {B : ℕ} (hroot : M.root ∈ T) (hsub : ∀ s ∈ T, Reach M B s)
    (hcl : ClosedAt M T B) : T = {s | Reach M B s} := by
  ext s
  refine ⟨hsub s, fun ⟨blks, p⟩ => ?_⟩
  suffices ∀ {a b : σ} {bl : List V}, Path M B a b bl → a ∈ T → b ∈ T from this p hroot
  intro a b bl q
  induction q with
  | refl _ => exact id
  | cons ha hc _ ih => exact fun h => ih (hcl _ h _ _ ha hc)

/-- Jumping from `B` to the smallest pending cost `b` is safe: if no arc out of the
table has cost in `(B, B']`, the table is also closed at `B'`. -/
theorem skip_levels {T : Set σ} {B B' : ℕ} (hcl : ClosedAt M T B)
    (hgap : ∀ s ∈ T, ∀ blk t, M.arc s blk t → ¬ (B < M.cost s blk ∧ M.cost s blk ≤ B')) :
    ClosedAt M T B' := by
  intro s hs blk t ha hc
  by_cases h : M.cost s blk ≤ B
  · exact hcl s hs blk t ha h
  · exact absurd ⟨lt_of_not_ge h, hc⟩ (hgap s hs blk t ha)

/-- Windowed rescan: when `lo ≤ B`, the arcs offered at the previous scan (cost ≤ `lo`)
together with those offered now (`lo < cost ≤ B`) are exactly the arcs of cost ≤ `B`. -/
theorem window {lo B c : ℕ} (h : lo ≤ B) : c ≤ B ↔ c ≤ lo ∨ (lo < c ∧ c ≤ B) := by
  omega

section width
variable [Fintype V] {w : Finset V → V → ℕ}

/-- If the table is closed at `B`, sound, and contains no state with set `V`, then
`B` is below the width (given O0–O2 and that the root block costs ≤ `B`). -/
theorem width_gt_of_closed (h0 : O0 M) (h1 : O1 M w) (h2 : O2 M w) {T : Set σ} {B : ℕ}
    (hroot : M.root ∈ T) (hsub : ∀ s ∈ T, Reach M B s) (hcl : ClosedAt M T B)
    (hno : ∀ s ∈ T, M.set s ≠ Finset.univ) : B < width w := by
  by_contra hB
  obtain ⟨-, t, blks, p, ht⟩ := (value_iff h0 h1 h2 B).2 (not_lt.1 hB)
  have : t ∈ T := by rw [closed_eq_reach hroot hsub hcl]; exact ⟨blks, p⟩
  exact hno t this ht

/-- **Theorem E (value).** If every level below `B` was completed without reaching `V`
(witnessed by closed tables `T b`), and at level `B` a state with set `V` is
reachable (the engine inserted it), then `B` is the width. -/
theorem width_eq_of_first (h0 : O0 M) (h1 : O1 M w) (h2 : O2 M w) {B : ℕ}
    (hrootB : bw w ∅ M.rootBlock ≤ B)
    (T : ℕ → Set σ) (hroot : ∀ b < B, M.root ∈ T b) (hsub : ∀ b < B, ∀ s ∈ T b, Reach M b s)
    (hcl : ∀ b < B, ClosedAt M (T b) b) (hno : ∀ b < B, ∀ s ∈ T b, M.set s ≠ Finset.univ)
    {t : σ} (ht : Reach M B t) (htV : M.set t = Finset.univ) : width w = B := by
  have hle : width w ≤ B := (value_iff h0 h1 h2 B).1 ⟨hrootB, let ⟨b, p⟩ := ht; ⟨t, b, p, htV⟩⟩
  rcases Nat.eq_zero_or_pos B with rfl | hpos
  · omega
  · have := width_gt_of_closed h0 h1 h2 (hroot (B - 1) (by omega)) (hsub (B - 1) (by omega))
      (hcl (B - 1) (by omega)) (hno (B - 1) (by omega))
    omega

/-- **Theorem E (lower bound).** An interrupted run that had completed level `B - 1`
without `V` certifies `width ≥ B` (reported as `lb=B`). -/
theorem width_ge_of_interrupted (h0 : O0 M) (h1 : O1 M w) (h2 : O2 M w) {B : ℕ} (hB : 0 < B)
    {T : Set σ} (hroot : M.root ∈ T) (hsub : ∀ s ∈ T, Reach M (B - 1) s)
    (hcl : ClosedAt M T (B - 1)) (hno : ∀ s ∈ T, M.set s ≠ Finset.univ) : B ≤ width w := by
  have := width_gt_of_closed h0 h1 h2 hroot hsub hcl hno
  omega

end width

/-- **O3.** If `key` is injective on the states that can occur, a table indexed by keys
determines the states: equal keys mean equal states. -/
theorem key_table {K : Type*} (key : σ → K) (N : Set σ) (hinj : Set.InjOn key N)
    {s t : σ} (hs : s ∈ N) (ht : t ∈ N) (h : key s = key t) : s = t :=
  hinj hs ht h

end KPW
