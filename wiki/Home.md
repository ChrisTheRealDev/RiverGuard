# RiverGuard, from packet to picture

RiverGuard turns four imperfect sensor signals into a picture someone can inspect. A station measures acidity, cloudiness, temperature and water height. The laptop keeps the evidence, applies calibration, checks a few explicit conditions and draws the result. Rill can explain that captured picture in words. None of those steps turns four sensors into a water-safety certificate.

The useful starting point is one sample. It has a measurement time, a source, a station ID, raw signals and a calibration revision. Follow those fields through the system and most of the architecture becomes understandable. Lose one of them and apparently simple features become misleading: a delayed packet can look current, an old calibration can look like a rising river, or synthetic data can look like field evidence.

## Read a path, then follow the code

| Question | Start here |
|---|---|
| What runs when I double-click the launcher? | [Architecture](architecture.md) |
| How does a packet become a status or chart? | [Backend and evidence](backend.md) |
| How does the browser stay consistent as requests arrive? | [Frontend](frontend.md) |
| How should colors, spacing and type stay consistent? | [Style system](style-system.md) |
| What happens after I ask Rill a question? | [Rill and local AI](rill-ai.md) |
| What must happen before a physical probe is useful? | [Hardware](hardware.md) |
| Why keep this design small and opinionated? | [Decisions and tradeoffs](decisions.md) |

For installation and day-to-day commands, use the [README](../README.md). For changes to the project, read [AGENTS.md](../AGENTS.md). This wiki explains the reasoning behind the implementation; it is not a second installation manual.

## A small experiment

Start the isolated review server from the repository root:

```powershell
.venv\Scripts\python serve.py --web-port 8504 --sensor-port 8001 --db output/review.db --no-browser
```

Open the protected owner link printed by the launcher before its two-minute expiry. Choose Demo, watch the measurements, and pause the simulation in Settings. The numbers remain visible while their age increases. After the freshness window expires, the status changes. That is intentional: the system still knows the last measurement, but it no longer knows current conditions.

Now select a different chart metric. Its line and legend change color together; the raw measurements do not change. This separates presentation from evidence. Many of RiverGuard's design choices are versions of that same separation.

## Keep this wiki useful

These pages describe version 2.3.0. Source references name a function and its current line so a reader can locate the implementation; line numbers will move. When behavior changes, update its explanation and example in the same change. Link to the existing hardware guide and setup instructions instead of copying them into more places.

Each page should answer a concrete question, show a small example and name the code responsible. If an explanation needs an unverified assumption, label it. Observed behavior, design rationale and physical validation are different kinds of evidence.
