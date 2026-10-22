# Android distribution repair evidence

22 October 2026 (Malaysia). No existing release asset, APK bytes, signing key or
Android application source was changed by this repair.

## Implemented

- Exact V1 standalone and V2 preview download links, sizes, checksums and clear
  product/version labels in README and `ANDROID-DOWNLOADS.md`.
- Public release verifier and pinned build manifest. Checks anonymous fresh
  redirects, full response, attachment filename/type/length/hash, partial transfer
  and fresh-URL continuation. Signed CDN URLs are not logged or persisted.
- Separate distribution-check workflow; a release event must match an explicit
  manifest tag before it is accepted. New releases must add their size/hash from
  the build output to the manifest.
- Optional ZIP staging preserves the original APK byte for byte, checks archive
  integrity and refuses to overwrite old staged artifacts.

## Checks completed

| Asset | Full transfer | Continuation | SHA-256 |
| --- | --- | --- | --- |
| V1 standalone 2.0.0-preview.1 | HTTP 200; 4,719,750 bytes | HTTP 206; 65,536-byte prefix plus 4,654,214-byte suffix | Matches published manifest |
| V2 observatory preview 1 | HTTP 200; 4,739,999 bytes | HTTP 206; 65,536-byte prefix plus 4,674,463-byte suffix | Matches published manifest |
| Legacy companion 1.0.0-preview.1 | HTTP 200; 5,222,077 bytes | HTTP 206; 65,536-byte prefix plus 5,156,541-byte suffix | Matches published manifest |

All three used unauthenticated public URLs and redirected to
`release-assets.githubusercontent.com`. Responses advertised byte ranges and the
expected Android package content type and attachment filename. Eight verifier
regressions passed, including truncation, checksum mismatch, wrong resume offsets,
ignored range requests, HTML/attachment errors and ZIP preservation.

Local evidence: `output/release-staging/all-public-download-evidence.json`.
Staged V1 ZIP: `output/release-staging/v1-download-repair/RiverGuard-Android-Standalone-2.0.0-preview.1-download.zip`.
Size: 4,383,603 bytes. SHA-256:
`7962c681786ae79a068d021ca7f4f5b274c09bb2d662e9b1e6212ec234250fc9`.
The ZIP contains the original APK, checksum text and install instructions; APK
comparison and ZIP CRC checks passed. These local build files are excluded from Git.

## Still open

- Affected-phone Chrome/Samsung Internet reproduction, actual Download Manager
  resume and completed saving. The automated test closes one HTTP request and
  continues another; it is not an Android browser or radio-disconnection test.
- Phone install/update acceptance and original reported interruption cause.
- Publication of the ZIP alternative and new distribution notes, after the
  agreed release gate. Documentation intentionally does not link an unpublished
  ZIP or claim the original report has been fixed.

No corrupt upload or broken public HTTP range support was reproduced from this
machine. Network-specific or browser-specific failure must remain open until
observed and resolved on the affected phone or an equivalent reproduction.
