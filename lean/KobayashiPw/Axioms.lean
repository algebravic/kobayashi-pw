import KobayashiPw

/-! Axiom audit: each main theorem should depend only on Lean's standard axioms
(`propext`, `Classical.choice`, `Quot.sound`) — no `sorry`, no extra axioms. -/

#print axioms KPW.value_iff
#print axioms KPW.width_eq_of_first
#print axioms KPW.width_ge_of_interrupted
#print axioms KPW.greedy_front
#print axioms KPW.greedySystem_value
#print axioms KPW.kpw_value
#print axioms KPW.kcw_closure_value
