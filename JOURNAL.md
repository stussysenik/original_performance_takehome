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
