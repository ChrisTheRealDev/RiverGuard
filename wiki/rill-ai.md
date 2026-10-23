# A reply is a job with a captured sample

[Home](Home.md) · [Frontend](frontend.md) · Next: [Hardware](hardware.md)

Imagine asking “Is the water rising?” and closing the browser halfway through the answer. If the browser owned generation, the reply would vanish or restart. RiverGuard instead stores the question, context and job on the server. The browser observes that work.

## The durable path

[chat_service.py](../chat_service.py), `ChatService.submit()` at line 313, checks the conversation revision and request ID inside a transaction. Repeating the same request returns its existing job. Reusing an ID for different work is a conflict. There can be one active job per conversation and four active jobs overall: one generation and up to three waiting.

The job stores the selected station snapshot, recent chat, actual provider/model, question and turn identity. `_work()` at line 463 reserves queued work and runs one generation at a time. `_generate()` at line 491 persists streaming text in small batches. This keeps reconnectable progress without a transaction for every token. An abrupt process crash can still lose the latest unflushed fragment.

`events()` at line 549 sends complete persisted job snapshots with sequence numbers. A reconnect can skip missed events because the next snapshot contains the accumulated text. Refreshing the browser only resumes observation. Backend startup, by contrast, identifies previously active jobs as interrupted and preserves them as retryable failures.

## Retry and Continue answer different questions

Retry takes a fresh reading snapshot and uses the currently selected model. Continue retains the original model, captured measurements and partial answer. Their age is refreshed, so a continued answer may need to say its data is now old. A draft rejected for unsupported claims cannot simply be continued; it needs a fresh retry.

This distinction prevents a paragraph from silently combining two different moments in the river. It also makes recovery understandable: a failed request does not erase the question, and Stop cancels generation without pretending that the partial answer was completed.

## Give the model explicit facts

[rill_ai.py](../rill_ai.py), `context_data()` at line 105, derives context from the same measurement and status logic used by the dashboard. It includes missing sensors, provisional calibration, captured time, thresholds and the observed rise when available. `_payload()` at line 153 builds the local prompt with authoritative comparisons, a bounded recent history and the user's question.

For instance, “35 cm is below a 70 cm watch setting” is calculated before inference. The model should explain that fact, not discover the comparison by guessing. A height in cm and a speed in cm/min are separate facts. Recent chat cannot override the captured sample.

The local default is Ollama at loopback with `llama3.2:3b`. The local payload uses a 4,096-token context and 256-token answer budget. The configured model can be changed through Settings after installation; the selected value persists in SQLite. Warmup sends no river question or readings. It can reduce cold-start delay but cannot guarantee fast CPU generation.

## Verification is a filter, not another oracle

[rill_verification.py](../rill_verification.py), `verify_reply()` at line 60, checks supported numeric claims, unit comparisons, freshness/provisional disclosures and known unsupported safety conclusions. A contradictory draft becomes incomplete and remains available as unverified text. The system does not replace it with a canned answer or silently switch providers.

Passing these checks means those checks did not find a problem. It does not prove every sentence true. The patterns can reject ambiguous wording and miss claims outside their scope. [Verification tests](../tests/test_rill_verification.py) and the [quality benchmark](../benchmark_rill_quality.py) are evidence about specific cases, not a claim of general reliability.

## Local describes a destination

`provider_info()` at line 28 distinguishes loopback Ollama, remote Ollama and explicitly configured Gemini. A remote Ollama URL sends context off the laptop even though the software is called Ollama. Cloud mode sends selected readings and conversation to its provider. Credentials stay server-side. There is no automatic local-to-cloud fallback when memory, network or quota limits are hit.

When investigating a slow or failed reply, inspect its actual model, state, error and timing counters first. Monitoring and calibration do not depend on an available language model.
