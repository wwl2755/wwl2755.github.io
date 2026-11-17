"""Generate the blog's SVG figures into assets/fig/.

Colours are CSS variables (--fg, --muted, --line, --card, --accent, --accent2,
--good, --bad) so the figures follow the page's light and dark themes when the
SVG is inlined into the HTML (the build script inlines them).
"""
from pathlib import Path
from html import escape

OUT = Path(__file__).resolve().parent.parent / "assets" / "fig"
COLORS = {"line": "var(--line)", "accent": "var(--accent)", "accent2": "var(--accent2)",
          "bad": "var(--bad)", "good": "var(--good)", "muted": "var(--muted)"}


def svg(name, w, h, label, body):
    markers = "".join(
        f"<marker id='{name}-arr-{k}' viewBox='0 0 10 10' refX='9' refY='5' markerWidth='7' "
        f"markerHeight='7' orient='auto-start-reverse'><path d='M0 0L10 5L0 10z' fill='{v}'/></marker>"
        for k, v in COLORS.items())
    return (f"<svg class='fig' viewBox='0 0 {w} {h}' role='img' aria-label='{escape(label, quote=True)}' "
            f"xmlns='http://www.w3.org/2000/svg' font-family='var(--sans)'>"
            f"<defs>{markers}</defs>{body}</svg>")


def t(x, y, s, size=14, anchor="start", weight=400, color="var(--fg)", italic=False):
    st = " font-style='italic'" if italic else ""
    return (f"<text x='{x}' y='{y}' font-size='{size}' text-anchor='{anchor}' font-weight='{weight}' "
            f"fill='{color}'{st}>{escape(s)}</text>")


def rect(x, y, w, h, stroke="var(--line)", fill="var(--card)", sw=1.25, rx=8, dash=None, fop=None):
    d = f" stroke-dasharray='{dash}'" if dash else ""
    fo = f" fill-opacity='{fop}'" if fop is not None else ""
    return (f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='{rx}' fill='{fill}'{fo} "
            f"stroke='{stroke}' stroke-width='{sw}'{d}/>")


def path(name, d, color="line", sw=1.4, dash=None, head=True):
    da = f" stroke-dasharray='{dash}'" if dash else ""
    m = f" marker-end='url(#{name}-arr-{color})'" if head else ""
    return f"<path d='{d}' fill='none' stroke='{COLORS[color]}' stroke-width='{sw}'{da}{m}/>"


def node(x, y, w, h, title, lines=(), stroke="var(--line)", sw=1.25, fill="var(--card)", fop=None, title_size=14):
    out = [rect(x, y, w, h, stroke, fill, sw, fop=fop)]
    cy = y + 24 if lines else y + h / 2 + 5
    out.append(t(x + w / 2, cy, title, title_size, "middle", 600))
    for i, line in enumerate(lines):
        out.append(t(x + w / 2, y + 44 + 18 * i, line, 12.5, "middle", 400, "var(--muted)"))
    return "".join(out)


def lifeline(x, y0, y1, label, w=150):
    return (rect(x - w / 2, y0, w, 34, "var(--line)", "var(--card)") + t(x, y0 + 22, label, 14, "middle", 600)
            + f"<line x1='{x}' y1='{y0 + 34}' x2='{x}' y2='{y1}' stroke='var(--line)' stroke-width='1' stroke-dasharray='3 4'/>")


# ---------------------------------------------------------------- figures

