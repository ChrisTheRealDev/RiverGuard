# V2 platform contract

The fresh shared React UI lives in v2/frontend. Android project and Capacitor
package live in v2/mobile (app ID com.riverguard.v2). Build frontend assets to
v2/mobile/web. Do not change the existing app, launchers, databases or releases.

Use the existing standalone phone API SHAPES (mobile/offline/bridge.ts) as the
platform boundary, not its old UI. Copy the validated pure domain implementation
and declarations to v2/frontend/src/domain.js and domain.d.ts, with conformance
tests. New UI imports its shared rules. Native plugin name RiverGuardV2.

The platform object offers getState, setState, registerStation, listStations,
getSettings, saveSettings, listReadings, appendDemo, setReceiver, exportData,
saveText and saveGuide with the existing phone signatures. Server counterpart:
POST /api/v2/phone/{method}, body is each method's input. listStations and
saveGuide take {}. Native operations keep their existing document-picker behavior.
Add getMonitoring() -> {running,enabled,notificationsAllowed,error?}; Android
setReceiver now starts/stops user-enabled background monitoring. Browser returns
running/enabled from server and notificationsAllowed:false, explaining laptop
monitoring requires the service running. Histories remain separate.

Web authentication: GET /api/v2/session returns {authenticated,csrf?}; POST
/api/v2/bootstrap {token} establishes loopback owner session, POST /api/v2/pair
{code} establishes paired session. All phone operations require browser auth,
same-origin checks and X-CSRF-Token. Reuse existing security helpers with an
isolated V2 database. No permissive CORS, no unauthenticated calibration writes.
Native bundled UI uses local native bridge and needs no browser pairing.
Frontend consumes #bootstrap=... and removes it immediately, offers code entry
when unauthenticated. Preview mode may be explicitly synthetic IndexedDB, but
must not silently stand in for a failed real backend or sensor connection.

Local settings use key watch:<deviceId> with {elevated,warning,rise_limit}.
Background evaluators and interface use these saved watch settings. A receiver
credential is unique to its installation and hashed at rest. Device API remains
POST /api/v1/readings and GET /api/v1/device-config with bearer auth.

Dual receivers: V2 firmware has primary URL/token and optional secondary
URL/token, independent configuration polling, pending sample and delivery retry
per destination. Each destination's packet uses that destination's acknowledged
configuration revision. Each installation preserves raw readings and its own
calibration snapshot. Clearly disclose that independent setup settings can
differ; do not falsely label cross-device data/calibration as synchronized.
Both destinations share stable measurement timestamp/sample ID. Do not let a
blocked destination prevent the other from receiving. No hardcoded credentials.

UI requirements: ordinary river monitor; two independent plain-language status
summaries for water quality and rising water, evidence age and next action above
the fold. Details/units/raw values below. Calm deep teal, readable soft glass,
spacious charts/tables. Progressive detail and accessible mobile navigation.
No global safe/drinkable label. Water warning persists despite another missing
probe. Rill is an optional explicitly rule-based guide, no AI dependency.
Background permission denial and disconnects must be honest. Separate demo from
real sensors everywhere. Do not overwrite unrelated work.
