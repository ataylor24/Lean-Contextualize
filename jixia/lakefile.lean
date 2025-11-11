import Lake

open Lake DSL

require Cli from git "https://github.com/leanprover/lean4-cli.git" @ s!"v{Lean.versionStringCore}"
-- Removed unused Analysis dep to avoid cross-toolchain conflicts
package jixia where
  leanOptions := #[
    ⟨`autoImplicit, false⟩,
    ⟨`relaxedAutoImplicit, false⟩
  ]

lean_lib Analyzer
@[default_target]
lean_exe jixia where
  root := `Main
  supportInterpreter := true
