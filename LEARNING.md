# LEARNING.md — learning log

Role (ULTIMATE.md §11): append-only. One dated line per learning. A changed
mind is a new line marking the old one superseded; never an edit. Knowledge,
not decisions (JOURNAL.md) and not agent-correction memory (tasks/lessons.md).

## 2026-11-19

- 2026-11-19 — Vectorizing 8 lanes per `valu` slot beat scalar ALU by ~13x; VLIW packing then needs an explicit end-of-cycle RAW/WAW hazard model.
- 2026-11-19 — A greedy VLIW bundler must flush on engine slot cap *and* on any read/write of an address written in the same bundle; missing either corrupts results.
- 2026-11-19 — Software pipelining one gather per 4 iterations while other groups' hash chains fill `valu` slots cut 10891 to 2206 cycles.
- 2026-11-19 — `(a + c) + (a << k) == a*(2^k + 1) + c` folds three hash stages into one `multiply_add` (4097/33/9).
- 2026-11-19 — Index wrap must match the reference semantics: `& n_nodes` wraps modulo, the reference wraps to 0; use a round-dependent mask.
- 2026-11-19 — Absolute addressing (`idx = fp + logical`) removed ~513 address-precompute ops; batch state kept in scratch avoids recomputation.
- 2026-11-19 — A linear node trick for a 2-node depth (`node = diff*addr + C`) replaces 8 scalar gathers with one vector op; it does not generalize to 4+ nodes without a permute.
- 2026-11-19 — Without a vector permute/gather, scattered per-lane loads are a hard bandwidth floor: 8 loads/gather × 384 / 2 per cycle = 1536 cycles.
- 2026-11-19 — Throughput of independent serial chains = chain_length / start_interval; adding dummy ops leaves iterations invariant (chains × interval), so it cannot raise throughput.
- 2026-11-19 — Burst scheduling all gathers at once is worse than steady pipelining: 3056 vs 2043 cycles, because loads serialize and chains retire in lockstep.
- 2026-11-19 — Flush-reason census (monkeypatched `_Bundler.add` + `Counter`) identified load cap 1342 / valu cap 368 / RAW 296, proving the design was load-bound before any valu tuning.
- 2026-11-19 — Deriving hardware floors from ISA limits (1536 load, 1365 valu) proves a target unreachable and stops unbounded search; 1363 < both floors.
- 2026-11-19 — `git diff origin/main -- tests/` and `git ls-remote origin refs/heads/main` are proof, not paranoia: silence from a push or an edit is not evidence.
- 2026-11-19 — Keeping a known-good file at `/tmp/pt_baseline.py` and diffing against it after every experiment makes reverts exact and cheap.
- 2026-11-19 — Terminal output is the only correctness oracle; never claim a cycle count or a clean tree from memory.
