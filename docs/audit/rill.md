> Audit snapshot, 22 October 2026. Raw databases, personal transcripts, screenshots, logs and session material are excluded. Findings remain unfixed.

# Rill audit — 22 October 2026

Audit only. No application changes, production database writes, downloads, deletions, browser control, or real model calls were performed. Root owns browser acceptance and the wider dashboard audit. This review read the current backend and frontend, rather than relying on the earlier handoff review.

Checks used pure verifier/payload examples, the actual frontend state helpers, an extracted copy of the existing request-ID function, an HTTP MockTransport catalog, and a temporary SQLite database with an injected one-off worker database error. These are reproductions of code paths, not claims that a real model generated the hypothetical bad answers below. No full suite was run alongside root's checks.

## Findings

### R01 — P1: Another browser's failed reply can inherit an older reply's verification and retry target

- **Location:** `frontend/src/RillChat.tsx:34`, `:37`, `:42`, `:60`, `:63`; `frontend/src/chatState.ts:45`.
- **Trigger:** Browser A retains completed job A. Browser B asks another question in the same chat and gets unverified failure B. A's conversation poll receives B's failure, but A's GET for job B fails or is delayed.
- **Impact:** `replyFailure()` correctly selects failure B, but `job?.verification` and `job?.id` still take precedence over B's verification and ID. B's unverified draft can render expanded, Continue can be offered, the model label can name A, and Retry/Continue submit A's job ID. The backend rejects the stale action, but the display has already bypassed the intended unverified-draft treatment. The failed metadata GET is swallowed and has no timed retry, so the mismatch can persist.
- **Evidence:** Replayed canonical A + user B + failed B through the real helper and current derived expressions: `failureJob=B`, `renderedUnverified=false`, `renderedContinue=true`, `submittedJobId=A`, although B had `passed=false, can_continue=false`.
- **Confidence:** High; deterministic state reproduction. Browser network-fault reproduction would strengthen UI evidence.
- **Recommendation:** Bind all failure properties and actions to one attempt ID. Only use job metadata when it matches the displayed failure; otherwise use canonical failure metadata and fetch the matching job with visible recovery. Test the entire derived view/action model, not only `replyFailure()` in isolation.

### R02 — P1: Safety/forecast assertion variants bypass the completion verifier

- **Location:** `rill_verification.py:70–76`, `:141–153`; promotion at `chat_service.py:523–528`.
- **Trigger:** The provider emits a prohibited conclusion using wording outside the small regex vocabulary.
- **Impact:** The guard would promote that hypothetical output to a normal completed answer. The documented 'conservative checks, not a truth proof' limitation is accurate, but the uncovered examples directly contradict the app's stated drinking-safety and flood-forecast boundaries.
- **Evidence:** A normal synthetic context accepted both `In this demo, the river is drinkable.` and `In this demo, no flooding is expected.` with `passed=true`, no reasons, and `can_continue=true`.
- **Confidence:** High for the verifier gap; no claim about frequency in real model output.
- **Recommendation:** Expand explicit prohibited-conclusion tests and classification beyond the current narrow wording. Keep the AI limitation visible; do not describe a passed guard as proof of correctness. Include these paraphrases in grounded quality acceptance for every newly selected model.

### R03 — P2: Reference/threshold values are accepted as invented measured values

- **Location:** `rill_verification.py:91–125`, `:141–152`.
- **Trigger:** A reply uses a number that belongs to the allowlist for a unit but assigns it the wrong factual role.
- **Impact:** Values for neutral pH, reference limits, or configured warning heights can be presented as actual measurements. Role checking is implemented for observed rise speed, but not consistently for pH, temperature, cloudiness, or height.
- **Evidence:** For actual pH 7.2, temperature 27.4°C and height 35cm, all these hypothetical replies passed: `the latest pH is 14`, `the measured temperature is 20 °C`, and `the current water level is 100 cm` (each prefixed `In this demo,`).
- **Confidence:** High; pure verifier reproduction.
- **Recommendation:** Distinguish measurement, reference, threshold and change claims per sensor. Match measurement assertions against the corresponding captured field, rather than the union of legitimate numbers for that unit.

### R04 — P2: A long generation is checked against freshness at generation start

- **Location:** `chat_service.py:508`, `:523`; `rill_ai.py:138–151`; final transcript rendering `frontend/src/RillChat.tsx:57`.
- **Trigger:** A sample is fresh when generation starts, but the model takes enough time that the sample becomes more than 30 seconds old before completion.
- **Impact:** Completion verification uses the start-time context, so a reply describing 'current' conditions can pass after its snapshot is stale. Completed transcript messages also omit the captured sample time that is visible during generation. This matters for the previously observed 52-second reply time.
- **Evidence:** With a timestamp 65 seconds ago but the stored start flag `stale=false`, `In this demo, the current temperature is 27.4 °C.` passed. Running the same check through `refreshed_context()` first correctly rejected it for missing the old-reading warning.
- **Confidence:** High for the timestamp/flag gap; actual model latency determines exposure.
- **Recommendation:** Re-evaluate age at completion and retain captured-reading time/age alongside completed answers. Preserve the original snapshot for Continue, but label its age accurately instead of silently describing it as current.