def pd_transfer():
    n = "pdt"
    R, P, D = 100, 380, 660
    b = [t(24, 30, "One KV transfer in PD disaggregation (SGLang + Mooncake, push style)", 15, weight=600),
         lifeline(R, 50, 446, "Router"), lifeline(P, 50, 446, "Prefill"), lifeline(D, 50, 446, "Decode")]
    # 1 router -> both
    b.append(path(n, f"M{R} 118H{P - 4}"))
    b.append(path(n, f"M{R} 140H{D - 4}"))
    b.append(t(R + 12, 110, "1  request + bootstrap room", 12.5, color="var(--muted)"))
    # 2 decode allocates and tells prefill
    b.append(rect(D - 70, 170, 140, 34, "var(--accent2)", "var(--card)", 1.5))
    b.append(t(D, 192, "allocate pages", 13, "middle", 600))
    b.append(path(n, f"M{D - 70} 228H{P + 4}", "accent2"))
    b.append(t((P + D) / 2, 220, "2  destination KV page indices", 12.5, "middle", color="var(--muted)"))
    # 3 RDMA write
    b.append(rect(P - 70, 256, 140, 34, "var(--accent)", "var(--card)", 1.5))
    b.append(t(P, 278, "compute KV", 13, "middle", 600))
    b.append(path(n, f"M{P + 70} 300H{D - 4}", "accent", 3))
    b.append(t(D - 14, 324, "3  RDMA WRITE into Decode GPU memory", 12.5, "end", 600, "var(--accent)"))
    b.append(t(D - 14, 342, "one-sided: Decode's CPU never sees it", 12, "end", color="var(--muted)", italic=True))
    # 4 done
    b.append(path(n, f"M{P} 380H{D - 4}", "line", 1.4, "5 4"))
    b.append(t((P + D) / 2, 372, "4  done notice (after the write completes)", 12.5, "middle", color="var(--muted)"))
    b.append(rect(D - 80, 400, 160, 34, "var(--line)", "var(--card)"))
    b.append(t(D, 422, "pages go to attention", 13, "middle", 600))
    return svg(n, 760, 458, "One KV transfer in PD disaggregation", "".join(b))


def pd_race():
    n = "race"
    P, D, B = 120, 420, 660
    b = [t(24, 30, "The late write: a timeout is not proof that the remote write stopped", 15, weight=600),
         lifeline(P, 50, 470, "Prefill + NIC", 170), lifeline(D, 50, 470, "Decode"), lifeline(B, 50, 470, "Request B")]
    b.append(path(n, f"M{D} 112H{P + 4}", "accent2"))
    b.append(t((P + D) / 2, 104, "write A's KV into page P", 12.5, "middle", color="var(--muted)"))
    # the in-flight write: a long diagonal
    b.append(path(n, f"M{P} 140L{D - 4} 382", "accent", 3, "7 5"))
    b.append(t(P + 8, 330, "RDMA WRITE queued on the NIC", 12.5, weight=600, color="var(--accent)"))
    b.append(t(P + 8, 348, "(cannot be cancelled)", 12, color="var(--muted)", italic=True))
    # timeout
    b.append(rect(D + 14, 186, 210, 50, "var(--accent)", "var(--card)", 1.5))
    b.append(t(D + 119, 206, "local timeout fires", 13, "middle", 600))
    b.append(t(D + 119, 225, "abort A, free page P", 12.5, "middle", color="var(--muted)"))
    # B arrives
    b.append(path(n, f"M{B} 270H{D + 4}"))
    b.append(t((D + B) / 2, 262, "new request", 12.5, "middle", color="var(--muted)"))
    b.append(t(D + 14, 300, "P is allocated to B", 12.5, color="var(--muted)"))
    # landing
    b.append(f"<circle cx='{D}' cy='384' r='9' fill='var(--bad)'/>")
    b.append(t(D + 18, 380, "A's KV lands in page P", 13, weight=600, color="var(--bad)"))
    b.append(t(D + 18, 398, "and overwrites B's KV", 12.5, color="var(--muted)"))
    b.append(path(n, f"M{D} 438H{B - 4}", "bad", 2))
    b.append(t((D + B) / 2, 430, "HTTP 200, A's context mixed in", 12.5, "middle", 600, "var(--bad)"))
    return svg(n, 760, 482, "The late RDMA write overwrites a reused page", "".join(b))


def nondeterminism():
    n = "nd"
    b = [t(24, 30, "A test walks one path; a model checker walks every branch", 15, weight=600)]
    root = (24, 150, 220, 56)
    b.append(node(*root, "state s", ["A's RDMA write in flight"]))
    kids = [("RDMA completes first", 70), ("timeout fires first", 150), ("new request arrives", 230)]
    for i, (lab, y) in enumerate(kids):
        hl = i == 0
        b.append(path(n, f"M244 178C290 178 300 {y + 22} 330 {y + 22}", "accent2" if hl else "line", 2.4 if hl else 1.3))
        b.append(node(332, y, 210, 44, lab, stroke="var(--accent2)" if hl else "var(--line)", sw=2 if hl else 1.25, title_size=13))
        for j, dy in enumerate((-16, 0, 16)):
            c = "accent2" if (hl and j == 1) else "line"
            b.append(path(n, f"M542 {y + 22}L612 {y + 22 + dy * 1.6}", c, 2.4 if c == "accent2" else 1.1))
        b.append(t(622, y + 27, "…", 16, color="var(--muted)"))
    b.append(f"<line x1='560' y1='300' x2='600' y2='300' stroke='var(--accent2)' stroke-width='2.4'/>")
    b.append(t(608, 304, "one test run", 12.5, color="var(--accent2)", weight=600))
    b.append(f"<line x1='560' y1='322' x2='600' y2='322' stroke='var(--line)' stroke-width='1.3'/>")
    b.append(t(608, 326, "explored by TLC", 12.5, color="var(--muted)"))
    return svg(n, 760, 344, "Nondeterminism: every enabled action is a branch", "".join(b))


