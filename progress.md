# progress.md — developer's board

Role (ULTIMATE.md §11): mutable `## Active` view + append-only `## Tasks` ledger.
Source of truth for decisions is `JOURNAL.md`. Nothing load-bearing lives in chat.

## Active

- Goal: minimize simulated cycles in `KernelBuilder.build_kernel` (perf_takehome.py).
- Target to beat: 1363 cycles (best-known bar, submission_tests.py:115).
- Baseline: 147734 cycles.
- Current best verified: **2206 cycles** (correctness confirmed on frozen simulator, 2026-11-19).
- Correctness oracle: final `inp_values` must match `reference_kernel2` on (10, 16, 256).
- Hard rules: never edit `tests/`; `git diff origin/main tests/` must be empty.
- Machine limits: alu 12, valu 6, load 2, store 2, flow 1; VLEN 8; SCRATCH 1536.
- n_nodes=2047, n_groups=32 (batch 256 / VLEN 8), rounds=16.
- Current design: SIMD+VLIW software pipeline; one gather/4 iteration cycles;
  17-op hash chain per group per round overlapped across groups. `_Bundler`
  packs dependency-safe slots into cycles.
- Measured slots: load 4306 (floor 2153 cyc), valu 9234 (floor 1539 cyc).
  2206 actual ≈ load floor. Beating 1363 needs load ≤ 2726 AND valu ≤ 8178.
- Cycle floor reasoning (open): 4096 scalar node loads dominate. Need broadcast
  for rounds with few distinct indices (0/11 share idx 0) and removal of the
  513 addr-precompute valu ops via absolute addressing.

## Tasks

- 2026-11-19 — cloned repo, captured 147734 baseline. [done]
- 2026-11-19 — built `_Bundler` + vectorized SIMD kernel; 10891 cycles correct. [done]
- 2026-11-19 — rewrote as software pipeline; correctness failed. [done]
- 2026-11-19 — root cause: loop issued 516 gathers (4 extra for groups 0-3)
  after work was queued, producing extra hash chains. Fixed by guarding gathers
  with `gather_seq < total_gathers` and draining remaining chains. [done]
- 2026-11-19 — verified 2206 cycles correct on frozen simulator; removed all
  debug instrumentation; tests/ untouched. [done]
- 2026-11-19 — collapse index update 6→4 ops; round-dependent wrap mask.
  2206 cycles correct (no cycle gain yet, load-bound). [done]
- 2026-11-19 — optimize below 1363 cycles. [active]
- 2026-11-19 — absolute addressing (remove 513 addr-precompute valu ops) and
  root broadcast for rounds 0/11 (remove ~510 loads). [active]
