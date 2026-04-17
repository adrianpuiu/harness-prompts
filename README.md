Harness loop : 



 Round k of N:
  1. git snapshot round_ref = HEAD           (per-round, enables round-scoped diff)
  2. build CoderState
       instruction + current_files
       + last_feedback + rolling digest
       + rounds_remaining
  3. CODER → <approach> + <patch> (XML)
  4. apply patches (full-file writes, validate before writing)
  5. GATE → run GateSpec.commands (subprocess, pluggable)
       ├── FAIL → feedback = gate_output ──▶ step 7
       └── PASS → step 6
  6. git diff round_ref..HEAD → REVIEWER (JSON findings)
       ├── blocker_count > 0 → feedback = findings ──▶ step 7
       └── CLEAN → return Result(PASS, confidence=derive(...))
  7. DIGEST → rewrite ≤200-word summary (overwrites prior)
  8. k < N ? yes → next round ; no → return Result(MAX_CYCLES)
