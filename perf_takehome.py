"""
# Anthropic's Original Performance Engineering Take-home (Release version)

Copyright Anthropic PBC 2026. Permission is granted to modify and use, but not
to publish or redistribute your solutions so it's hard to find spoilers.

# Task

- Optimize the kernel (in KernelBuilder.build_kernel) as much as possible in the
  available time, as measured by test_kernel_cycles on a frozen separate copy
  of the simulator.

Validate your results using `python tests/submission_tests.py` without modifying
anything in the tests/ folder.

We recommend you look through problem.py next.
"""

from collections import defaultdict
import random
import unittest

from problem import (
    Engine,
    DebugInfo,
    cdiv,
    SLOT_LIMITS,
    VLEN,
    N_CORES,
    SCRATCH_SIZE,
    Machine,
    Tree,
    Input,
    HASH_STAGES,
    reference_kernel,
    build_mem_image,
    reference_kernel2,
)


class _Bundler:
    """Greedy VLIW scheduler: packs dependency-safe slots into cycle bundles.

    Scratch writes land only at the end of a cycle, so a slot that reads an
    address written earlier in the same bundle must wait for the next bundle.
    """

    def __init__(self, limits):
        self.limits = limits
        self.bundles = []
        self.cur = {}
        self.cur_writes = set()
        self.count = {}

    def add(self, engine, slot, reads=(), writes=()):
        if any(a in self.cur_writes for a in reads) or any(
            a in self.cur_writes for a in writes
        ):
            self.flush()
        if self.count.get(engine, 0) >= self.limits[engine]:
            self.flush()
        self.cur.setdefault(engine, []).append(slot)
        self.count[engine] = self.count.get(engine, 0) + 1
        self.cur_writes.update(writes)

    def flush(self):
        if self.cur:
            self.bundles.append(self.cur)
        self.cur = {}
        self.cur_writes = set()
        self.count = {}

    def result(self):
        self.flush()
        return self.bundles


