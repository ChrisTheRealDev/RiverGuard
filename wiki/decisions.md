# Keep the reasons next to the code

[Home](Home.md) · [Hardware](hardware.md)

These are working rationales reconstructed from the current code and repository conventions, not a record of every original author's intent. They explain the tradeoffs to preserve when changing RiverGuard, and the conditions that could justify revisiting them.

## One supervisor

A laptop owner needs one start command and one stop command. The [supervisor](../serve.py) can check both HTTP services, start one simulation and shut down one chat worker together. Splitting those responsibilities into independently managed processes would add coordination and recovery work before providing an obvious benefit to this deployment.

The cost is shared fate: a supervisor failure affects both services. If the receiver must remain available during independent UI deployments, reconsider that boundary and explicitly assign worker ownership.

## SQLite and explicit transactions

Measurements, settings, sessions and chat jobs live with the laptop. [SQLite connections](../core.py) avoid requiring a separate database service during installation. Transactions support consistent overview snapshots, revision checks and idempotent chat submission. WAL allows useful reader/writer concurrency, but does not create unlimited write capacity or a distributed database.

For this deployment, an additional database server would increase operations work. Multiple independent writers or remote database administration could change that calculation. Back up with SQLite's backup mechanism or stop the app before copying the complete data folder; a live main database file alone may omit WAL contents.

## Raw evidence survives interpretation

Keeping only the calculated NTU would be compact, but it would conceal which voltage and standards produced the value. Keeping raw signals, calibration identity and health alongside it makes the number inspectable. A later calibration must not rewrite the original observation.

Watch thresholds are different: historical signal checks use current settings. The report includes those settings so someone can understand the interpretation. This deliberately separates “what was measured” from “which checks we apply now.”

## Small pure tests before a larger testing stack

The frontend's most consequential bugs often involve scope, revisions and stale responses. Small pure state functions let Node's built-in tests exercise those cases without introducing a component runner. [AGENTS.md](../AGENTS.md) requires asking before adding test-only dependencies.

This leaves a gap: focus order, clipping and animation exits require browser verification. If repeated DOM-specific failures make manual checks inadequate, propose a focused testing tool and the cases it would protect. Do not claim that passing state tests proves the whole interface accessible.

## One dark theme with shared tokens

Dark mode is the project's current product constraint. A second theme would double many color and visual checks. Shared metric, status, spacing and type tokens make the existing interface easier to tune consistently. The current migration is partial; changing every legacy literal at once would produce a large review surface for a cosmetic goal.

Metric colors identify acidity, cloudiness, temperature and height. Status text and status colors communicate what a check found. Stronger accents should make those roles easier to see while keeping labels legible and reduced-motion behavior intact.

## Local inference by default, explicit recovery

The default model destination keeps questions and readings on the laptop. That choice costs memory and latency. RiverGuard reports allocation failures and keeps unfinished work instead of secretly choosing a smaller model or sending it to a cloud provider.

The user can explicitly configure another destination. [Rill's provider description](rill-ai.md) must then describe where the data goes. Warmup and queueing improve operation, but they do not remove the need to measure speed and review answer quality on the actual hardware.

## Be precise about what a check means

A synthetic anomaly detector can identify departure from its training distribution. It cannot identify a pollutant. A prototype height threshold can flag a measurement. It cannot establish a flood forecast. A reply verifier can catch known contradictions. It cannot certify every sentence.

Preserving those distinctions is part of the data model, not just a disclaimer added after rendering. When adding a feature, ask which evidence supports its strongest user-visible claim, then make the missing or uncertain case explicit.
