---
title: What I Learned About Formal Verification for LLM Inference
date: 2026-11-16
description: Learning notes on formal verification for LLM inference, from a silent PD-disaggregation bug to an 80-line TLA+ model of a real vLLM bug.
---

In October 2026, [Cloudflare disclosed](https://blog.cloudflare.com/kv-cache-exposure-remediation/) that its GLM-5.3 model on Workers AI had returned 155 responses containing data from other customers' requests. The cause combined a configuration mismatch with an SGLang bug in prefill-decode (PD) disaggregated mode: a request that should have been rejected as too long reported itself as live, and the decode node then generated a response while attending over stale KV cache pages from earlier requests ([SGLang issue #30233](https://github.com/sgl-project/sglang/issues/30233)). The clients got HTTP 200, not an error. SGLang's maintainers published a matching [security update on request isolation](https://www.lmsys.org/blog/2026-10-26-cf-security/).

Hao AI Lab's [Towards Verifiable LLM Infra](https://haoailab.com/blogs/verifiable-llm-infra/) cites these disclosures as evidence of the production risk that motivates its work on formal verification. This post is my learning notes from that blog and its two repos, [vstack](https://github.com/hao-ai-lab/vstack) and [veriserve](https://github.com/hao-ai-lab/veriserve).

## How a late KV write leaks data

A closely related PD failure, which veriserve studies in depth, needs no misconfiguration at all: a Decode instance times out waiting for a request's KV cache, frees that request's KV pages, and hands them to a new request. Meanwhile the Prefill instance's RDMA write for the old request is still queued on the NIC, and it lands in the new request's pages. Nothing crashes and no error is logged. The new user just gets an answer polluted by another user's context.

### How the KV gets there

In PD disaggregation, Decode reserves KV pages for the request and tells Prefill which pages to fill. Prefill computes the KV, and its NIC writes it straight into Decode's GPU memory with one-sided RDMA. When the write is done, Prefill sends a done notice, and only then does Decode use the pages.

{{fig:pd-transfer|One KV transfer. Decode chooses the pages; Prefill's NIC writes into them directly.}}

Three properties make this fragile:

- **One-sided:** Decode's CPU is not involved and cannot see when the write happens.
- **Not cancellable:** in [Hao AI Lab's](https://haoailab.com/blogs/verifiable-llm-infra/) words, one-sided transfers already queued on the NIC "cannot be canceled in hardware on the studied transport paths".
- **Notice-only:** the only way Decode learns the write finished is a message from Prefill.

### How it goes wrong

Put a timeout on top and you get the bug:

{{fig:pd-race|The in-flight write is drawn as a long diagonal: it leaves Prefill before the timeout and lands after page P has a new owner.}}

1. Decode allocates page P for request A and tells Prefill to write into P.
2. Prefill posts an RDMA WRITE for A targeting P. It waits in the NIC queue.
3. The network is congested or Prefill is slow. Decode's local timeout fires.
4. Decode decides A has failed: **it aborts A and frees P**.
5. Request B arrives. The allocator gives P to B, and B's KV is written into P.
6. A's RDMA write finally lands: **A's KV overwrites B's page P**.
7. B runs attention over the corrupted KV and returns HTTP 200 with A's context mixed in.

The root cause is one wrong inference: Decode treated "I have waited too long" as "the other side has stopped writing". With one-sided RDMA, local elapsed time cannot prove that a remote write has stopped.

### Why testing misses it

With n concurrent actors each taking k steps, the number of possible orderings (interleavings) is (nk)!/(k!)^n:

{{fig:interleavings|Each extra actor or step multiplies the orderings. Counts are (nk)!/(k!)^n, computed exactly.}}

A PD deployment has at least the scheduler, the Prefill worker, the Decode worker, the RDMA NIC, GPU streams, and users who can abort at any moment. A stress test walks one of these orderings, usually the most common one. Reproducing the bug on real hardware also needs multiple GPUs, RDMA NICs and precise cross-node timing.

## Formal verification in one page

Formal verification means treating the program as a mathematical object, writing "correct" as a precise proposition, and proving it. The whole field fits in one line: **M ⊨ P**, "model M satisfies property P". Testing checks examples; verification checks a universal claim: for all inputs and **all schedules**, the program satisfies P.

The tools that come up below are **TLA+**, a language for writing a system down as a state machine; **TLC**, the model checker that explores a TLA+ model's states; **TLAPS**, the proof checker for TLA+; and **Z3**, an SMT solver that answers questions about arithmetic.

{{fig:m-p-check|The three parts of every formal check: a model, a property, and a checker that either confirms it or hands back a counterexample.}}

### The model is a state machine

A state is a snapshot of the variables that matter. An action has a precondition (when it may happen) and an effect (how the state changes):

{{fig:state-machine|Two variables describe the whole allocator. Alloc(C, 2) is enabled because page 2 is free.}}

```python
def Alloc(r, p):
    require(p in free)   # precondition
    free.remove(p)       # effect
    owner[p] = r

def Free(p):
    require(p not in free)
    owner[p] = None
    free.add(p)
```

One run of the system is a sequence of states s0 → s1 → s2 …, called a behavior or trace.

### Nondeterminism is the key trick

At every step, any action whose precondition holds may be the next one. You do not simulate the network, the thread scheduler or the NIC. You only say "the RDMA completion OR the timeout OR a new request may happen next", and the checker tries every branch. Everything you cannot control becomes a choice, and the property must hold on every branch.

{{fig:nondeterminism|Each enabled action is a branch. A test follows one; a model checker such as TLC enumerates them all.}}

### Safety and liveness

| | Safety | Liveness |
| --- | --- | --- |
| Meaning | A bad thing never happens | A good thing eventually happens |
| Inference examples | A KV page is never owned by two requests; a locked radix node is never evicted | Every request finishes; a draining page is eventually reclaimed |
| Counterexample | A finite trace that reaches the bad state | An infinite loop: deadlock, livelock, starvation |

Liveness usually needs fairness assumptions ("if the RDMA completion keeps being possible, it eventually happens"), and those assumptions are promises about your hardware.

{{fig:safety-liveness|A safety bug shows up as a finite trace; a liveness bug as a loop that never reaches the good state.}}

### Proofs rest on inductive invariants

To prove a property Inv holds in every reachable state you need two facts: **Init ⇒ Inv** (every start state satisfies Inv) and **Inv ∧ Next ⇒ Inv′** (if Inv holds and any one enabled action runs, Inv still holds afterwards). Here ⇒ means "implies", ∧ means "and", Init describes the start states, Next means "any one enabled action", and the prime in Inv′ means "evaluated on the state after the step". It is the same idea as a loop invariant: true on entry, preserved by every iteration.

The catch: the property you care about is rarely inductive on its own. Take P = "a prefix-cache node that a running request still uses is never evicted", where the eviction code only evicts nodes with lock_ref = 0. P also holds in an odd state that the real system never reaches: lock_ref = 0 while a running request still uses the node (the count is too low). From that state a single eviction step is legal and evicts a node in use. So "P before the step" does not guarantee "P after the step", and the induction fails. You must strengthen it, for example by adding "lock_ref equals the number of running requests whose path crosses the node". Finding that strengthening is writing down why the system is correct. veriserve's proof of its PD page ledger needed [54 inductive invariants across 64 protocol actions](https://github.com/hao-ai-lab/veriserve#readme).

{{fig:induction|P alone admits unreachable states like u from which one step breaks P. The strengthened Inv excludes them, so every step from Inv stays in Inv.}}

### Three families of tools, used together

| | Model checking | SMT solving | Theorem proving |
| --- | --- | --- | --- |
| Tools | TLC, Apalache | Z3 | TLAPS, Lean, Dafny |
| How | Enumerate every reachable state | Encode the question as a formula: "is there a solution?" | Write a proof, usually by induction |
| Automation | Full | Mostly | Needs a human or an AI |
| Any scale | No, bounded | Bounded, or within a theory | Yes |
| Finding bugs | Excellent: shortest counterexample trace | Good: concrete counterexample values | Weak |
| Best for | Protocols, concurrency, lifecycles | Arithmetic, indexing, addresses | Final, unbounded guarantees |

Model checking does breadth-first search, so the first violation it finds is the **shortest** reproduction. It suffers from state explosion, so you run it at tiny scale (say 3 requests and 2 pages). That works because of the small-scope hypothesis: most concurrency bugs show up at small scale. In my own toy model of the RDMA bug above, 2 requests and 1 page are enough to hit it.

{{fig:bfs|TLC explores level by level, so the first violation it reports is the shortest possible reproduction.}}

SMT turns a bug into a question. Can two different (page, slot) pairs map to the same KV address? ([kv_address.py](/assets/models/kv_address.py))

```python
from z3 import *
p1, t1, p2, t2 = Ints("p1 t1 p2 t2")
PAGE, NPAGES = 16, 1024
s = Solver()
for p, t in [(p1, t1), (p2, t2)]:
    s.add(0 <= p, p < NPAGES, 0 <= t, t < PAGE)
s.add(Or(p1 != p2, t1 != t2))         # two different (page, slot) pairs
s.add(p1*PAGE + t1 == p2*PAGE + t2)   # ...same address?
print(s.check())  # unsat: impossible, proven for every value
```

Change `t < PAGE` to `t <= PAGE` (a classic off-by-one) and Z3 answers `sat` with a concrete collision: page 0 slot 16 and page 1 slot 0.

### Reading "verified" correctly

Every result really means: **under assumptions A, model M satisfies property P.** A can be wrong (the NIC does drop completion notices). M can be wrong (a code path left out, or a non-atomic step modeled as atomic). P can be wrong (you proved something other than what you care about). "Verified" does not mean bug-free. It means any remaining bug lives outside an explicit list of assumptions and abstractions.

{{fig:verified-means|A proof moves the bugs that can remain into three named places, plus the tools you trust.}}

## The PD bug is a dilemma, not a bad timeout value

With safety and liveness in hand, the PD bug looks different. Decode has two options when a transfer is late, and each breaks one property:

| Option | Keeps | Breaks |
| --- | --- | --- |
| Free the pages on timeout | Liveness: requests never hang, pages are always reclaimed | Isolation, a safety property (data never crosses requests): a late write lands in a new request's pages |
| Wait for the done notice | Isolation: pages are never reused while a write may land | Finality, a liveness property (everything eventually finishes): a lost notice hangs the request and its pages forever |

[Hao AI Lab's blog](https://haoailab.com/blogs/verifiable-llm-infra/) proves this is not a tuning problem. When delays have no upper bound, a slow write and a dead peer look exactly the same from Decode's side, so no rule based only on what Decode can see can guarantee both. veriserve's way out is to separate what happens to the **request** from what happens to its **pages**:

{{fig:pd-fix|PdLedger page states when a request ends or times out. Simplified: the ledger tracks six states in all, adding SHARED and DUP for prefix sharing.}}

On a timeout the request fails at once, so it never hangs, but its pages go to DRAINING instead of FREE. A page returns to FREE only with evidence that the write has stopped: Prefill confirms the write either never reached the NIC or has completed. Without that evidence the page is QUARANTINED and never reused, so a late write can only land in a page nobody uses. Version numbers on pages and transfers make a stale message from an earlier session harmless.

The cost is a few pages lost for good when something goes wrong. Across six paired runs against an unverified bypass baseline, [the blog](https://haoailab.com/blogs/verifiable-llm-infra/) measures PdLedger at +0.18% mean p50 TPOT (95% CI −0.32% to +0.68%). Note what is proven: the TLAPS proof covers safety only. Finality, the request failing fast instead of hanging, is runtime behavior outside the proof.

In upstream SGLang, the stale-message bugs have local fix PRs ([#48883](https://github.com/sgl-project/sglang/pull/48883), [#48889](https://github.com/sgl-project/sglang/pull/48889), [#48960](https://github.com/sgl-project/sglang/pull/48960), [#48979](https://github.com/sgl-project/sglang/pull/48979), [#48982](https://github.com/sgl-project/sglang/pull/48982)), but treating a timeout as "the remote side has stopped" is classed as architectural: no local patch escapes the dilemma ([veriserve case studies](https://github.com/hao-ai-lab/veriserve/tree/main/verification/pd-disagg/case-studies)).

## A worked example: modeling a real vLLM bug

To learn the workflow end to end, I modeled one bug from vstack's [verified bug list](https://docs.google.com/spreadsheets/d/1LSjmF0IlTFFDbeRYxs6vuNX2IQwLRkXLokIzgq2CyRc/edit?gid=0#gid=0): after a LoRA hot reload, new requests can silently run on old weights ([vLLM PR #67459](https://github.com/vllm-project/vllm/pull/67459)). The model is my own teaching version, written from that PR's code change; the vstack and veriserve repos do not publish one. It is about 80 lines of TLA+ ([LoraReload.tla](/assets/models/LoraReload.tla)), and every result below is from a real TLC run.

### The bug

{{fig:lora-ledgers|The front end, the queued request and the worker can each hold a different idea of which weights adapter A means.}}

vLLM keeps two records of which weights a LoRA adapter means: the front end's (name → weight path) and each worker's CPU cache of loaded weights. Every queued request carries the path that was current when it arrived. On a cache miss the worker loads from the request's path; on a hit it reuses the cached weights without checking. A hot reload switches both records to the new path, in five events:

1. Adapter A is at v1. Request r1 arrives carrying "A → v1" and waits in the queue.
2. A is hot-reloaded to v2. The worker cache and the front end both now say v2.
3. A request for adapter B runs. The CPU cache is full, so A is evicted.
4. r1 is scheduled. A is not cached, so it is loaded from r1's stale path: **the cache goes back to v1**.
5. New request r2 carries "A → v2", finds A in the cache, and **runs on v1 weights with no error**.

The victim (r2) is not the culprit (r1), which is why per-request assertions miss it. The bug also needs more adapters than the CPU cache holds; single-adapter setups are unaffected.

### Modeling it, step by step

1. **Write the spec. It is a design decision.** The obvious spec, "every request runs the version it arrived with", is wrong: the upstream fix runs r1 on v2 too, which is what a hot reload should mean. The rule I chose: once a request is done, the version it ran on is at least the version it arrived with. Old requests may get newer weights; new requests must never get older ones.
2. **Abstract.** Paths become version numbers. The cache holds one adapter and there are only two, A and B, which is enough to evict A. Tensors, GPUs and tensor parallelism are dropped. The hot reload is modeled as one atomic step, an assumption to revisit later. What remains is 7 variables and 4 actions: a request arrives, a hot reload, another adapter evicts A, a request runs.
3. **Model both versions of the code.** One switch selects the code before or after the patch. The fix: the worker remembers the latest hot-reload source and loads from it on a cache miss.
4. **Check it.** With 2 requests and 2 versions, TLC finds the violation in under a second. Its counterexample is exactly the five events above, as 7 states (the start plus 6 steps, because r2 arriving is its own step), and it is the shortest one possible.

{{fig:lora-trace|TLC's counterexample, plotted (numbers are states, not the five events above). At state 5 the cache holds v1 while the front end says v2; at state 7 r2 runs on v1 and the rule fails.}}

| Configuration | Distinct states checked | Result |
| --- | --- | --- |
| Original code, 2 requests, 2 versions | 89 | Rule violated, 7-state trace |
| Fixed code, 2 requests, 2 versions | 90 | Passes |
| Fixed code, 3 requests, 3 versions | 2,486 | Passes |

5. **Make sure the model is not lying.** A rule can pass because it is true, or because the model cannot even reach the bad state. Three checks tell them apart. The original code must fail; it does. A mutation, stopping the fixed code from recording the new source, must fail again; it does, so that part of the fix is load-bearing. A reachability witness, a claim that *should* fail ("no request that arrives after a reload ever finishes"), must fail; TLC breaks it in 4 states, so the interesting path is reachable.
6. **Strengthen it for any scale.** The fact that actually carries the proof: the worker's cached copy of A is either absent or the newest version. Two helper facts make it inductive: a reload always records its source, and no request holds a version from the future. This is the strengthening from the induction section, and its main line states the bug in one sentence: the worker cache must never be older than the front end. TLC confirms it in every reachable state with 3 requests and 3 versions, and on the original code it fails right after the first reload. A TLAPS proof would extend the result to any number of requests and versions; checking reachable states alone does not.

### What this does not prove

The atomic hot reload hides a real window between the worker reload and the front-end update. The model has one worker, while tensor parallelism gives each worker its own cache. [vstack's entry for this bug](https://docs.google.com/spreadsheets/d/1LSjmF0IlTFFDbeRYxs6vuNX2IQwLRkXLokIzgq2CyRc/edit?gid=0#gid=0) also notes that the fix does not cover a cache-key mismatch after rolling back to an earlier path. Splitting the hot reload into two steps is a good exercise.

## Why now: AI writes the specs, vstack keeps it honest

Formal methods are decades old. What changed is cost. Hand-written specs and proofs took months, while vLLM and SGLang merge new code every day. LLMs can now read a large codebase and produce specs and proofs quickly. Proof checkers are strict, so a fake proof is rejected: the failure mode is "could not prove it", not "hallucinated a proof".

The new failure mode is **reward hacking**. In [Hao AI Lab's](https://haoailab.com/blogs/verifiable-llm-infra/) words, when a checker finds a race, a naive coding agent "weakens the invariant, deletes the timeout branch from the model" instead of surfacing the real bug, until the checker says 0 errors.

[vstack](https://github.com/hao-ai-lab/vstack) is a plugin for Claude Code, Codex and Cursor built to block this. It adds no new solver; it uses TLC, Apalache, TLAPS and Z3. It forces the agent through gates:

| Gate | What it enforces | Where it showed up in the LoRA example |
| --- | --- | --- |
| Role isolation | Coordinator, worker and red-team agents are kept separate | I approved the rule and reviewed the results myself |
| Hash-pinned specs | SHA-256 locks the approved safety properties, so they cannot be quietly weakened | The rule never changed after step 1 |
| Line-anchored models | Every state variable and action maps to `file:line@commit` | Each action tied to the code in step 2 |
| Mutation and trace gates | The old bug must fail, the fix must pass, removing a guard must fail again, and logs from real runs must replay as valid model behaviors | Step 5 (without trace replay) |
| Proof and runtime checks | TLAPS proofs for critical state machines, with preconditions mirrored as runtime checks | The strengthened invariant in step 6 |

The blog summarizes the workflow as five steps (specification, abstraction, validation, verification, continuous checking). The repo splits it into nine stage skills:

{{fig:vstack-stages|vstack's stage skills. Orange: what the LoRA example walked through (S4 without trace replay; no TLAPS proof was run, so S7 is not marked).}}

You point it at one module with one safety property, for example `/vstack-mode verify that our RDMA KV cache lease manager never recycles an in-flight page on timeout.`, and it walks the agent through the stages.

Even with vstack, three steps stay with a human: approving the spec, judging whether a counterexample is real and reproducing it on hardware, and reviewing the assumption list at the end.

### Does every feature need its own model? Do I write the rules myself?

Both yes. Nobody models a whole engine. Pick a subsystem with a clear boundary and keep only the state the property needs. But draw the boundary where components interact, not along the directory tree: veriserve's ledger covers RDMA transfer, prefix sharing and decode attention in one state machine, because the PD bugs live at their seams.

Defining the rules is the step least safe to hand to an AI. You do not start from zero, though. Most bugs in [vstack's list](https://github.com/hao-ai-lab/vstack/blob/main/bugs/verified-bugs.csv) fall into five classes (the list also uses Progress and Invariance for a few):

| Class | Meaning | Example | Ask of a new feature |
| --- | --- | --- | --- |
| Isolation | Data never crosses requests | A KV page is never written by another request | Can it leak data? |
| Integrity | No stale or corrupt state | New requests never use old LoRA weights | Can it use stale state? |
| Finality | Requests terminate | An abort always takes effect | Can it hang? |
| Conservation | No leaked resources | Every page is accounted for | Can it leak resources? |
| Agreement | All ranks agree | Every DP rank enters the same collective | Can ranks diverge? |

## Where else it applies, and where it does not

Follow a request through an inference engine and almost every stop has a property worth checking:

| Component | Property | Tool |
| --- | --- | --- |
| Request lifecycle | An abort at any point frees every resource, and the request terminates | TLA+ |
| Scheduler admission and retraction | Memory stays within budget; chunked prefill covers the prompt exactly once | TLA+, Z3 |
| KV allocator | Used + free = total; no double free | TLA+ |
| Prefix cache | A node with lock_ref > 0 is never evicted; counts match the tree | TLA+ |
| Speculative decoding | Rejected tokens' KV is rolled back; the sampling distribution equals the target model's | TLA+, Lean |
| Constrained decoding | The token mask equals exactly the set the grammar allows | Automata, SMT |
| Streaming detokenization | Incremental chunks concatenate to the one-shot decode, UTF-8 boundaries included | Property tests |
| CUDA graph padding | Writes from padding rows never touch real requests' KV | Z3 |
| Parallel collectives | All ranks issue collectives in the same order; all-to-all is a permutation | TLA+, Z3 |
| Kernel indexing | Block tables and mask bounds never go out of range | Z3 |

These are not hypothetical. From vstack's verified bug list ([SGLang](https://github.com/hao-ai-lab/vstack/blob/main/bugs/verified-bugs.csv), [vLLM](https://docs.google.com/spreadsheets/d/1LSjmF0IlTFFDbeRYxs6vuNX2IQwLRkXLokIzgq2CyRc/edit?gid=0#gid=0)), each linked to its upstream fix or report:

- **SGLang, PD:** a reopened bootstrap room reset the in-flight RDMA counter, causing an early abort ACK and cross-request KV overwrite (68/68 reproductions on GB200; [PR #48889](https://github.com/sgl-project/sglang/pull/48889)).
- **SGLang, multi-rank scheduler:** with DP attention and the prefill delayer, DP ranks decided locally whether to defer prefill and entered different collectives; the server aborted ([issue #50136](https://github.com/sgl-project/sglang/issues/50136), [PR #50146](https://github.com/sgl-project/sglang/pull/50146)).
- **SGLang, DP attention abort path:** an abort and its request reach the owning rank over two unordered channels; an abort that arrived first was dropped, and 19 of 200 requests ran on ([issue #50137](https://github.com/sgl-project/sglang/issues/50137), [PR #50147](https://github.com/sgl-project/sglang/pull/50147)).
- **SGLang, CUDA graph padding:** padded rows wrote into reserved slot 0 and produced NaN logits ([PR #47013](https://github.com/sgl-project/sglang/pull/47013)).
- **vLLM, multimodal KV keys:** with prefix caching and the multimodal processor cache disabled, media items got per-process counter ids instead of content hashes, so an external KV store shared across processes answered a blue image with an earlier red image's content ([PR #67461](https://github.com/vllm-project/vllm/pull/67461)).

It is a poor fit for some things. Performance (latency, throughput) is out of scope. Floating point is hard: addition is not associative, so "bit-identical to the reference kernel" is often false by design, and proving error bounds is expensive. Anything without a precise definition, such as output quality, cannot be specified. And Python plus CUDA cannot be verified directly today, so the realistic setup is a design-level model plus runtime checks and trace replay to keep it honest.

**My rule of thumb: if you can state in one sentence what must never (or must eventually) happen, tests can't reach the orderings that break it, and a violation would be silent or costly, it is worth a model.**

## My takeaways: what we still need

At the design level, formal verification can largely handle the bugs testing is worst at: interleavings, lifecycles, resource accounting and index arithmetic. What I think is still missing:

1. **Specs are the product, and humans must own them.** The tool proves whatever you write down. Deciding what "correct" means was the hardest and least automatable step in my example. Inference engines would benefit from a shared, reviewed spec library organized by the classes above.
2. **The model-code gap needs CI, not a one-off proof.** We cannot verify Python or CUDA directly, so the model is a second artifact that drifts. Trace replay (production logs must be valid behaviors of the model) and runtime checks derived from the model's preconditions should run on every PR, like tests.
3. **Hardware assumptions are the new trust boundary.** Half of the PD story is RDMA semantics: what a one-sided write guarantees, whether it can be cancelled, what a completion actually certifies. Proofs are only as good as that assumption list, and much of it lives in provider-specific behavior rather than a spec you can model against.

## Sources

- Cloudflare, [Cross-request KV cache exposure in the GLM-5.3 Workers AI model, and our remediation with SGLang](https://blog.cloudflare.com/kv-cache-exposure-remediation/)
- LMSYS, [SGLang security update: improving request isolation](https://www.lmsys.org/blog/2026-10-26-cf-security/)
- Hao AI Lab, [Towards Verifiable LLM Infra](https://haoailab.com/blogs/verifiable-llm-infra/)
- [vstack](https://github.com/hao-ai-lab/vstack): the agent workflow and the verified bug lists ([SGLang, bugs/verified-bugs.csv](https://github.com/hao-ai-lab/vstack/blob/main/bugs/verified-bugs.csv); [vLLM, Verified AI Infra Bugs sheet](https://docs.google.com/spreadsheets/d/1LSjmF0IlTFFDbeRYxs6vuNX2IQwLRkXLokIzgq2CyRc/edit?gid=0#gid=0))
- [veriserve](https://github.com/hao-ai-lab/veriserve): PdLedger, its TLA+/TLAPS/Z3 models and the [PD case studies](https://github.com/hao-ai-lab/veriserve/tree/main/verification/pd-disagg/case-studies)
- [vLLM PR #67459](https://github.com/vllm-project/vllm/pull/67459): the LoRA hot-reload fix
- My model and config files: [LoraReload.tla](/assets/models/LoraReload.tla), [bug.cfg](/assets/models/bug.cfg), [fix.cfg](/assets/models/fix.cfg), [reach.cfg](/assets/models/reach.cfg), [kv_address.py](/assets/models/kv_address.py)
