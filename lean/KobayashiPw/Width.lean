import Mathlib

/-!
# Set-determined bottleneck layout problems

A *step cost* `w : Finset V → V → ℕ` gives the cost of placing `v` after the
prefix set `S`.  The bottleneck of an ordering is the largest step cost along
it, and the width is the least bottleneck over all orderings of `V`.

Vertex separation (`w S v = f (insert v S)` with `f S = |N⁻(S) \ S|`), cutwidth
(`f S = |E(S, V \ S)|`) and treewidth (`w S v = |Q(S, v)|`) are instances
(`doc/dsl_design.md` §0).
-/

namespace KPW

variable {V : Type*} [DecidableEq V]

/-- Bottleneck of placing the list `l` after the prefix set `S`. -/
def bw (w : Finset V → V → ℕ) : Finset V → List V → ℕ
  | _, [] => 0
  | S, v :: l => max (w S v) (bw w (insert v S) l)

@[simp] theorem bw_nil (w : Finset V → V → ℕ) (S : Finset V) : bw w S [] = 0 := rfl

@[simp] theorem bw_cons (w : Finset V → V → ℕ) (S : Finset V) (v : V) (l : List V) :
    bw w S (v :: l) = max (w S v) (bw w (insert v S) l) := rfl

theorem bw_append (w : Finset V → V → ℕ) (S : Finset V) (l₁ l₂ : List V) :
    bw w S (l₁ ++ l₂) = max (bw w S l₁) (bw w (S ∪ l₁.toFinset) l₂) := by
  induction l₁ generalizing S with
  | nil => simp
  | cons v l ih =>
    simp only [List.cons_append, bw_cons, ih, List.toFinset_cons, Finset.insert_union,
      Finset.union_insert, max_assoc]

/-- `l` is an ordering of `V`: every vertex exactly once. -/
def IsOrder [Fintype V] (l : List V) : Prop := l.Nodup ∧ ∀ v, v ∈ l

/-- `l` completes the prefix set `S`: the vertices outside `S`, each once. -/
def IsCompletion [Fintype V] (S : Finset V) (l : List V) : Prop :=
  l.Nodup ∧ (∀ v ∈ l, v ∉ S) ∧ ∀ v, v ∉ S → v ∈ l

theorem isCompletion_empty [Fintype V] (l : List V) : IsCompletion ∅ l ↔ IsOrder l := by
  simp [IsCompletion, IsOrder]

variable [Fintype V]

/-- The set of bounds achieved by some ordering. -/
def Feasible (w : Finset V → V → ℕ) (B : ℕ) : Prop := ∃ l, IsOrder l ∧ bw w ∅ l ≤ B

theorem feasible_nonempty (w : Finset V → V → ℕ) : ∃ B, Feasible w B :=
  ⟨_, Finset.univ.toList, ⟨Finset.nodup_toList _, by simp⟩, le_rfl⟩

theorem Feasible.mono {w : Finset V → V → ℕ} {B C : ℕ} (h : Feasible w B) (hBC : B ≤ C) :
    Feasible w C := by
  obtain ⟨l, hl, hb⟩ := h
  exact ⟨l, hl, hb.trans hBC⟩

/-- The width: the least bottleneck of an ordering. -/
noncomputable def width (w : Finset V → V → ℕ) : ℕ :=
  @Nat.find (Feasible w) (Classical.decPred _) (feasible_nonempty w)

theorem feasible_width (w : Finset V → V → ℕ) : Feasible w (width w) := by
  classical
  exact Nat.find_spec (feasible_nonempty w)

theorem width_le {w : Finset V → V → ℕ} {B : ℕ} (h : Feasible w B) : width w ≤ B := by
  classical
  exact Nat.find_min' (feasible_nonempty w) h

theorem feasible_iff_width_le (w : Finset V → V → ℕ) (B : ℕ) :
    Feasible w B ↔ width w ≤ B :=
  ⟨width_le, fun h => (feasible_width w).mono h⟩

end KPW
