/-
Copyright (c) 2024 BICMR@PKU. All rights reserved.
Released under the Apache 2.0 license as described in the file LICENSE.
Authors: Tony Beta Lambda, Kokic, Znssong
-/
import Lean
import Analyzer.Process.Tactic.Simp

open Lean Elab Meta Command Tactic TacticM PrettyPrinter.Delaborator SubExpr
open Std (HashSet HashMap)

namespace Analyzer.Process.Elaboration
open Analyzer.Process.Tactic

@[reducible]
def String.Range.lt (r : String.Range) (r' : String.Range) : Prop :=
  Prod.lexLt (r.start, r.stop) (r'.start, r'.stop)

/-- Collect names of constants used in an elaborated expression. -/
partial def exprConstRefs (e : Expr) : StateM (HashSet UInt64 × HashSet Name) Unit := do
  let k := e.data
  let (seen, acc) ← get
  if seen.contains k then
    return ()
  modify fun (s, a) => (s.insert k, a)
  match e with
  | .bvar _ | .fvar _ | .mvar _ | .sort _ | .lit _ => pure ()
  | .const n _        => modify fun (s, a) => (s, a.insert n)
  | .app f x          => exprConstRefs f; exprConstRefs x
  | .lam _ t b _      => exprConstRefs t; exprConstRefs b
  | .forallE _ t b _  => exprConstRefs t; exprConstRefs b
  | .letE _ t v b _   => exprConstRefs t; exprConstRefs v; exprConstRefs b
  | .mdata _ b        => exprConstRefs b
  | .proj _ _ b       => exprConstRefs b

def collectConstNames (e : Expr) : HashSet Name :=
  (exprConstRefs e |>.run (.empty, .empty)).2.2

def collectTacticInfo (ctx : ContextInfo) (info : Info) (a : Array (ContextInfo × TacticInfo)) : Array (ContextInfo × TacticInfo) :=
  match info with
  | .ofTacticInfo ti => a.push (ctx, ti)
  | _ => a

partial def references : Syntax → HashSet Name
  | .missing => .empty
  | .node _ _ args =>
    args.map references |>.foldl (init := .empty) fun s t => s.fold (fun s a => s.insert a) t
  | .atom _ _ => .empty
  | .ident _ _ name _ => .empty |>.insert name

def getUsedFVarIds (e : Expr) : MetaM (Array FVarId) :=
  e.collectFVars.run default <&> fun s => s.2.fvarIds

def getUsedVariables (e : Expr) : MetaM (Array Name) := do
  return (← getUsedFVarIds e).map FVarId.name

def getDependentsFromGoal (goal : MVarId) : MetaM (Array MVarId × Array FVarId) := do
  let mut visited : HashSet MVarId := {}
  let mut mvars := #[goal]
  let mut dependentMVars := #[]
  let mut dependentFVars := #[]
  while !mvars.isEmpty do
    let mvarId := mvars.back!
    mvars := mvars.pop
    if visited.contains mvarId then continue
    visited := visited.insert mvarId
    match ← getDelayedMVarAssignment? mvarId with
    | none => do
      match ← getExprMVarAssignment? mvarId with
      | none => dependentMVars := dependentMVars.push mvarId
      | some expr => mvars := mvars.append (← getMVars expr)
    | some {fvars, mvarIdPending} => do
      dependentFVars := dependentFVars.append <| fvars.map Expr.fvarId!
      mvars := mvars.push mvarIdPending
  return (dependentMVars, dependentFVars)


def getUsedInfo (mvar : MVarId) : MetaM (Option Json) := do
  let typeUses ← getUsedVariables (← mvar.getType)
  let valueUses ← getUsedVariables <| .mvar mvar
  let typeMVars := (← getMVars (← mvar.getType)).map MVarId.name
  return json%{
    typeUses: $(typeUses),
    typeMVars: $(typeMVars),
    valueUses: $(valueUses)
  }

def setOptions (opts : Lean.Options) : Lean.Options :=
  opts
    |>.set pp.fieldNotation.name false
    |>.set pp.fullNames.name true

def getTacticInfo (ci : ContextInfo) (ti : TacticInfo) : IO TacticElabInfo := do
  let mut extra := Json.null
  try
    let simp ← Simp.getUsedTheorems ci ti
    extra := extra.mergeObj simp
  catch _ => pure ()
  let goalsBefore ← runWithInfoBefore ci ti getUnsolvedGoals
  let dependencies ← runWithInfoAfter ci ti do
    goalsBefore.foldlM
      fun map goal => do
        match ← getExprMVarAssignment? goal with
        | some _ =>
          let (mvars, fvars) ← getDependentsFromGoal goal
          let json := json%{
            newGoals: $(mvars.map MVarId.name),
            newHypotheses: $(fvars.map FVarId.name)
          }
          return map.insert goal json
        | none => return map
      ({} : HashMap MVarId Json)

  let getUsedInfo' (mvar : MVarId) : MetaM (Option Json) := do
    let extra ← getUsedInfo mvar
    return do return .mergeObj (← extra) (← dependencies.get? mvar)

  let before ← TacticM.runWithInfoBefore ci ti <| withOptions setOptions <|
    Goal.fromTactic (extraFun := getUsedInfo')
  let after ← TacticM.runWithInfoAfter ci ti <| withOptions setOptions <|
    Goal.fromTactic (extraFun := getUsedInfo)
  pure {
    references := references ti.stx,
    before,
    after,
    extra? := if extra.isNull then none else extra,
  : TacticElabInfo}

def getSpecialValue : Expr → Option SpecialValue
  | .const name .. => some <| .const name
  | .fvar id .. => some <| .fvar id
  | _ => none

def getTermInfo (ci : ContextInfo) (ti : TermInfo) : IO (Option TermElabInfo) := do
  try
    ti.runMetaM ci <| withOptions setOptions do
      let e      := ti.expr
      let ty     ← inferType e
      let tRefs  := collectConstNames ty
      let vRefs  := collectConstNames e
      pure <| some {
        -- NOTE: TermElabInfo.context is `Array Variable` in your type.
        -- If you don’t yet build a structured context, set it empty for now:
        context       := #[]               -- temporary; see note below
        type          := (← ppExpr ty).pretty
        expectedType  := ← ti.expectedType?.mapM (ppExpr · <&> (·.pretty))
        value         := (← ppExpr e).pretty
        special?      := getSpecialValue e
        typeConstRefs := tRefs.toArray.map (·.toString)
        termConstRefs := vRefs.toArray.map (·.toString)
      }
  catch _ =>
    pure none

@[delab app]
def delabCoeWithType : Delab := whenPPOption getPPCoercions do
  let typeStx ← withType delab
  let e ← getExpr
  let .const declName _ := e.getAppFn | failure
  let some info ← Meta.getCoeFnInfo? declName | failure
  let n := e.getAppNumArgs
  withOverApp info.numArgs do
    match info.type with
    | .coe => `((↑$(← withNaryArg info.coercee delab) : $typeStx))
    | .coeFun =>
      if n = info.numArgs then
        `((⇑$(← withNaryArg info.coercee delab) : $typeStx))
      else
        withNaryArg info.coercee delab
    | .coeSort => `((↥$(← withNaryArg info.coercee delab) : $typeStx))

def skip : Tactic := fun stx =>
  Term.withNarrowedArgTacticReuse (argIdx := 1) evalTactic stx

def onLoad : CommandElabM Unit := do
  enableInfoTree
  -- TODO: add an option to enable/disable handling `focus`-like tactics
  modifyEnv fun env => env |>
  (delabAttribute.ext.addEntry · {
    key := `app,
    declName := ``delabCoeWithType,
    value := delabCoeWithType,
  })