class KernelBuilder:
    def __init__(self):
        self.instrs = []
        self.scratch = {}
        self.scratch_debug = {}
        self.scratch_ptr = 0
        self.const_map = {}

    def debug_info(self):
        return DebugInfo(scratch_map=self.scratch_debug)

    def build(self, slots: list[tuple[Engine, tuple]], vliw: bool = False):
        # Simple slot packing that just uses one slot per instruction bundle
        instrs = []
        for engine, slot in slots:
            instrs.append({engine: [slot]})
        return instrs

    def add(self, engine, slot):
        self.instrs.append({engine: [slot]})

    def alloc_scratch(self, name=None, length=1):
        addr = self.scratch_ptr
        if name is not None:
            self.scratch[name] = addr
            self.scratch_debug[addr] = (name, length)
        self.scratch_ptr += length
        assert self.scratch_ptr <= SCRATCH_SIZE, "Out of scratch space"
        return addr

    def scratch_const(self, val, name=None):
        if val not in self.const_map:
            addr = self.alloc_scratch(name)
            self.add("load", ("const", addr, val))
            self.const_map[val] = addr
        return self.const_map[val]

    def build_hash(self, val_hash_addr, tmp1, tmp2, round, i):
        slots = []

        for hi, (op1, val1, op2, op3, val3) in enumerate(HASH_STAGES):
            slots.append(("alu", (op1, tmp1, val_hash_addr, self.scratch_const(val1))))
            slots.append(("alu", (op3, tmp2, val_hash_addr, self.scratch_const(val3))))
            slots.append(("alu", (op2, val_hash_addr, tmp1, tmp2)))
            slots.append(("debug", ("compare", val_hash_addr, (round, i, "hash_stage", hi))))

        return slots

    def build_kernel(
        self, forest_height: int, n_nodes: int, batch_size: int, rounds: int
    ):
        """Vectorized SIMD + VLIW kernel with a software-pipelined gather.

        Each group owns VLEN lanes kept in scratch across all rounds. Node values
        are gathered with scalar loads (2/cycle); while one group gathers, the
        hash/index chains of other groups occupy the 6 valu slots. Three hash
        stages fold to multiply-add: (a + c) + (a << k) == a * (1<<k + 1) + c.
        """
        b = _Bundler(SLOT_LIMITS)
        vrange = lambda a: tuple(range(a, a + VLEN))
        n_groups = cdiv(batch_size, VLEN)
        forest_p = 7
        idx_p = forest_p + n_nodes
        val_p = idx_p + batch_size

        def vec(name):
            return self.alloc_scratch(name, VLEN)

        def scalar(name):
            return self.alloc_scratch(name, 1)

        def const_vec(value, name):
            s = scalar(name + "_s")
            b.add("load", ("const", s, value), (), (s,))
            v = vec(name)
            b.add("valu", ("vbroadcast", v, s), (s,), vrange(v))
            return v

        one = const_vec(1, "one")
        nn = const_vec(n_nodes, "nn")
        fp = const_vec(forest_p, "fp")
        m1 = const_vec(4097, "m1")
        m3 = const_vec(33, "m3")
        m5 = const_vec(9, "m5")
        c1 = const_vec(0x7ED55D16, "c1")
        c2 = const_vec(0xC761C23C, "c2")
        c3 = const_vec(0x165667B1, "c3")
        c4 = const_vec(0xD3A2646C, "c4")
        c5 = const_vec(0xFD7046C5, "c5")
        c6 = const_vec(0xB55A4F09, "c6")
        sh19 = const_vec(19, "sh19")
        sh9 = const_vec(9, "sh9")
        sh16 = const_vec(16, "sh16")

        idx_v = [vec(f"idx{g}") for g in range(n_groups)]
        val_v = [vec(f"val{g}") for g in range(n_groups)]
        x = [vec(f"x{g}") for g in range(n_groups)]
        t = [vec(f"t{g}") for g in range(n_groups)]
        addr = [vec(f"addr{g}") for g in range(n_groups)]
        maddr = [scalar(f"m{g}") for g in range(n_groups)]

        # Load the batch into scratch vectors.
        for g in range(n_groups):
            b.add("load", ("const", maddr[g], idx_p + g * VLEN), (), (maddr[g],))
        for g in range(n_groups):
            b.add("load", ("vload", idx_v[g], maddr[g]), (maddr[g],), vrange(idx_v[g]))
        for g in range(n_groups):
            b.add("load", ("const", maddr[g], val_p + g * VLEN), (), (maddr[g],))
        for g in range(n_groups):
            b.add("load", ("vload", val_v[g], maddr[g]), (maddr[g],), vrange(val_v[g]))

        # Matches the reference kernel's first yield.
        b.add("flow", ("pause",))

        def hash_op(g, s):
            """Emit one of the 19 sequential hash/index vector ops for group g."""
            iv, vv, xx, tt = idx_v[g], val_v[g], x[g], t[g]
            if s == 0:
                slot = ("^", xx, vv, tt)
                reads, writes = vrange(vv) + vrange(tt), vrange(xx)
            elif s == 1:
                slot = ("multiply_add", xx, xx, m1, c1)
                reads, writes = vrange(xx) + vrange(m1) + vrange(c1), vrange(xx)
            elif s == 2:
                slot = (">>", tt, xx, sh19)
                reads, writes = vrange(xx) + vrange(sh19), vrange(tt)
            elif s == 3:
                slot = ("^", xx, xx, tt)
                reads, writes = vrange(xx) + vrange(tt), vrange(xx)
            elif s == 4:
                slot = ("^", xx, xx, c2)
                reads, writes = vrange(xx) + vrange(c2), vrange(xx)
            elif s == 5:
                slot = ("multiply_add", xx, xx, m3, c3)
                reads, writes = vrange(xx) + vrange(m3) + vrange(c3), vrange(xx)
            elif s == 6:
                slot = ("+", tt, xx, c4)
                reads, writes = vrange(xx) + vrange(c4), vrange(tt)
            elif s == 7:
                slot = ("<<", xx, xx, sh9)
                reads, writes = vrange(xx) + vrange(sh9), vrange(xx)
            elif s == 8:
                slot = ("^", xx, xx, tt)
                reads, writes = vrange(xx) + vrange(tt), vrange(xx)
            elif s == 9:
                slot = ("multiply_add", xx, xx, m5, c5)
                reads, writes = vrange(xx) + vrange(m5) + vrange(c5), vrange(xx)
            elif s == 10:
                slot = (">>", tt, xx, sh16)
                reads, writes = vrange(xx) + vrange(sh16), vrange(tt)
            elif s == 11:
                slot = ("^", xx, xx, tt)
                reads, writes = vrange(xx) + vrange(tt), vrange(xx)
            elif s == 12:
                slot = ("^", vv, xx, c6)
                reads, writes = vrange(xx) + vrange(c6), vrange(vv)
            elif s == 13:
                slot = ("&", tt, vv, one)
                reads, writes = vrange(vv) + vrange(one), vrange(tt)
            elif s == 14:
                slot = ("<<", xx, iv, one)
                reads, writes = vrange(iv) + vrange(one), vrange(xx)
            elif s == 15:
                slot = ("+", xx, xx, tt)
                reads, writes = vrange(xx) + vrange(tt), vrange(xx)
            elif s == 16:
                slot = ("+", iv, xx, one)
                reads, writes = vrange(xx) + vrange(one), vrange(iv)
            elif s == 17:
                slot = ("<", tt, iv, nn)
                reads, writes = vrange(iv) + vrange(nn), vrange(tt)
            else:
                slot = ("*", iv, iv, tt)
                reads, writes = vrange(iv) + vrange(tt), vrange(iv)
            b.add("valu", slot, reads, writes)

        # One gather every 4 cycles (8 loads, 2/cycle); hash chains of finished
        # groups fill the valu slots in the same cycles.
        total_gathers = n_groups * rounds
        gather_seq = 0
        load_j = 0
        stage = [-1] * n_groups
        group_round = [0] * n_groups
        pending = []
        done = 0
        b.add("valu", ("+", addr[0], idx_v[0], fp), vrange(idx_v[0]) + vrange(fp), vrange(addr[0]))

        while done < n_groups:
            for g in pending:
                stage[g] = 0
            pending.clear()

            if gather_seq < total_gathers:
                g = gather_seq % n_groups
                for jj in (0, 1):
                    j = load_j + jj
                    b.add("load", ("load", t[g] + j, addr[g] + j),
                          (addr[g] + j,), (t[g] + j,))
                load_j += 2
                if load_j == VLEN:
                    load_j = 0
                    pending.append(g)
                    gather_seq += 1
                    if gather_seq < total_gathers:
                        ng = gather_seq % n_groups
                        b.add("valu", ("+", addr[ng], idx_v[ng], fp),
                              vrange(idx_v[ng]) + vrange(fp), vrange(addr[ng]))

            for gg in range(n_groups):
                s = stage[gg]
                if s >= 0:
                    hash_op(gg, s)
                    stage[gg] = s + 1
                    if stage[gg] == 19:
                        stage[gg] = -1
                        group_round[gg] += 1
                        if group_round[gg] == rounds:
                            done += 1

        # Write the batch back out.
        for g in range(n_groups):
            b.add("load", ("const", maddr[g], idx_p + g * VLEN), (), (maddr[g],))
        for g in range(n_groups):
            b.add("store", ("vstore", maddr[g], idx_v[g]), (maddr[g],) + vrange(idx_v[g]))
        for g in range(n_groups):
            b.add("load", ("const", maddr[g], val_p + g * VLEN), (), (maddr[g],))
        for g in range(n_groups):
            b.add("store", ("vstore", maddr[g], val_v[g]), (maddr[g],) + vrange(val_v[g]))

        # Matches the reference kernel's final yield.
        b.add("flow", ("pause",))
        self.instrs = b.result()