def state_machine():
    n = "sm"
    b = [t(24, 30, "A state is a snapshot; an action moves one snapshot to the next", 15, weight=600)]

    def pool(x, y, owners, hi=None):
        out = []
        for i, o in enumerate(owners):
            used = o is not None
            stroke = "var(--accent)" if i == hi else ("var(--accent2)" if used else "var(--line)")
            out.append(node(x + i * 74, y, 64, 56, f"page {i}", [o or "free"], stroke=stroke, sw=2 if i == hi else 1.25, title_size=12.5))
        return "".join(out)

    b.append(t(24, 66, "state s0", 13, weight=600, color="var(--muted)"))
    b.append(pool(24, 76, ["A", "B", None, None]))
    b.append(t(24, 160, "free = {2, 3}", 13, color="var(--fg)"))
    b.append(t(24, 180, "owner = {0: A, 1: B}", 13, color="var(--fg)"))
    b.append(path(n, "M330 104H418", "accent", 2))
    b.append(t(374, 94, "Alloc(C, 2)", 13, "middle", 600, "var(--accent)"))
    b.append(t(374, 128, "needs 2 ∈ free", 11.5, "middle", color="var(--muted)"))
    b.append(t(430, 66, "state s1", 13, weight=600, color="var(--muted)"))
    b.append(pool(430, 76, ["A", "B", "C", None], hi=2))
    b.append(t(430, 160, "free = {3}", 13, color="var(--fg)"))
    b.append(t(430, 180, "owner = {0: A, 1: B, 2: C}", 13, color="var(--fg)"))
    return svg(n, 760, 200, "Alloc moves the allocator from one state to the next", "".join(b))


def pd_fix():
    n = "fix"
    b = [t(24, 30, "A page is reused only after proof that the write stopped", 15, weight=600)]
    b.append(path(n, "M194 170H266"))
    b.append(path(n, "M440 162H480V110H532", "good"))
    b.append(path(n, "M440 178H480V230H532", "bad"))
    b.append(node(24, 142, 170, 56, "PRIVATE", ["in use by one request"]))
    b.append(node(270, 142, 170, 56, "DRAINING", ["waits for stop evidence"]))
    b.append(t(355, 222, "its request has already failed", 12, "middle", color="var(--muted)", italic=True))
    b.append(node(536, 82, 200, 56, "FREE", ["ACK: the write has stopped"], "var(--good)", 1.8))
    b.append(node(536, 202, 200, 56, "QUARANTINED", ["no proof: never reused"], "var(--bad)", 1.8))
    b.append(t(230, 162, "release", 12, "middle", color="var(--muted)"))
    b.append(t(506, 102, "ACK", 12, "middle", color="var(--muted)"))
    b.append(t(506, 248, "no ACK", 12, "middle", color="var(--muted)"))
    return svg(n, 760, 278, "PdLedger page states after a release or timeout", "".join(b))


def lora_ledgers():
    n = "lora"
    b = [t(24, 30, "Two ledgers, plus a copy in every queued request", 15, weight=600)]
    b.append(node(24, 56, 210, 92, "front-end ledger", ["serving.py", "name → LoRARequest", "(id, path)"]))
    b.append(node(284, 56, 190, 92, "queued request r", ["carries the LoRARequest", "current at admission"], "var(--accent)", 1.8))
    b.append(node(524, 56, 212, 92, "worker ledger", ["worker_manager.py", "CPU LRU cache: id → weights", "capacity max_cpu_loras"]))
    b.append(path(n, "M234 102H280"))
    b.append(path(n, "M474 102H520"))
    b.append(t(257, 172, "at admission", 12, "middle", color="var(--muted)"))
    b.append(t(497, 172, "add_adapter()", 12, "middle", color="var(--muted)"))
    b.append(rect(24, 196, 712, 64, "var(--line)", "var(--card)", 1.25, dash="5 4"))
    b.append(t(40, 222, "hot reload (load_inplace=True): the worker reloads from the new path and the front end points at it,", 12.5))
    b.append(t(40, 242, "but requests already queued still carry the old path; a cache miss loads whatever path the request carries.", 12.5, color="var(--muted)"))
    return svg(n, 760, 276, "vLLM keeps LoRA state in two ledgers", "".join(b))


