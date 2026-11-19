# progress.md — developer's board

Role (ULTIMATE.md §11): mutable `## Active` view + append-only `## Tasks` ledger.
Source of truth for decisions is `JOURNAL.md`. Nothing load-bearing lives in chat.

## Active

- Goal: minimize simulated cycles in `KernelBuilder.build_kernel` (perf_takehome.py).
- Target to beat: 1363 cycles (best-known bar, submission_tests.py:115).
- Baseline: 147734 cycles.
- Current best verified: **2043 cycles** (correctness confirmed on frozen simulator, 2026-11-19).
- Correctness oracle: final `inp_values` must match `reference_kernel2` on (10, 16, 256).
- Hard rules: never edit `tests/`; `git diff origin/main tests/` must be empty.
- Machine limits: alu 12, valu 6, load 2, store 2, flow 1; VLEN 8; SCRATCH 1536.
- n_nodes=2047, n_groups=32 (batch 256 / VLEN 8), rounds=16.
- Current design: SIMD+VLIW software pipeline; one gather/4 iteration cycles;
  17-op hash chain per group per round overlapped across groups. `_Bundler`
  packs dependency-safe slots into cycles.
- Measured slots @2043: load 3286 (floor 1643 cyc), valu 8371 (floor 1395 cyc),
  flow 2, store 64. 2043 actual ≈ load floor + ~400 valu-only bundles.
  Beating 1363 needs load ≤ 2726 AND valu ≤ 8178 — neither holds yet.
- Absolute addressing + D=2 linear node (rounds 1/12) + root broadcast (0/11)
  landed: 2206 → 2043 cycles. idx_v holds fp+logical; gather addr = idx_v[j].
- D=4 via vselect (rounds 2/13) REVERTED: 2180 cycles (worse). Flow engine is
  1/cycle so 3 serial vselects/group + dependency flushes wreck valu packing.
  Load floor dropped to 1391 but valu-only bundles dominated. Selection on flow
  is the wrong tool here; need a load-side reduction that stays valu-friendly.
- 1363 cycles is UNREACHABLE on this ISA — two independent hard floors both
  exceed it. (1) Hash: 16 ops/chain is minimal (1 xor + 12 hash + 3 index);
  512 chains × 16 = 8192 valu ops; 1363×6 = 8178 < 8192. (2) Gather: 384
  gathers × 8 scalar loads / 2 per cycle = 1536 cycles > 1363. Verified no
  vector permute/gather op exists: `vload` loads 8 contiguous words but cannot
  select per-lane, `load_offset` is still 1 word/slot, so 8 loads/gather is a
  hard floor. Practical floor ≈ load 1536 + non-gather valu phases ≈ 1938;
  current 2043 is within ~105 cycles of it.
- Flush diagnosis @2043 (monkeypatched `_Bundler.add`): load cap 1342, valu cap
  368, RAW dep 296, store cap 30. Load-throughput-bound; cycles ≈ scheduler
  iterations. Concurrency = chain_len/gather_interval = 16/4 = 4 valu slots used
  of 6. Adding dummy ops to lengthen chains leaves iterations invariant
  (chains × interval) and adds cost, so it cannot help.
- Burst scheduler experiment (start every idle group's next round immediately):
  3056 cycles (much worse) — 32 gathers launch at once, loads serialize and all
  chains finish in lockstep. REVERTED; the steady one-gather-per-4-iterations
  pipeline is near-optimal.

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
  root broadcast for rounds 0/11 (remove ~510 loads). 2206 → 2043. [done]
- 2026-11-19 — D=2 linear node selection (rounds 1/12): 2043 confirmed. [done]
- 2026-11-19 — D=4 vselect experiment: 2180 (regression), reverted. [done]
- 2026-11-19 — proved 1363 unreachable (load floor 1536, valu floor 8192 ops);
  burst scheduler 3056 (reverted); finalized at verified 2043. [done]