BASELINE = 147734

def do_kernel_test(
    forest_height: int,
    rounds: int,
    batch_size: int,
    seed: int = 123,
    trace: bool = False,
    prints: bool = False,
):
    print(f"{forest_height=}, {rounds=}, {batch_size=}")
    random.seed(seed)
    forest = Tree.generate(forest_height)
    inp = Input.generate(forest, batch_size, rounds)
    mem = build_mem_image(forest, inp)

    kb = KernelBuilder()
    kb.build_kernel(forest.height, len(forest.values), len(inp.indices), rounds)
    # print(kb.instrs)

    value_trace = {}
    machine = Machine(
        mem,
        kb.instrs,
        kb.debug_info(),
        n_cores=N_CORES,
        value_trace=value_trace,
        trace=trace,
    )
    machine.prints = prints
    for i, ref_mem in enumerate(reference_kernel2(mem, value_trace)):
        machine.run()
        inp_values_p = ref_mem[6]
        if prints:
            print(machine.mem[inp_values_p : inp_values_p + len(inp.values)])
            print(ref_mem[inp_values_p : inp_values_p + len(inp.values)])
        assert (
            machine.mem[inp_values_p : inp_values_p + len(inp.values)]
            == ref_mem[inp_values_p : inp_values_p + len(inp.values)]
        ), f"Incorrect result on round {i}"
        inp_indices_p = ref_mem[5]
        if prints:
            print(machine.mem[inp_indices_p : inp_indices_p + len(inp.indices)])
            print(ref_mem[inp_indices_p : inp_indices_p + len(inp.indices)])
        # Updating these in memory isn't required, but you can enable this check for debugging
        # assert machine.mem[inp_indices_p:inp_indices_p+len(inp.indices)] == ref_mem[inp_indices_p:inp_indices_p+len(inp.indices)]

    print("CYCLES: ", machine.cycle)
    print("Speedup over baseline: ", BASELINE / machine.cycle)
    return machine.cycle


