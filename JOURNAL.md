# JOURNAL.md — decision log

Append-only (ULTIMATE.md §8). Changed mind = new entry marking old superseded.

## 2026-11-19

- Decision: SIMD (VLEN=8) + VLIW design with a `_Bundler` greedy scheduler.
  Why: scalar baseline is 147734 cycles; vectorization packs 8 lanes per valu.
- Decision: collapse HASH_STAGES 1/3/5 to `multiply_add` (multipliers 4097/33/9);
  keep stages 2/4/6 as explicit shift/xor chains. Why: `(a+c)+(a<<k) == a*(1<<k+1)+c`.
- Decision: node gathers must be scalar loads (non-contiguous idx blocks vload).
  Why: simulator has no scratch gather; non-contiguous addresses cannot vload.
- Decision: replace per-group emission (10891 cycles) with a global software
  pipeline: one gather/4 cycles, other groups' hash chains fill valu slots.
  Why: per-group serialization left 5 of 6 valu slots idle.
- Root cause (correctness bug): the `while done < n_groups` loop kept gathering
  after `gather_seq` reached `total_gathers`, so groups 0-3 received a 17th gather
  and ran an extra hash chain. Evidence: DEBUG_GATHERS = [17,17,17,17,16,...],
  total 516 vs expected 512; DEBUG_BAD = [(0,16,12)]. Fix: guard the gather block
  with `if gather_seq < total_gathers` and drain remaining chains until all done.
  Verified: 2206 cycles, correct on frozen simulator.
- Decision: keep tests/ byte-identical; validate with `python tests/submission_tests.py`
  and `git diff origin/main tests/`. Why: README warns LLM test-editing is cheating.
- Decision: collapse index update from 6 to 4 ops (fuse `2*idx+1` into multiply_add,
  parity into +, wrap into mask). Why: fewer valu slots for when load floor breaks.
- Root cause (correctness bug): `& n_nodes` wraps modulo, but reference wraps to 0.
  Evidence: AssertionError on round 1 with mask. Fix: round-dependent mask —
  `all_ones` normally, `zero` at forest_height (round 10). Verified: 2206 cycles correct.
- Decision: instrumented slot counts — load 4306 (floor 2153 cyc), valu 9234 (floor
  1539 cyc), 2206 actual. Why: load-bound; must cut loads AND valu to beat 1363.
- Decision: absolute addressing (idx_v = fp+logical) + root broadcast + D=2 linear
  node selection. Why: removes ~508 loads and 513 addr-precompute valu ops.
  Result: 2206 → 2043 cycles, correct. Slots: load 3286, valu 8371, flow 2.
- Decision: D=4 node selection via 2-level `vselect` on flow engine was tried and
  REVERTED. Why: flow is 1/cycle, so 3 serial vselects/group plus their dependency
  flushes created ~700 extra valu-only bundles; 2180 cycles despite load floor
  dropping to 1391. Lesson: flow-based selection trades load floor for scheduling
  collapse; any load cut must stay valu/load-friendly.
- Analysis: 17-op sequential hash chain × 512 chains / 6 valu = 1451 cyc hard floor;
  1363 is below it. Reaching 1363 needs fewer hash ops per chain, fewer chains,
  or a fundamentally different packing. Load floor 1643 also needs ≥600 loads cut.
