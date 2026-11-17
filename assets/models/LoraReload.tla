---------------------------- MODULE LoraReload ----------------------------
(* Teaching model of vLLM bug: in-place LoRA reload lost after CPU-LRU eviction.
   Adapter A has versions 1..MaxVer (each version = one lora_path).
   Adapter B exists only to push A out of the CPU LoRA cache (max_cpu_loras = 1). *)
EXTENDS Naturals

CONSTANTS Reqs,      \* requests that use adapter A, e.g. {r1, r2}
          MaxVer,    \* how many paths A can be reloaded to, e.g. 2
          FIX        \* TRUE = model the patched worker_manager.py

VARIABLES reg,       \* front-end: version currently registered for A (serving.py lora_requests)
          cacheA,    \* worker CPU cache: version of A loaded, 0 = not cached
          cacheB,    \* worker CPU cache: is B loaded?
          inplaceSrc,\* patched worker only: newest in-place version of A, 0 = none
          status,    \* per request: "idle" | "queued" | "done"
          snap,      \* per request: version in the LoRARequest captured at admission
          used       \* per request: version whose weights actually ran

vars == <<reg, cacheA, cacheB, inplaceSrc, status, snap, used>>

Init ==
  /\ reg = 1 /\ cacheA = 1 /\ cacheB = FALSE      \* /load_lora_adapter A path v1
  /\ inplaceSrc = 0
  /\ status = [r \in Reqs |-> "idle"]
  /\ snap   = [r \in Reqs |-> 0]
  /\ used   = [r \in Reqs |-> 0]

\* A generate request arrives; it copies the current LoRARequest (path = reg).
Admit(r) ==
  /\ status[r] = "idle"
  /\ status' = [status EXCEPT ![r] = "queued"]
  /\ snap'   = [snap   EXCEPT ![r] = reg]
  /\ UNCHANGED <<reg, cacheA, cacheB, inplaceSrc, used>>

\* /load_lora_adapter A, new path, load_inplace=True.
\* Worker reloads A (evicting B since capacity is 1); front-end registry moves on.
Reload ==
  /\ reg < MaxVer
  /\ reg'    = reg + 1
  /\ cacheA' = reg + 1
  /\ cacheB' = FALSE
  /\ inplaceSrc' = IF FIX THEN reg + 1 ELSE inplaceSrc
  /\ UNCHANGED <<status, snap, used>>

\* Some other request on adapter B is scheduled: B is loaded, A is evicted (LRU).
UseB ==
  /\ ~cacheB
  /\ cacheB' = TRUE
  /\ cacheA' = 0
  /\ UNCHANGED <<reg, inplaceSrc, status, snap, used>>

\* Request r is scheduled; worker_manager.add_adapter(r's LoRARequest), load_inplace=False.
\*   if A not cached: load from the request's own path      (buggy)
\*                    or from the newest in-place source    (fixed)
\*   else:            just touch the cached copy
Run(r) ==
  /\ status[r] = "queued"
  /\ LET loadVer == IF FIX /\ inplaceSrc # 0 THEN inplaceSrc ELSE snap[r]
         ver     == IF cacheA = 0 THEN loadVer ELSE cacheA
     IN /\ cacheA' = ver
        /\ cacheB' = IF cacheA = 0 THEN FALSE ELSE cacheB
        /\ used'   = [used EXCEPT ![r] = ver]
  /\ status' = [status EXCEPT ![r] = "done"]
  /\ UNCHANGED <<reg, inplaceSrc, snap>>

Next == Reload \/ UseB \/ \E r \in Reqs : Admit(r) \/ Run(r)
Spec == Init /\ [][Next]_vars

\* Safety: a request never runs on weights OLDER than what was registered
\* when it was admitted.  (Running old requests on newer weights is allowed:
\* that is exactly the policy the upstream fix chose.)
NoStaleWeights == \A r \in Reqs : status[r] = "done" => used[r] >= snap[r]

\* Reachability witness: claims "no request admitted after a reload ever finishes".
\* TLC SHOULD violate this; if it doesn't, the model can't even reach the
\* interesting path and a clean NoStaleWeights result would be meaningless.
NeverRunNewVersion == \A r \in Reqs : ~(status[r] = "done" /\ snap[r] = MaxVer)

\* Strengthened invariant behind the fix: the worker never holds an older A than the registry.
FreshCache == /\ cacheA \in {0, reg}
              /\ (reg > 1 => inplaceSrc = reg)
              /\ \A r \in Reqs : snap[r] <= reg
=============================================================================