def lora_trace():
    n = "trace"
    steps = ["init", "Admit r1", "Reload", "UseB", "Run r1", "Admit r2", "Run r2"]
    reg = [1, 1, 2, 2, 2, 2, 2]
    cache = [1, 1, 2, None, 1, 1, 1]
    x0, dx = 120, 96
    Y = {2: 90, 1: 170, None: 230}
    b = [t(24, 30, "TLC's counterexample: the worker cache falls behind the front end at step 5", 15, weight=600)]
    for v, lab in ((2, "v2"), (1, "v1"), (None, "not cached")):
        b.append(f"<line x1='{x0 - 20}' y1='{Y[v]}' x2='{x0 + dx * 6 + 20}' y2='{Y[v]}' stroke='var(--line)' stroke-opacity='0.35'/>")
        b.append(t(x0 - 30, Y[v] + 4, lab, 12.5, "end", color="var(--muted)"))
    pts = " ".join(f"{x0 + i * dx},{Y[v] - 4}" for i, v in enumerate(reg))
    b.append(f"<polyline points='{pts}' fill='none' stroke='var(--accent2)' stroke-width='2.4'/>")
    pts = " ".join(f"{x0 + i * dx},{Y[v] + 4}" for i, v in enumerate(cache))
    b.append(f"<polyline points='{pts}' fill='none' stroke='var(--accent)' stroke-width='2.4' stroke-dasharray='6 4'/>")
    for i, v in enumerate(cache):
        b.append(f"<circle cx='{x0 + i * dx}' cy='{Y[v] + 4}' r='4' fill='var(--accent)'/>")
    for i, s in enumerate(steps):
        b.append(t(x0 + i * dx, 262, f"{i + 1}", 12, "middle", 600, "var(--muted)"))
        b.append(t(x0 + i * dx, 280, s, 12.5, "middle"))
    b.append(f"<circle cx='{x0 + 6 * dx}' cy='{Y[1] + 4}' r='9' fill='none' stroke='var(--bad)' stroke-width='2'/>")
    b.append(t(x0 + 4 * dx, Y[1] - 16, "cache regresses to v1", 12.5, "middle", 600, "var(--accent)"))
    b.append(t(x0 + 6 * dx + 16, Y[1] + 32, "r2 carries v2, runs v1", 12.5, "end", 600, "var(--bad)"))
    b.append(f"<line x1='{x0}' y1='306' x2='{x0 + 30}' y2='306' stroke='var(--accent2)' stroke-width='2.4'/>")
    b.append(t(x0 + 38, 310, "registered version (front end)", 12.5, color="var(--fg)"))
    b.append(f"<line x1='{x0 + 300}' y1='306' x2='{x0 + 330}' y2='306' stroke='var(--accent)' stroke-width='2.4' stroke-dasharray='6 4'/>")
    b.append(t(x0 + 338, 310, "adapter A in the worker cache", 12.5, color="var(--fg)"))
    return svg(n, 760, 326, "TLC counterexample for the LoRA hot-reload bug", "".join(b))


