# Can two different (page, slot) pairs map to the same KV address?
# unsat = impossible for every value; change `t < PAGE` to `t <= PAGE` to see `sat`.
from z3 import Ints, Or, Solver

p1, t1, p2, t2 = Ints("p1 t1 p2 t2")
PAGE, NPAGES = 16, 1024
s = Solver()
for p, t in [(p1, t1), (p2, t2)]:
    s.add(0 <= p, p < NPAGES, 0 <= t, t < PAGE)
s.add(Or(p1 != p2, t1 != t2))         # two different (page, slot) pairs
s.add(p1 * PAGE + t1 == p2 * PAGE + t2)  # ...same address?
print(s.check())
if str(s.check()) == "sat":
    print(s.model())
