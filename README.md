# RiverGuard AI

Private-network river monitoring with React, TypeScript, Plotly, FastAPI and SQLite. One Python service owns simulation, sensor data and durable Rill jobs. Synthetic data is labelled throughout. Node.js is needed to develop/build the frontend, not to run the friend ZIP.

## Windows setup

1. Clone this repository or extract its source ZIP. Install Python 3.14 with Python on PATH (tested with 3.14.2).
2. Double-click **Setup RiverGuard.cmd** once. This installs the verified `requirements-lock.txt` into `.venv`; installation needs internet.
3. For Rill, install Ollama and run `ollama pull llama3.2:3b` once. The model is separate from the ZIP. Monitoring works without Ollama; Rill requires its configured model.
4. Double-click **Start RiverGuard.cmd**. Keep the window open; Ctrl+C stops both services. The launcher checks ports and readiness before opening a single-use owner session.

Web app: port **8501**. ESP32 receiver: **8000**. If either is occupied, close the earlier launcher/application first. **Stop RiverGuard.cmd** stops this folder's background services while keeping saved data; a reply in progress becomes retryable after restart. If you sign out your only browser, stop/restart the launcher for a new owner link. Opening localhost without an existing session shows pairing rather than granting access.

For phones: same private Wi-Fi → Station settings → Create pairing code. Open the displayed laptop address on your phone and enter its eight-digit code within five minutes. Codes work once. Paired browsers share full access, including calibration and chats; revoke them in settings. Pairing controls access, but HTTP traffic is not encrypted. Do not expose these ports to the internet. Allow them only on a trusted private Windows network when needed.

## App destinations

- **Overview:** station/source, main status, four explained measurements, average/min–max trend and concise recent signals. Select alerts for details. Red/green arrows mean decrease/increase, not water safety.
- **Sensor setup:** Connect → Check signals → Calibrate → Verify. Upload authenticated firmware once; later enablement and calibration changes happen in the app. Saved settings and acknowledged device revisions are distinct. Stale, faulted and missing signal captures are blocked.
- **History & reports:** station/time filtering before cursor pagination, complete CSV exports, signal samples with counts, observation reports and experimental AI evaluation.
- **Ask Rill:** shared saved chats, rename/delete confirmation, retryable failures, partial replies and refresh recovery. Unsent drafts are tab-scoped. Refresh reconnects to existing jobs; Stop cancels generation. Retry captures fresh readings; Continue uses the original snapshot.

One simulation stream runs in the backend independently of browser sessions. Scenario changes preserve history; Reset & replay clears synthetic readings only. Pause stops new measurements, so their age continues to advance.

## Real sensors

Read `hardware/README.md`, `hardware/Tank-Assembly.md` and `output/pdf/RiverGuard-Friend-Setup.pdf` before connecting parts. Required: NodeMCU-32S, SEN0161-V2 pH, SEN0189 turbidity, DS18B20 and JSN-SR04T. TDS remains unsupported until its model is confirmed. Wiring includes the required voltage dividers.

Register the station in Sensor setup and download its private firmware configuration. Add Wi-Fi and receiver URL, then compile/upload using the pinned PlatformIO project in `hardware/firmware`. Both sensor POST and configuration GET require `Authorization: Bearer STATION_CREDENTIAL`. A credential accesses only its own station and cannot write calibration. Explicit credential rotation requires updating the firmware configuration. Never share `station_config.h` or credentials.

Raw signals stay separate from calibrated measurements. ADC counts never become NTU without known standards. Calibrate pH with two known buffers, turbidity with standards and ultrasonic level with the measured datum and actual sensor's usable range. Calibration revisions apply to the original sample. Chart lines and rise calculations break at revision changes. Firmware retries one pending packet in RAM with a stable sample ID; it is not durable offline logging. Actual wiring, board revision, NTP, sensor ranges and physical calibration still need hardware acceptance.

## Data and safety of interpretation

Storage: `data/riverguard.db`, overridden by `RIVERGUARD_DB`. Startup creates an SQLite backup before versioned transactional migration. Existing readings, calibration and chats are retained. Connections close explicitly. To move data, stop the launcher and copy the complete data folder, or use SQLite's backup API; do not copy only a live database file.

Current measurements sort by indexed UTC measurement time, then insertion ID. Delayed packets stay historical. Receipt age is separate. Timestamps over five seconds ahead are rejected; freshness spans five seconds ahead through 30 seconds old. Missing/faulted probes stay unavailable. Water warnings remain visible alongside faults and provisional calibration; stale warnings are last-known conditions. Rise requires five samples spanning eight seconds within one calibration revision.

Overview, alerts, reports and Rill share signal evaluation. Historical interpretation uses current station watch settings and exports include those settings. Graphs use bounded interval averages/min–max bands with missing-data gaps and preserved zoom. CSV streams a complete database snapshot and escapes formula prefixes in text while keeping measurements numeric. These research signals do not establish water safety, identify pollutants or predict floods.

## Local AI

