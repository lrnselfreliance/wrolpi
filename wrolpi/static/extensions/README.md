# Browser extension binaries

This directory holds the prebuilt WROLPi browser extension binaries that the
backend serves at `/api/extensions/`. The frontend's `/admin/extension` page
serves them to end users.

| File                 | Browser                               | Source                                             |
|----------------------|---------------------------------------|----------------------------------------------------|
| `wrolpi-chrome.zip`  | Chrome / Brave / Edge (Load Unpacked) | `wrolpi-extension` repo, `bash scripts/release.sh` |
| `wrolpi-firefox.xpi` | Firefox (one-click install)           | Mozilla-signed via AMO unlisted self-distribution  |
| `versions.json`      | metadata                              | hand-edited per release                            |

See `wrolpi-extension/RELEASING.md` for the full release procedure.

The signed `.xpi` is not committed in the initial release — it must be
produced by uploading the unsigned bundle to AMO once. The install page
gracefully shows "Not yet available" if a binary is missing.
