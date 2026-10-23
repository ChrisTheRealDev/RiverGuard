# Download RiverGuard for Android

Choose a named version below. **V1 standalone's Android package version is 2.0.0;
it is different from the new V2 observatory.** Both include their interface and
phone storage. Neither download contains an AI model. Do not select GitHub's
automatically generated **Source code** ZIP to install the app.

| App | Download | Size | Release |
| --- | --- | --- | --- |
| V2 observatory, preview 3 - latest warning and readability fixes | [RiverGuard-V2-Preview-3.apk](https://github.com/ChrisTheRealDev/RiverGuard/releases/download/v2-observatory-preview.3/RiverGuard-V2-Preview-3.apk) | 4,757,957 bytes | [Preview 3 release](https://github.com/ChrisTheRealDev/RiverGuard/releases/tag/v2-observatory-preview.3) |
| V1 standalone, preserved older interface | [RiverGuard-Android-Standalone-2.0.0-preview.1.apk](https://github.com/ChrisTheRealDev/RiverGuard/releases/download/android-v2.0.0-preview.1/RiverGuard-Android-Standalone-2.0.0-preview.1.apk) | 4,719,750 bytes (4.72 MB) | [V1 standalone release](https://github.com/ChrisTheRealDev/RiverGuard/releases/tag/android-v2.0.0-preview.1) |
| V2 river observatory, preview 2 — repairs and new colours | [RiverGuard-V2-Preview-2.apk](https://github.com/ChrisTheRealDev/RiverGuard/releases/download/v2-observatory-preview.2/RiverGuard-V2-Preview-2.apk) | 4,757,369 bytes (4.76 MB) | [V2 preview 2 release](https://github.com/ChrisTheRealDev/RiverGuard/releases/tag/v2-observatory-preview.2) |
| V2 river observatory, preview 1 | [RiverGuard-V2-Preview.apk](https://github.com/ChrisTheRealDev/RiverGuard/releases/download/v2-observatory-preview.1/RiverGuard-V2-Preview.apk) | 4,739,999 bytes (4.74 MB) | [V2 preview 1 release](https://github.com/ChrisTheRealDev/RiverGuard/releases/tag/v2-observatory-preview.1) |

V2 preview 2 includes the audit repairs and colour hierarchy update. Preview 1
remains available for reference. The new release is for testing; physical
phone/sensor acceptance is still pending. V1 and V2 have different Android package IDs and can be installed side
by side. Updating the same standalone app should retain its data: do not
uninstall it to retry a download.

For V2 preview 2, an [APK-in-ZIP alternative](https://github.com/ChrisTheRealDev/RiverGuard/releases/download/v2-observatory-preview.2/RiverGuard-V2-Preview-2-APK.zip) contains the identical signed APK.

Preview 3 includes the latest warning labels, emphasis, severity ordering and mobile readability fixes. [APK ZIP alternative](https://github.com/ChrisTheRealDev/RiverGuard/releases/download/v2-observatory-preview.3/RiverGuard-V2-Preview-3-APK.zip) contains the identical APK. [Laptop ZIP](https://github.com/ChrisTheRealDev/RiverGuard/releases/download/v2-observatory-preview.3/RiverGuard-V2-Laptop-Preview-3.zip) includes the same compiled interface.

Preview 3 APK SHA-256: `194844798dd1dadca83715a5fca9626842596bb5665d1b54c4f8a65e13f79482`.

## If the browser download stops

1. Open the exact APK link above in Chrome or Samsung Internet. Check the browser's
   Downloads screen for the filename, received size and error. Downloading an APK
   happens before Android's installation permission prompt.
2. Use Resume if available. If a cached link has expired, reopen this page and start
   from its release link. The repository link redirects to GitHub's download host;
   do not save or reuse the temporary redirected address.
3. Check free storage and retry on a different connection if possible. If only one
   network fails, note whether it blocks `release-assets.githubusercontent.com`.
   Do not disable browser protection or install a file flagged as unsafe.
4. A ZIP alternative is being prepared for the V1 distribution repair. Once its
   release is published, download it, extract the APK in Android Files and open
   that APK. It contains exactly the same signed app. **The ZIP is not yet a
   published download; use the verified APK links above for now.**
5. If it still stops, record the phone/Android version, browser, selected filename,
   displayed error and approximate received size. A desktop transfer passing does
   not establish that the affected phone's download is fixed.

After a complete download, Android may ask whether this browser may install apps.
That is a separate step. The legacy 1.x laptop companion had a different signing
identity; follow [the standalone upgrade guide](STANDALONE-ANDROID.md#installation-and-updates)
if Android rejects an update. Never uninstall an existing standalone installation
without exporting its saved data first.

## File checksums

SHA-256 for the exact APK files linked above:

```text
e21b36913c54e94e80956019faafbff0e68b3c5281b8d4aad62a5046cf36d5b9  RiverGuard-V2-Preview-2.apk
3c7b3be90f346b7f51b19f8fa1a6657ad95df8d23ad46fb8d724ccb8d332fe20  RiverGuard-Android-Standalone-2.0.0-preview.1.apk
f2c73cf50b9377932edaa8f5c1474b9faae960d78bcdb1d2d8434ccbe3f28060  RiverGuard-V2-Preview.apk
```

## Maintainer verification

`docs/downloads.json` pins the release tag, filename, byte count and SHA-256.
When preparing a new release, add its exact asset rather than changing an older
release's files or pointing users to an ambiguous `/latest` URL.

Run from the repository root:

```text
python -m unittest discover -s scripts -p release_downloads_test.py -v
python scripts/release_downloads.py --report output/release-download-evidence.json
python scripts/release_downloads.py --asset v1-standalone --stage output/new-download-staging --report output/new-download-staging-evidence.json
```

The checker uses public anonymous requests, validates full bytes and attachment
headers, obtains a 64 KiB prefix, and resumes through a fresh release URL. It
requires correct HTTP 206 ranges and a matching hash of the combined bytes. It
never writes signed CDN URLs, credentials or authentication tokens into evidence.
Staging verifies the original APK and ZIP round-trip without modifying or
re-signing it; existing staged artifacts are never overwritten.

Public release checks run on manual dispatch, release publication and relevant
pull requests. A failed transfer check blocks treating that release as verified;
it does not automatically delete or replace published assets.

## Repair evidence â€” 22 October 2026

The V1 standalone APK completed anonymously with HTTP 200, the expected APK
content type, attachment filename, all 4,719,750 bytes and its published hash.
A separate 65,536-byte prefix request and a fresh-URL continuation both returned
HTTP 206 with correct ranges; the joined file matched the same checksum.

The staged ZIP contains the byte-identical APK and installation/checksum notes.
It has not been published while the broader repair release is being verified.
**Affected-phone Chrome/Samsung Internet reproduction remains pending.** A
corrupt upload or broken range support was not reproduced from this machine, and
the original stalled-download report remains open.