def vstack_stages():
    n = "vs"
    stages = [("S0", "decompose", ["control, data, boundaries;", "historical bug anchors"]),
              ("S1", "select", ["tool and assurance", "tier per property"]),
              ("S2", "spec", ["owner approves;", "hash-pinned"]),
              ("S3", "model", ["from pinned code,", "file:line@commit"]),
              ("S4", "calibrate + traces", ["bug fails, fix passes,", "real traces replay"]),
              ("S5", "red team", ["attack fidelity, strength,", "scope extrapolation"]),
              ("S6", "hunt + fix", ["counterexamples, fixes", "in model and code"]),
              ("S7", "prove", ["inductive invariants,", "TLAPS"]),
              ("S8", "package + maintain", ["regression skill that", "reruns as code changes"])]
    used = {"S2", "S3", "S4", "S6", "S7"}
    W, H, gx, gy = 216, 80, 32, 36
    b = [t(24, 30, "vstack's nine stages (orange: the ones the LoRA example walked through)", 15, weight=600)]
    pos = {}
    for i, (sid, name, lines) in enumerate(stages):
        r, c = divmod(i, 3)
        if r == 1:
            c = 2 - c  # snake
        x, y = 24 + c * (W + gx), 52 + r * (H + gy)
        pos[sid] = (x, y)
        hl = sid in used
        b.append(node(x, y, W, H, f"{sid}  {name}", lines, "var(--accent)" if hl else "var(--line)", 1.8 if hl else 1.25))
    order = [s for s, _, _ in stages]
    for a, c in zip(order, order[1:]):
        (x1, y1), (x2, y2) = pos[a], pos[c]
        if y1 == y2:
            if x2 > x1:
                b.append(path(n, f"M{x1 + W} {y1 + H / 2}H{x2 - 4}"))
            else:
                b.append(path(n, f"M{x1} {y1 + H / 2}H{x2 + W + 4}"))
        else:
            b.append(path(n, f"M{x1 + W / 2} {y1 + H}V{y2 - 4}"))
    return svg(n, 760, 52 + 3 * H + 2 * gy + 20, "vstack's nine stages", "".join(b))


def interleavings():
    import math
    n = "il"
    rows = [("2 actors × 5 steps", 252), ("3 actors × 5 steps", 756756),
            ("4 actors × 5 steps", 11732745024), ("3 actors × 10 steps", 5550996791340)]
    x0, W, top = 190, 420, 70
    X = lambda v: x0 + W * math.log10(v) / 13
    b = [t(24, 30, "Possible orderings explode with every actor and step", 15, weight=600),
         t(24, 50, "log scale", 12, color="var(--muted)", italic=True)]
    for e in (0, 3, 6, 9, 12):
        x = X(10 ** e)
        b.append(f"<line x1='{x}' y1='{top - 6}' x2='{x}' y2='{top + 4 * 46}' stroke='var(--line)' stroke-opacity='0.35'/>")
        b.append(t(x, top + 4 * 46 + 18, f"10^{e}" if e else "1", 12, "middle", color="var(--muted)"))
    for i, (lab, v) in enumerate(rows):
        y = top + i * 46
        b.append(t(x0 - 12, y + 19, lab, 13, "end"))
        b.append(rect(x0, y + 4, X(v) - x0, 22, "var(--accent)", "var(--accent)", 1, rx=4, fop=0.25))
        b.append(t(X(v) + 8, y + 20, f"{v:,}", 12.5, weight=600))
    return svg(n, 760, top + 4 * 46 + 36, "Possible orderings for n actors with k steps each", "".join(b))


def m_p_check():
    n = "mp"
    b = [t(24, 30, "Formal verification checks a model against a property, for every behavior", 15, weight=600)]
    b.append(node(24, 56, 210, 72, "Model M", ["the system as a state machine:", "states + actions"]))
    b.append(node(24, 150, 210, 72, "Property P", ["what must always (or", "eventually) be true"]))
    b.append(node(300, 103, 170, 72, "Checker", ["TLC, Z3 or TLAPS", "tries every behavior"], "var(--accent2)", 1.8))
    b.append(node(536, 56, 200, 72, "P holds", ["under the listed", "assumptions A"], "var(--good)", 1.8))
    b.append(node(536, 150, 200, 72, "Counterexample", ["an exact step-by-step", "trace that breaks P"], "var(--bad)", 1.8))
    b.append(path(n, "M234 92H262V130H296"))
    b.append(path(n, "M234 186H262V148H296"))
    b.append(path(n, "M470 130H500V92H532", "good"))
    b.append(path(n, "M470 148H500V186H532", "bad"))
    return svg(n, 760, 240, "A checker takes a model and a property and returns either a proof or a counterexample", "".join(b))


