namespace Chapter3
theorem SetTheory.Set.pairwise_disjoint (A B:Set) :
    Pairwise (Function.onFun Disjoint ![A \ B, A ∩ B, B \ A]) := by sorry
end Chapter3
