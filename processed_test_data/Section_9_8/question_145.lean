namespace Chapter9
theorem IsMaxOn.of_monotone_on_compact {a b:ℝ} (h:a < b) {f:ℝ → ℝ} (hf: MonotoneOn f (.Icc a b)) :
  ∃ xmax ∈ Set.Icc a b, IsMaxOn f (.Icc a b) xmax := by sorry
end Chapter9
