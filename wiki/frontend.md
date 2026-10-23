# The browser is a view of changing evidence

[Home](Home.md) · [Backend](backend.md) · Next: [Rill](rill-ai.md)

The difficult frontend problem is not drawing four cards. It is deciding which response still belongs on the screen when the user changes station, changes tab, edits a draft or reconnects during a reply.

[App.tsx](../frontend/src/App.tsx) owns the current destination, source, station and overview. It renders Overview, Setup and History, with Settings and Rill as overlays. The source control's **Sensors** button chooses hardware data; the navigation's **Setup** button opens the station workflow. Keeping those names distinct makes their different effects visible.

## Keep the rule separate from the component

Small `*State.ts` modules hold decisions that do not need a DOM. [historyState.ts](../frontend/src/historyState.ts) builds a view identity from source, station, tab and relevant filters. `pageRows()` returns rows only when the response identity matches the view identity. A late reading response must not become a signal-history row simply because the user switched tabs before it arrived.

[modelState.ts](../frontend/src/modelState.ts) preserves an unapplied local model choice while inventory polling continues. A successful refresh should update the available models without discarding the user's draft. Its loading placeholder also distinguishes an initial request from an already-settled failure.

[chatState.ts](../frontend/src/chatState.ts) reconciles independently arriving job events and conversation snapshots. Sequence and revision checks reject older updates. A completed answer stays visible until its exact turn appears in the persisted transcript; matching text in an earlier answer is not enough.

Empty chats keep the welcome text at the top. Automatic scrolling follows actual conversation content only while the reader is already near the bottom, and stays disabled in chat history.

The components still own effects, input and rendering. The extracted functions own testable decisions. Tests use Node's built-in runner and import the TypeScript modules directly; there is no component-test framework installed.

## Requests carry context

[api.ts](../frontend/src/api.ts), `api()` at line 4, prefixes the web API path, sends same-origin credentials and attaches the CSRF token. It converts error bodies into `ApiError`, preserving HTTP status and retry delay. Components can distinguish a session failure or conflicting save from a generic network problem.

`time()` displays Malaysia time. `age()` formats elapsed seconds into seconds, minutes, hours or days and keeps unknown values explicit. A missing transmission age should not pretend to be a fresh transmission.

History uses paired tab and panel IDs, roving tab stops, Left/Right wrapping and Home/End navigation. The selected panel is keyboard focusable. The chart receives a human-readable title so assistive technology hears “Water level” instead of an internal field key.

## Motion belongs to the lifecycle

[ui.tsx](../frontend/src/ui.tsx), `Modal()` at line 6, renders through a portal, locks background scrolling and restores the prior focus after unmount. Its close function first changes visual state and then calls the parent's close callback after 220 ms. Inner Cancel buttons use that same close path through `exposeClose`; directly unmounting would skip the exit.

The focus trap includes native `summary` controls as well as form controls and buttons. Only the top modal handles Escape and boundary wrapping. Check nested dialogs and disclosures in the browser when editing this code; a pure state test cannot prove focus behavior.

[styles.css](../frontend/src/styles.css) keeps motion, palette, spacing, type and radius tokens in `:root`. Reading cards and chart colors share metric tokens. A metric color identifies a measurement; status wording and status colors describe the current check. Changing a metric must update its line, selected control and legend together. Plotly also reads the shared text, surface, border and caption tokens.

Entrance animation enhances otherwise visible content. Reduced-motion rules disable animation and transitions. The stylesheet uses tokens for every font size and border radius, with shared spacing steps for common padding, margins and gaps. Small optical offsets and layout-specific dimensions remain explicit. See the [style system](style-system.md) for choosing a token. Do not reformat the entire stylesheet to adjust one component.

## Check both logic and appearance

Run `npm test` and `npm run build` from `frontend`, plus the backend suite from the root. Open the isolated review app for desktop and narrow-screen inspection. Test keyboard navigation and real error states as well as the happy path. A successful TypeScript build cannot detect an obscured button or a focus escape.
