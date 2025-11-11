/- Compatibility helpers for Lean 4.23 -/
import Lean

open System Lean

namespace Analyzer.Compat

def initSrcSearchPath : IO (List System.FilePath) := do
  initSearchPath (← findSysroot)
  return (← searchPathRef.get)

instance : ToJson String.Pos where
  toJson p := toJson p.1

instance : ToJson String.Range where
  toJson r := Json.arr #[toJson r.start, toJson r.stop]

namespace Array

universe u v

def getIdx? {α : Type u} [BEq α] (xs : Array α) (x : α) : Option Nat :=
  xs.findIdx? (· == x)

def concatMapM {m : Type → Type _} [Monad m] {α β : Type}
  (xs : Array α) (f : α → m (Array β)) : m (Array β) :=
  xs.foldlM (init := #[]) (fun acc a => do
    let ys ← f a
    pure (acc ++ ys))

end Array

open Lean Elab Parser System Frontend

def handleHeader (header : HeaderSyntax) (messages : MessageLog) (inputCtx : InputContext)
    (options : Options := {}) : IO Command.State := do
  initSearchPath (← findSysroot)
  let (env, messages) ← processHeader (leakEnv := true) header options messages inputCtx
  return Command.mkState env messages options

def loadFrontend (inputCtx : InputContext)
    (initState : HeaderSyntax → MessageLog → InputContext → IO Command.State := handleHeader)
    : IO (Context × State) := do
  let (header, parserState, messages) ← parseHeader inputCtx
  let commandState ← initState header messages inputCtx
  return ({ inputCtx }, { commandState, parserState, cmdPos := parserState.pos, commands := #[] })

def loadFile (path : FilePath)
    (initState : HeaderSyntax → MessageLog → InputContext → IO Command.State := handleHeader)
    : IO (Context × State) := do
  let input ← IO.FS.readFile path
  let inputCtx := mkInputContext input path.toString
  loadFrontend inputCtx initState

def withFile {α : Type} (path : FilePath) (m : FrontendM α)
    (initState : HeaderSyntax → MessageLog → InputContext → IO Command.State := handleHeader)
    : IO (α × State) := do
  let (context, state) ← loadFile path initState
  m context |>.run state

end Analyzer.Compat

namespace Lean.Elab.Tactic.TacticM

def runWithInfoBefore {α : Type} (ci : ContextInfo) (ti : TacticInfo) (x : TacticM α) : IO α :=
  { ci with mctx := ti.mctxBefore }.runMetaM {} <|
    x { elaborator := .anonymous, recover := false } |>.run' { goals := ti.goalsBefore }
    |>.run'

def runWithInfoAfter {α : Type} (ci : ContextInfo) (ti : TacticInfo) (x : TacticM α) : IO α :=
  { ci with mctx := ti.mctxAfter }.runMetaM {} <|
    x { elaborator := .anonymous, recover := false } |>.run' { goals := ti.goalsAfter }
    |>.run'

def runWithInfo {α : Type} (useAfter : Bool) : ContextInfo → TacticInfo → TacticM α → IO α :=
  if useAfter then runWithInfoAfter else runWithInfoBefore

end Lean.Elab.Tactic.TacticM

-- JSON instances usable across the project (Lean 4.23 compatible)
namespace Analyzer.Compat

open Lean

instance : ToJson (Option String.Range) where
  toJson
  | some r => toJson r
  | none => Json.null

instance : ToJson Syntax where
  toJson x := json% {
    kind: $(x.getKind),
    range: $(x.getRange?)
  }

instance : ToJson (Array Syntax) where
  toJson xs := Json.arr (xs.map toJson)

end Analyzer.Compat