Defaults: `RILL_PROVIDER=ollama`, `RILL_MODEL=llama3.2:3b`, `RILL_OLLAMA_URL=http://127.0.0.1:11434`. Context: 4,096 tokens; answer budget: 256 tokens. Current readings and grounding instructions take priority over older chat. One generation runs at a time, with up to three queued requests across conversations. Settings names the actual provider and host, including remote Ollama destinations.

To use a different local model, install it with Ollama on the laptop running
RiverGuard, then open **Settings → Rill’s AI connection → Refresh installed
models**. Choose it under **Installed local model**, click **Use this model**,
then **Prepare model**. The choice is saved across restarts; no source edits or
firmware upload are needed. A saved choice takes precedence over the initial
`RILL_MODEL` default. Switching waits until all replies and model preparation
finish. Existing chats are retained; Continue keeps the original model, while
Retry uses the selected model with a fresh reading snapshot.

For Qwen 3.5 4B, run `ollama pull qwen3.5:4b` first. Its download is about
3.4 GB; allow additional free storage and runtime memory. The ZIP does not
include model weights. The selector only accepts installed local chat models,
including checking aliases for cloud routing. It never downloads or changes
providers automatically. Different models require testing on your river
questions; selecting a larger model does not guarantee faster or better answers.
Thinking-capable models keep their default reasoning behavior and may take
longer or need Continue/Retry if the reply budget is exhausted.

Opening Rill prepares the selected model in the background without sending
questions or readings. Prepare model does the same explicitly. Ollama keeps it
loaded for up to 15 minutes after use; this removes cold loading when possible,
but CPU generation can still take tens of seconds. The same grounding, context
and answer budget remain in place. Streaming text is persisted in short batches
instead of one transaction per token; partial replies and cancellation remain
durable. Each job stores its actual model and timing counters for diagnosis.

Allocation failures, missing models, timeouts, interrupted replies and token limits have explicit recovery states. No automatic smaller-model/cloud fallback occurs. Explicit cloud configuration remains available with `RILL_PROVIDER=gemini`, `GEMINI_API_KEY` and optional `RILL_CLOUD_MODEL`; it sends selected readings and conversation to that provider. Keys stay server-side and quota failures preserve questions.

New replies receive basic consistency checks against the captured readings. Known contradictory numbers, threshold comparisons or unsupported safety claims keep the reply incomplete; its unverified draft stays saved and collapsed, with a fresh retry available. These conservative checks are not proof that every sentence is correct. They never substitute a preset answer or another provider.

Run `python benchmark_rill_quality.py` for the 20-question benchmark. Evidence includes first-token/completion timing and memory observations; human answer review is separate. Allocation failures are blocked results, never quality passes. Reply speed depends on hardware and available memory. This laptop's measured local replies did not reach a few seconds; see `docs/audit/FULL-AUDIT.md` for recorded limitations and outstanding findings.

## Development, review and packaging

Frontend: run `npm ci`, `npm run build` and `npm test` in `frontend`. Built `frontend/dist` is included in the friend ZIP. Run `.venv\Scripts\python -m pytest -q` for backend regressions.

Isolated review: `.venv\Scripts\python serve.py --web-port 8504 --sensor-port 8001 --db output/review.db`. `--no-browser` writes a protected, single-use owner link beside that database; it expires in two minutes and is removed on exit. Never share it. The ordinary launcher serves the replacement after release checks. Prior Streamlit source is retained for reference/rollback, not used by the new UI.

The consolidated audit and component reviews are under `docs/audit/`. Raw review evidence and the older development checklist are not distributed. Physical sensors and a real phone/virtual keyboard are separate acceptance checks, not implied by browser emulation. `package_app.py` produces a clean ZIP with compiled frontend, source, locked dependencies and hardware guides, excluding databases, personal chats, credentials, local environments and review artifacts.


## Standalone Android app

Download the standalone APK from [GitHub Releases](https://github.com/ChrisTheRealDev/RiverGuard/releases).
It bundles the dashboard and uses SQLite on the phone: no laptop, Python, AI
model or internet server is needed. Demo readings are clearly labelled synthetic.
Real sensors connect directly to the phone on the same private Wi-Fi using the
in-app receiver. Reception works only while the app is visible and enabled.

AI chat is not included in this phone build. Rill provides explicitly rule-based
reading notes. Read the [standalone guide](docs/STANDALONE-ANDROID.md) for sensor
setup, initial firmware flashing, local data and update limitations.

The earlier 1.x APK was a laptop companion. Uninstall that old companion before
installing the first standalone APK because the signing identity changed. Future
standalone updates use a persistent release key; do not uninstall them to update,
since that erases local readings/calibration. Export before any unavoidable
uninstall. Existing laptop data is not automatically migrated to the phone.

Based on the Android companion from
[alamien060512-alt/RiverGuard-Android](https://github.com/alamien060512-alt/RiverGuard-Android)
(revision a42f293), with its MIT license retained in `mobile/LICENSE`.

## Snapshot and known issues

This repository includes the current app, compiled frontend, firmware, hardware
and tank guides, Android companion source and the 22 October 2026 audit. The audit
records 31 findings, including three high-priority issues, which remain unfixed.
Start with `docs/audit/FULL-AUDIT.md`. Personal readings, conversations,
credentials, model weights and local logs are excluded. Fresh installations
create their own local data.
