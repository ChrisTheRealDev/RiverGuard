# What actually runs?

[Home](Home.md) · Next: [Backend](backend.md)

There are two HTTP doors into one RiverGuard Python process. The browser uses the web application on port 8501. The ESP32 sends packets to the receiver on port 8000. Both use the same SQLite database. Ollama, when configured locally, runs separately and answers inference requests from Python.

```text
Browser → ui_api.py :8501 → data_service.py → SQLite
                 │                ↑
                 ├─ simulation ── core.save()
                 └─ ChatService → Ollama / explicit cloud provider

ESP32 → api.py :8000 → station_setup.calibrate() → core.save()
```

The arrows show responsibility, not separate deployable services. [serve.py](../serve.py), `run()` at line 55, constructs two Uvicorn servers as asynchronous tasks. It checks both health endpoints for the current instance ID before declaring startup successful. A port occupied by an older app must not accidentally count as this launch being ready.

## Ownership follows the lifetime of the process

Opening three browser tabs does not create three simulations. The lifespan inside [ui_api.py](../ui_api.py), `create_app()` at line 150, starts one `Simulation` and one `ChatService`. Closing a tab does not stop sampling or cancel a persisted chat job. Those services stop when the backend stops.

This matters on a laptop: the browser is a replaceable view, while the backend owns the work. If the browser disappears during a reply, reopening it should observe the same job. If Python disappears, startup marks interrupted jobs as failed and retryable. Those two failures need different recovery behavior.

The one-process arrangement also creates a constraint: launch one supervisor for a database. This is not a deployment recipe for several web workers each starting their own simulation and chat worker. Revisit ownership and coordination before adding replicas.

## Storage is shared; credentials are not

[core.py](../core.py), `connect()` at line 100, selects the database from `RIVERGUARD_DB`, creates its directory, enables WAL and applies the core schema migrations. The ordinary path is `data/riverguard.db`. Security, chat and simulation initialize their own supporting tables through that connection layer; the entire schema does not live in one function.

Browser sessions and sensor tokens enter through different checks in [security.py](../security.py). A paired browser has full app access. A sensor token is bound to one station and may submit samples and retrieve that station's configuration. It cannot grant itself permission to change calibration.

The local owner link is single-use and short-lived. Pairing codes authorize other trusted browsers. CSRF and origin checks protect browser mutations, and host checks limit accepted hostnames. These are access controls on a private-network HTTP application; pairing itself does not encrypt traffic.

## Follow a late packet

Suppose a sample measured at 10:00 arrives at 10:04, after a sample measured at 10:03. The laptop records both measurement and receipt time. The newest arrival is evidence of a connection, but the 10:03 measurement remains the latest known river sample. Ordering by receipt time would silently turn transport delay into a false change in the river.

Calibration revision travels with the packet for the same reason. A delayed packet uses the settings acknowledged when it was sampled. It does not borrow whichever settings happen to exist when the network recovers.

These rules connect the [backend](backend.md), [hardware](hardware.md) and [Rill](rill-ai.md) pages. Each subsystem needs the same account of which station, which time and which calibration it is discussing.