class Tests(unittest.TestCase):
    def test_ref_kernels(self):
        """
        Test the reference kernels against each other
        """
        random.seed(123)
        for i in range(10):
            f = Tree.generate(4)
            inp = Input.generate(f, 10, 6)
            mem = build_mem_image(f, inp)
            reference_kernel(f, inp)
            for _ in reference_kernel2(mem, {}):
                pass
            assert inp.indices == mem[mem[5] : mem[5] + len(inp.indices)]
            assert inp.values == mem[mem[6] : mem[6] + len(inp.values)]

    def test_kernel_trace(self):
        # Full-scale example for performance testing
        do_kernel_test(10, 16, 256, trace=True, prints=False)

    # Passing this test is not required for submission, see submission_tests.py for the actual correctness test
    # You can uncomment this if you think it might help you debug
    # def test_kernel_correctness(self):
    #     for batch in range(1, 3):
    #         for forest_height in range(3):
    #             do_kernel_test(
    #                 forest_height + 2, forest_height + 4, batch * 16 * VLEN * N_CORES
    #             )

    def test_kernel_cycles(self):
        do_kernel_test(10, 16, 256)


# To run all the tests:
#    python perf_takehome.py
# To run a specific test:
#    python perf_takehome.py Tests.test_kernel_cycles
# To view a hot-reloading trace of all the instructions:  **Recommended debug loop**
# NOTE: The trace hot-reloading only works in Chrome. In the worst case if things aren't working, drag trace.json onto https://ui.perfetto.dev/
#    python perf_takehome.py Tests.test_kernel_trace
# Then run `python watch_trace.py` in another tab, it'll open a browser tab, then click "Open Perfetto"
# You can then keep that open and re-run the test to see a new trace.

# To run the proper checks to see which thresholds you pass:
#    python tests/submission_tests.py

if __name__ == "__main__":
    unittest.main()
