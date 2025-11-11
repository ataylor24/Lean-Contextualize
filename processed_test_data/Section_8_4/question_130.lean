namespace Chapter8
theorem axiom_of_choice_from_exists_set_singleton_intersect {I: Type} {X: I → Type} (h : ∀ i, Nonempty (X i)) :
  Nonempty (∀ i, X i) := by
  sorry
end Chapter8
