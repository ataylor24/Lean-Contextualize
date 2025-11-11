namespace Chapter9
theorem Convergesto.squeeze {E:Set ℝ} {f g h: ℝ → ℝ} {L:ℝ} {x₀:ℝ} (had: AdherentPt x₀ E)
  (hfg: ∀ x ∈ E, f x ≤ g x) (hgh: ∀ x ∈ E, g x ≤ h x)
  (hf: Convergesto E f L x₀) (hh: Convergesto E h L x₀) :
  Convergesto E g L x₀ := by
    sorry
end Chapter9