def safety_liveness():
    n = "sl"
    b = [t(24, 30, "What a violation looks like", 15, weight=600)]

    def st(x, y, lab, stroke="var(--line)", dash=None, fill="var(--card)"):
        d = f" stroke-dasharray='{dash}'" if dash else ""
        return (f"<circle cx='{x}' cy='{y}' r='20' fill='{fill}' stroke='{stroke}' stroke-width='1.6'{d}/>"
                + t(x, y + 5, lab, 13, "middle", 600))
    b.append(t(24, 62, "Safety: a finite trace reaches a bad state", 13.5, weight=600, color="var(--accent)"))
    xs = [50, 130, 210, 290]
    for i, x in enumerate(xs):
        b.append(st(x, 110, f"s{i}", "var(--bad)" if i == 3 else "var(--line)"))
        if i:
            b.append(path(n, f"M{xs[i - 1] + 20} 110H{x - 24}"))
    b.append(t(290, 150, "bad state", 12.5, "middle", 600, "var(--bad)"))
    b.append(t(24, 186, "e.g. a page owned by two requests", 12.5, color="var(--muted)"))
    ox = 400
    b.append(t(ox, 62, "Liveness: the run loops forever", 13.5, weight=600, color="var(--accent2)"))
    b.append(st(ox + 26, 110, "s0"))
    b.append(st(ox + 106, 110, "s1"))
    b.append(st(ox + 186, 110, "s2"))
    b.append(st(ox + 296, 110, "done", "var(--good)", "4 3"))
    b.append(path(n, f"M{ox + 46} 110H{ox + 82}"))
    b.append(path(n, f"M{ox + 126} 104H{ox + 162}"))
    b.append(path(n, f"M{ox + 166} 118H{ox + 130}"))
    b.append(path(n, f"M{ox + 206} 110H{ox + 272}", "good", 1.4, "4 4"))
    b.append(t(ox + 239, 100, "never taken", 12, "middle", color="var(--muted)", italic=True))
    b.append(t(ox + 146, 150, "s1 ↔ s2 forever", 12.5, "middle", 600, "var(--accent2)"))
    b.append(t(ox, 186, "e.g. a request that never finishes", 12.5, color="var(--muted)"))
    return svg(n, 760, 204, "A safety violation is a finite trace; a liveness violation is an infinite loop", "".join(b))


def induction():
    n = "ind"
    b = [t(24, 30, "Why a property must be strengthened before it can be proved by induction", 15, weight=600)]
    b.append("<ellipse cx='260' cy='185' rx='232' ry='118' fill='none' stroke='var(--line)' stroke-width='1.5'/>")
    b.append(t(40, 58, "P: nodes with lock_ref > 0 are never evicted", 13, weight=600))
    b.append("<ellipse cx='220' cy='190' rx='150' ry='72' fill='var(--accent2)' fill-opacity='0.08' stroke='var(--accent2)' stroke-width='2'/>")
    b.append(t(220, 146, "Inv = P + accurate lock_ref", 12.5, "middle", 600, "var(--accent2)"))
    pts = [(110, 195), (170, 172), (240, 208), (300, 182)]
    b.append(f"<circle cx='{pts[0][0]}' cy='{pts[0][1]}' r='7' fill='var(--accent2)'/>")
    b.append(t(pts[0][0], pts[0][1] + 24, "Init", 12, "middle", 600))
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        b.append(f"<circle cx='{x2}' cy='{y2}' r='5' fill='var(--fg)'/>")
        b.append(path(n, f"M{x1 + 7} {y1}L{x2 - 8} {y2}", "accent2", 1.4))
    b.append(t(220, 244, "every step from Inv stays in Inv", 12, "middle", color="var(--muted)", italic=True))
    ux, uy = 420, 200
    b.append(f"<circle cx='{ux}' cy='{uy}' r='6' fill='var(--bad)'/>")
    b.append(t(ux, uy - 14, "u", 13, "middle", 600, "var(--bad)"))
    b.append(path(n, f"M{ux + 6} {uy + 6}L{ux + 100} {uy + 80}", "bad", 1.8))
    b.append(f"<circle cx='{ux + 104}' cy='{uy + 83}' r='6' fill='none' stroke='var(--bad)' stroke-width='1.6'/>")
    b.append(t(520, 110, "u: an unreachable state in P", 12.5, weight=600, color="var(--bad)"))
    b.append(t(520, 128, "where lock_ref is already wrong.", 12.5, color="var(--muted)"))
    b.append(t(520, 146, "One unlock steps out of P, so", 12.5, color="var(--muted)"))
    b.append(t(520, 164, "the induction step fails for P.", 12.5, color="var(--muted)"))
    return svg(n, 760, 316, "A non-inductive property versus a strengthened inductive invariant", "".join(b))


