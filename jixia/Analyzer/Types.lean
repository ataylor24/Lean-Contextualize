/-
Copyright (c) 2024 BICMR@PKU. All rights reserved.
Released under the Apache 2.0 license as described in the file LICENSE.
Authors: Tony Beta Lambda, Blueberry
-/
import Lean

/-!
Note on source ranges: we encode all source positions/ranges by byte.
-/

open Lean Elab Term PrettyPrinter
open Std (HashSet)

namespace Analyzer

/-- Pretty-printed syntax bundle used across the analyzer. -/
structure PPSyntax where
  original : Bool
  range    : Option String.Range
  pp?      : Option String

def _root_.Lean.Syntax.isOriginal (stx : Syntax) : Bool :=
  match stx.getHeadInfo? with
  | some (.original ..) => true
  | _ => false

def PPSyntax.pp (category : Name) (stx : Syntax) : CoreM PPSyntax := do
  let pp ← try
    pure <| some (← ppCategory category stx).pretty
  catch _ => pure none
  pure {
    original := stx.isOriginal,
    range := stx.getRange?,
    pp? := pp,
  }

/-- Same as `PPSyntax` but tagging the parser kind. -/
structure PPSyntaxWithKind extends PPSyntax where
  kind : Name

def PPSyntaxWithKind.pp (category : Name) (stx : Syntax) : CoreM PPSyntaxWithKind := do
  pure { ← (PPSyntax.pp category stx) with kind := stx.getKind }

/-- JSON encoder (version 1) for `PPSyntax`. -/
instance : ToJson PPSyntax where
  toJson p :=
    let rangeJson :=
      match p.range with
      | some r => Json.mkObj [("start", toJson r.start.byteIdx), ("stop", toJson r.stop.byteIdx)]
      | none   => Json.null
    Json.mkObj [
      ("original", toJson p.original),
      ("range",    rangeJson),
      ("pp",       toJson p.pp?)
    ]

/-- Ambient declaration/elaboration scope info captured at command sites. -/
structure ScopeInfo where
  varDecls       : Array String
  includeVars    : Array Name
  omitVars       : Array Name
  levelNames     : Array Name
  currNamespace  : Name
  openDecl       : List OpenDecl
  scopedOpenDecl : Array Name

/-- Information about a declaration command in source file. -/
structure BaseDeclarationInfo where
  kind      : String
  ref       : PPSyntax
  /-- Syntax node corresponding to the name of this declaration. -/
  id        : Syntax
  name      : Name
  modifiers : Modifiers
  signature : PPSyntax
  params    : Array BinderView
  type      : Option Syntax
  value     : Option Syntax
  scopeInfo : ScopeInfo

/-- Minimal schema for a structure/record field. -/
structure FieldInfo where
  name       : Name
  type       : PPSyntax
  binderInfo : BinderInfo
  implicit   : Bool

/-- Inductive (and structure/class treated inductively) metadata. -/
structure InductiveInfo extends BaseDeclarationInfo where
  constructors : Array BaseDeclarationInfo
  fields       : Array FieldInfo := #[]

/-- Encode Lean's binder info as a JSON string. -/
instance : ToJson BinderInfo where
  toJson
    | .default        => Json.str "default"
    | .implicit       => Json.str "implicit"
    | .strictImplicit => Json.str "strictImplicit"
    | .instImplicit   => Json.str "instImplicit"

private def nameToJsonArray : Name → Array Json
  | .anonymous   => #[]
  | .str p s     => nameToJsonArray p |>.push (toJson s)
  | .num p n     => nameToJsonArray p |>.push (toJson n)

/-- JSON encoder for our `FieldInfo`. -/
instance : ToJson FieldInfo where
  toJson f := Json.mkObj
    [ ("name",       Json.arr (nameToJsonArray f.name))
    , ("type",       toJson f.type)
    , ("binderInfo", toJson f.binderInfo)
    , ("implicit",   toJson f.implicit)
    ]

inductive DeclarationInfo where
  | ofBase      : BaseDeclarationInfo → DeclarationInfo
  | ofInductive : InductiveInfo       → DeclarationInfo

def DeclarationInfo.toBaseDeclarationInfo : DeclarationInfo → BaseDeclarationInfo
  | .ofBase info      => info
  | .ofInductive info => info.toBaseDeclarationInfo

inductive SymbolKind where
  | «axiom»     : SymbolKind
  | definition  : SymbolKind
  | «theorem»   : SymbolKind
  | «opaque»    : SymbolKind
  | quotient    : SymbolKind
  | «inductive» : SymbolKind
  | constructor : SymbolKind
  | recursor    : SymbolKind

structure SymbolInfo where
  kind           : SymbolKind
  name           : Name
  type           : String
  /-- Names of constants that the type of this symbol references.  Mathematically, this roughly means "notions
  needed to state the theorem". -/
  typeReferences : HashSet Name
  /-- In the same spirit as above, "notions used in the proof of the theorem". `null` if this symbol has no value. -/
  valueReferences : Option (HashSet Name)
  /-- Whether the type of this symbol is a proposition. -/
  isProp         : Bool

structure Variable where
  id         : Name
  name       : Name
  binderInfo? : Option BinderInfo
  type       : String
  value?     : Option String
  isProp     : Bool

structure Goal where
  tag     : Name
  context : Array Variable
  mvarId  : Name
  type    : String
  isProp  : Bool
  extra?  : Option Json := none

structure TacticElabInfo where
  /-- Names referenced in this tactic, including constants and local hypotheses. -/
  references : HashSet Name
  before     : Array Goal
  after      : Array Goal
  extra?     : Option Json := none

inductive SpecialValue where
  | const : Name   → SpecialValue
  | fvar  : FVarId → SpecialValue

structure TermElabInfo where
  context       : Array Variable
  type          : String
  expectedType  : Option String
  value         : String
  special?      : Option SpecialValue
  typeConstRefs : Array String := #[]
  termConstRefs : Array String := #[]

structure MacroInfo where
  expanded : Syntax

inductive ElaborationInfo where
  | term   : TermElabInfo   → ElaborationInfo
  | tactic : TacticElabInfo → ElaborationInfo
  | macro  : MacroInfo      → ElaborationInfo
  | simple : String         → ElaborationInfo

inductive ElaborationTree where
  | mk (info : ElaborationInfo) (ref : Syntax) (children : Array ElaborationTree) : ElaborationTree

structure ModuleInfo where
  imports  : Array Name
  docstring : Array String

structure LineInfo where
  start : String.Pos
  state : Array Goal

end Analyzer