### R05 — P2: One worker database exception can strand all subsequent replies

- **Location:** `chat_service.py:463–489`, `:544–547`; readiness checks `:177–180`.
- **Trigger:** A transient SQLite exception occurs in the worker's queue reservation or escapes generation cleanup/metrics persistence.
- **Impact:** The sole worker task exits. `_started` remains true, so requests can still be accepted, jobs remain queued, and model changes remain locked by those jobs. No worker-health check or restart/failure transition makes this actionable to users.
- **Evidence:** In a temporary SQLite database, injected a single `sqlite3.OperationalError` only on the worker's next DB access. Result: `worker_done=true`, `job_state=queued`, `service_still_accepts_requests=true`. No real provider was invoked.
- **Confidence:** High; isolated lifecycle reproduction.
- **Recommendation:** Supervise worker liveness, report an actionable unavailable state, and handle recoverable storage failures without losing the durable job lifecycle. Add a one-off fault-injection test that verifies subsequent requests do not silently queue forever.

### R06 — P2: Unknown-result submission IDs change after polling observes the accepted job

- **Location:** `frontend/src/RillChat.tsx:37`, `:73`; backend idempotency validation `chat_service.py:325–328`.
- **Trigger:** A question POST is accepted but its response is lost. The original question remains in the draft/request store. Polling later observes the accepted attempt as job B instead of preceding job A. After B finishes, the user resends the unchanged retained draft.
- **Impact:** `submissionId()` includes the mutable `parent` job ID even for a new question. The retry now fingerprints B rather than A, discards the saved request identity, and can append a duplicate question/reply instead of resolving the original unknown-result submission.
- **Evidence:** Executed the existing extracted function with fake session storage: same chat/question/mode and parent A reused request `1`; after only the observed parent changed to B, the function generated request `2`.
- **Confidence:** High for request-identity instability; the complete lost-POST browser sequence remains untested in this audit.
- **Recommendation:** Bind a pending question's request identity to its original submission intent until acknowledgement/reconciliation. Do not derive a new-question identity from whichever job polling happens to show. Add a lost-response + polling + resubmit regression.

### R07 — P2: The compact model prompt drops known per-sensor changes and their interval

- **Location:** `rill_ai.py:126–129`, `:153–164`; `rill_verification.py:17–57`.
- **Trigger:** Ask a natural trend question such as 'How did pH change?' or 'Is the water getting cloudier?'
- **Impact:** `context_data()` computes changes and sample intervals, but the compact payload sends only `authoritative_facts()`. That text includes latest values and water-rise speed, not the pH/cloudiness/temperature deltas or previous interval. The model is instructed not to use earlier chat as station truth, so it cannot reliably answer these otherwise-supported questions from the evidence actually supplied.
- **Evidence:** Built a payload with `change_since_previous_sample.ph=0.73` and `previous_sample_interval_seconds=5`; neither the delta nor interval appeared in the system facts, although both existed in the context object.
- **Confidence:** High; pure payload inspection.
- **Recommendation:** Include concise, explicitly bounded per-sensor change facts and their real interval in the authoritative prompt. Keep height and speed distinctions intact.

### R08 — P2: Repeated Continue operations can exceed the fixed context budget

- **Location:** `rill_ai.py:154`, `:167–169`; prefix growth `chat_service.py:372–373`, `:397–398`.
- **Trigger:** Continue an unfinished reply repeatedly, accumulating an increasingly long prefix.
- **Impact:** Each generation resends the complete accumulated prefix while retaining a fixed 4,096-token context. Only four older history messages are clipped by characters; the continuation has no budget check. Provider-dependent truncation or failure can then defeat the plan's promise to protect grounding and safety context.
- **Evidence:** `_payload()` accepted a 20,000-word continuation into a roughly 102,000-character prompt while still setting `num_ctx=4096`. This is a boundary reproduction, not an observed normal-length conversation.
- **Confidence:** High for the unbounded payload; exact provider overflow behavior was not exercised.
- **Recommendation:** Enforce a model-aware input budget that protects system/current-reading facts first, trims history next, and limits or summarizes continuation safely. Explicitly reject an impossible continuation rather than silently relying on provider truncation.

### R09 — P3: General educational questions can be rejected for unrelated station warnings

