/-
A minimal test for Analyzer.Process.Declaration.collectStructFields.
Covers:
  • struct named field
  • struct simple binder (`x : Ty`)
  • struct instance binder (`[instName : Ty]`)
  • class with fields + instance binder
  • inductive + constructor
-/

import Std

namespace StructTest

/-- Simple class for instance-binder tests. -/
class P (α : Type u) : Prop where
  ok : True

/-- Structure with:
  • named field `f : Nat := 0`
  • simple binder field `x : List α`
  • instance binder field `[instP : P α]`  (note the colon)
-/
structure S (α : Type u) where
  /-- Named field with default value. -/
  f : Nat := 0
  /-- Simple binder form. -/
  x : List α
  /-- Instance binder form: MUST be `[name : Type]`. -/
  [instP : P α]

/-- Class variant to exercise `class` field parsing, including an instance binder. -/
class C (α : Type u) where
  g : α → Bool
  [instDec : DecidableEq α]

/-- Inductive with a single constructor, for constructor collection. -/
inductive T where
  | mk : Nat → T

open T in
def demo : T := .mk 3

/-- Another structure to check multiple declarations & instance binder. -/
structure S2 where
  y : Nat
  [instDecNat : DecidableEq Nat]

end StructTest