def getResult : CommandElabM (Array ElaborationTree) := do
  let trees := (← getInfoTrees).toArray
  trees.filterMapM fun tree => do
    tree.visitM (postNode := fun ci info _ children => do
      let info' ← match info with
      | .ofTacticInfo ti => .tactic <$> getTacticInfo ci ti
      | .ofTermInfo ti => pure <| .term <$> (← getTermInfo ci ti) |>.getD <| .simple "term"
      | .ofMacroExpansionInfo mi => pure <| .macro { expanded := mi.output }
      | .ofCommandInfo _ => pure <| .simple "command"
      | .ofFieldInfo _ => pure <| .simple "field"
      | .ofOptionInfo _ => pure <| .simple "option"
      | .ofCompletionInfo _ => pure <| .simple "completion"
      | .ofUserWidgetInfo _ => pure <| .simple "uw"
      | .ofCustomInfo _ => pure <| .simple "custom"
      | .ofFVarAliasInfo _ => pure <| .simple "alias"
      | .ofFieldRedeclInfo _ => pure <| .simple "redecl"
      | .ofDelabTermInfo _ => pure <| .simple "delab"
      | .ofChoiceInfo _ => pure <| .simple "choice"
      | .ofPartialTermInfo _ => pure <| .simple "partial"
      | _ => pure <| .simple "unknown"
      pure <| .mk info' info.stx <| children.filterMap id |>.toArray
    )


end Analyzer.Process.Elaboration
