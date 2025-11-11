namespace Chapter3
theorem SetTheory.Set.recursion (X: Type) (f: nat → X → X) (c:X) :
    ∃! a: nat → X, a 0 = c ∧ ∀ n, a (n + 1:ℕ) = f n (a n) := by sorry
end Chapter3
