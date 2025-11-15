namespace Chapter10
theorem lipschitz_bound {M a b:ℝ} (hM: M > 0) (hab: a < b) {f:ℝ → ℝ}
  (hcont: ContinuousOn f (.Icc a b))
  (hderiv: DifferentiableOn ℝ f (.Ioo a b))
  (hlip: ∀ x ∈ Set.Ioo a b, |derivWithin f (.Ioo a b) x| ≤ M)
  {x y:ℝ} (hx: x ∈ Set.Ioo a b) (hy: y ∈ Set.Ioo a b) :
  |f x - f y| ≤ M * |x - y| := by
  sorry
end Chapter10