def bfs():
    n = "bfs"
    b = [t(24, 30, "Breadth-first search finds the shortest counterexample first", 15, weight=600)]
    levels = [[380], [220, 380, 540], [140, 270, 380, 490, 620], [100, 200, 300, 420, 520, 660]]
    ys = [70, 140, 210, 280]
    parent = {1: [0, 0, 0], 2: [0, 0, 1, 2, 2], 3: [0, 1, 1, 3, 3, 3]}
    path_nodes = {(0, 0), (1, 2), (2, 3), (3, 3)}
    for d in range(1, 4):
        for i, x in enumerate(levels[d]):
            px = levels[d - 1][parent[d][i]]
            on = (d, i) in path_nodes and (d - 1, parent[d][i]) in path_nodes
            b.append(f"<line x1='{px}' y1='{ys[d - 1] + 12}' x2='{x}' y2='{ys[d] - 12}' stroke='{'var(--accent)' if on else 'var(--line)'}' stroke-width='{2.4 if on else 1.2}'/>")
    for d, row in enumerate(levels):
        b.append(t(24, ys[d] + 5, f"depth {d}", 12, color="var(--muted)"))
        for i, x in enumerate(row):
            bad = (d, i) == (3, 3)
            seen = (d, i) == (2, 4)
            fill = "var(--bad)" if bad else ("var(--accent)" if (d, i) in path_nodes else "var(--card)")
            dash = " stroke-dasharray='3 3'" if seen else ""
            b.append(f"<circle cx='{x}' cy='{ys[d]}' r='12' fill='{fill}' stroke='{'var(--bad)' if bad else 'var(--line)'}' stroke-width='1.4'{dash}/>")
    b.append(t(420, ys[3] + 34, "first violation found: a 3-step trace", 12.5, "middle", 600, "var(--bad)"))
    b.append(t(642, ys[2] + 4, "seen: skipped", 12, color="var(--muted)", italic=True))
    b.append(t(24, 350, "All states at depth k are checked before any at depth k + 1, so no shorter violating trace can exist.", 12.5, color="var(--muted)"))
    return svg(n, 760, 366, "Model checking explores states level by level", "".join(b))


def verified_means():
    n = "vm"
    b = [t(24, 30, "\"Verified\" means: under assumptions A, model M satisfies property P", 15, weight=600)]
    cols = [("A", "Assumptions", ["false assumption, e.g.", "\"RDMA completion notices", "always arrive\""], 24),
            ("M", "Model", ["model differs from the code:", "a path left out, or a", "non-atomic step made atomic"], 270),
            ("P", "Property", ["wrong or partial spec:", "you proved something other", "than what you care about"], 516)]
    for letter, name, lines, x in cols:
        b.append(rect(x, 54, 220, 128, "var(--accent)", "var(--card)", 1.5))
        b.append(t(x + 20, 92, letter, 30, weight=700, color="var(--accent)"))
        b.append(t(x + 54, 86, name, 14, weight=600))
        b.append(t(x + 54, 104, "where a bug can still hide", 11.5, color="var(--muted)", italic=True))
        for i, line in enumerate(lines):
            b.append(t(x + 20, 132 + 17 * i, line, 12.5, color="var(--muted)"))
    b.append(rect(24, 200, 712, 44, "var(--line)", "var(--card)", 1.25, dash="5 4"))
    b.append(t(380, 227, "Trusted base, assumed correct: the checker, the compiler, the hardware", 13, "middle", color="var(--muted)"))
    return svg(n, 760, 260, "Where bugs can still hide after a proof", "".join(b))


FIGS = {"pd-transfer": pd_transfer, "pd-race": pd_race, "nondeterminism": nondeterminism,
        "state-machine": state_machine, "pd-fix": pd_fix, "lora-ledgers": lora_ledgers,
        "lora-trace": lora_trace, "vstack-stages": vstack_stages,
        "interleavings": interleavings, "m-p-check": m_p_check, "safety-liveness": safety_liveness,
        "induction": induction, "bfs": bfs, "verified-means": verified_means}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in FIGS.items():
        (OUT / f"{name}.svg").write_text(fn())
    print("wrote", len(FIGS), "figures to", OUT)