- **Location:** `rill_verification.py:77–86`; prompt policy `rill_ai.py:158`.
- **Trigger:** Ask a general definition while a real station's readings are stale and unverified.
- **Impact:** A correct definition without any station-specific assertion is marked unverified for omitting stale/provisional disclaimers. This can make ordinary river questions feel unreliable and unnecessarily technical.
- **Evidence:** `pH describes how acidic or alkaline water is; 7 is neutral.` answering `What does pH mean?` failed with both 'treats old captured readings as current conditions' and 'omits ... provisional', despite describing no captured condition.
- **Confidence:** High; pure verifier reproduction. This is a quality/policy-scoping issue, not a storage or access-control issue.
- **Recommendation:** Apply freshness/calibration warnings to station-specific factual claims; retain concise station metadata in the UI so generic explanations do not need irrelevant caveats.

### R10 — P3: A single broken/stale catalog entry disables the entire installed-model selector

- **Location:** `rill_models.py:61–85`, `:98–100`; API `ui_api.py:215–223`.
- **Trigger:** A model disappears between `/api/tags` and its `/api/show`, or one otherwise unrelated installed entry returns malformed/error metadata.
- **Impact:** Catalog construction aborts instead of returning the other validated installed models. Settings then cannot use or prepare an unaffected model until the bad entry condition is resolved.
- **Evidence:** HTTP MockTransport returned one valid completion model and a second model whose `/api/show` returned 404. `catalog()` rejected the whole list with the generic local-model-list error.
- **Confidence:** High; isolated HTTP reproduction, with no actual Ollama request.
- **Recommendation:** Isolate per-entry metadata failures, retain validated entries and surface a partial-refresh warning, while continuing to reject remote/cloud aliases conservatively.

### R11 — P3: Another paired browser's model selection is not propagated to Rill's selected-model hint

- **Location:** `frontend/src/App.tsx:18`, `:20`; `frontend/src/ModelSettings.tsx:12–14`; `frontend/src/RillChat.tsx:63`.
- **Trigger:** Browser B changes the selected model while A stays open. A can receive the new selection in its Settings inventory, but does not execute its own `onChange` callback.
- **Impact:** A's cached session provider can remain the old model, so 'Fresh retry uses ...' may name the wrong model. The backend correctly uses the persisted selection, and active-job metadata subsequently shows the real model; this is a misleading pre-action hint rather than a provider-switching defect.
- **Confidence:** High from the state-update paths; paired-browser UI reproduction was left to root.
- **Recommendation:** Propagate authoritative model-selection revisions into the shared provider/session view, including remote changes, without remounting chats or discarding drafts.

### R12 — P2: Continue eligibility does not match the saved partial or backend lifecycle

- **Location:** `frontend/src/RillChat.tsx:43`, `:63`; supported server states/requirements `chat_service.py:349–351`, `:368–373`.
- **Trigger A:** Stop after receiving valid partial text, or encounter a connection/timeout failure after text was saved. These attempts are cancelled/failed rather than incomplete.
- **Impact A:** The backend supports continuation of their saved snapshot, but the UI only offers Continue for state `incomplete`; users must regenerate instead. The stopped-reply message itself says 'continue or retry'.
- **Trigger B:** A length-limited stream ends before producing visible answer text (for example a thinking-only response).
- **Impact B:** State `incomplete` can offer Continue despite an empty partial. The backend then rejects that action because it requires saved text and context.
- **Evidence:** Replayed the existing UI predicate: cancelled + nonempty valid partial → Continue false; failed + nonempty partial → false; incomplete + empty partial + no failed verification → true.
- **Confidence:** High; source and deterministic predicate reproduction, no model call.
- **Recommendation:** Base continuation eligibility on the matching terminal attempt, a nonempty saved partial, valid original snapshot availability and `can_continue`, covering the backend's supported terminal states. Keep unverified drafts blocked and legacy missing-snapshot failures retry-only.

## Source areas checked without an additional confirmed blocker

- Durable server-owned messages, expected-revision checks, queue bound, model selection while idle, fresh Retry versus snapshot/model-pinned Continue, local alias validation before sending readings, nonblocking preparation, and no automatic cloud fallback.
- Completed reply handoff/exact-turn acknowledgement, stale sequence/revision suppression, current keyboard composer mounting, nested Escape/focus trap structure, explicit destructive-chat confirmation, local Markdown image suppression, and external-link `noreferrer` handling.
- No new claim that a particular model is faster or equally good: the chosen Qwen model still needs actual laptop grounding/performance acceptance. No model was installed or benchmarked during this audit.
- Screen-reader announcements, real phone virtual keyboards, prolonged browser network transitions and provider-specific overflow behavior were not directly exercised here. Root's live browser checks and the separate physical acceptance step remain necessary.

## Suggested repair order for a later authorized fix pass

1. Bind failed-attempt display/actions to the same job and expand the safety/measurement assertion acceptance cases (R01–R03).
2. Correct completion-age handling and worker liveness reporting (R04–R05).
3. Repair unknown-result request reconciliation, continuation eligibility and compact trend evidence (R06–R07, R12).
4. Enforce continuation budgets and refine educational-question policy/catalog/model metadata consistency (R08–R11).

No fixes were made in this audit.
