namespace Chapter9
theorem mono_of_continuous_inj {a b:ℝ} (h: a < b) {f:ℝ → ℝ}
  (hf: ContinuousOn f (.Icc a b))
  (hinj: Function.Injective (fun x: Set.Icc a b ↦ f x )) :
  StrictMonoOn f (.Icc a b) ∨ StrictAntiOn f (.Icc a b) := by
  sorry
end Chapter9
