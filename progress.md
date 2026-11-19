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
  19-op hash chain per group per round overlapped across groups. `_Bundler`
  packs dependency-safe slots into cycles.
- Cycle floor reasoning (open): 4096 scalar node loads / 2 per cycle = 2048 hard
  floor for the current load-every-access design. Beating 1363 requires cutting
  loads (cache/group by node) or cutting valu ops (fewer than ~8178 total).

## Tasks

- 2026-11-19 — cloned repo, captured 147734 baseline. [done]
- 2026-11-19 — built `_Bundler` + vectorized SIMD kernel; 10891 cycles correct. [done]
- 2026-11-19 — rewrote as software pipeline; correctness failed. [done]
- 2026-11-19 — root cause: loop issued 516 gathers (4 extra for groups 0-3)
  after work was queued, producing extra hash chains. Fixed by guarding gathers
  with `gather_seq < total_gathers` and draining remaining chains. [done]
- 2026-11-19 — verified 2206 cycles correct on frozen simulator; removed all
  debug instrumentation; tests/ untouched. [done]
- 2026-11-19 — optimize below 1363 cycles. [active]
- 2026-11-19 — investigate load reduction (node grouping / level cache) and
  valu op reduction to break the 2048-cycle load floor. [active]
