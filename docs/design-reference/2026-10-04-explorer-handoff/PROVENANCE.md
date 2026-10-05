# Provenance: Trinity Explorer design handoff package

## Source

Alayala supplied this package as the folder `design_handoff_trinity_explorer/` in his Downloads folder. He stated that he has worked with it since Saturday, October 3, 2026. The source file times are October 4, 2026, 23:45 local time. On October 5, 2026, Claude copied the files here byte for byte, at his request (frontend proposal Q4). The originals stay unchanged in the source folder.

## Authorship

**Pending confirmation.** The author of `Trinity.dc.html` and `README.md` is not recorded. Do not attribute these files to a person or tool without evidence. Alayala reported that design images and design prompts were generated in a Codex chat; that chat was not inspected. The [A25](../../../DECISIONS.md#a25--figma-design-and-brand-handoff) attribution of the Figma mockups (alayala) and the brand board (ChatGPT, per alayala) is unchanged.

## Status

Design reference only. It is not production code, test evidence or EIA data. Values in the prototype are illustrative fixtures. The current contracts take priority over this package; see the [frontend specification](../../../sdd/frontend/spec.md).

## Excluded files

| File | SHA-256 of the original | Reason |
|---|---|---|
| `support.js` | `8fe7df74405f3c55f49b7249c74ea1397e65d07dea2b1bd3b4a489bec2e28cbe` | Generated prototype runtime, excluded at alayala's request. It is not needed by the React app. |
| `.DS_Store` | not recorded | macOS folder metadata, not part of the design. |

Because `support.js` is excluded, `Trinity.dc.html` does not run from this folder. To view the interactive prototype, open the original in the source folder. The HTML is still readable as source: the logic, fixtures and states are in its `<script data-dc-script>` block.

## Copied files

SHA-256 of each copy. Each copy matched its original when it was made.

| SHA-256 | File |
|---|---|
| `3a2ccf679033c21f92a1639bfa47dd0f70cdc929b98e064f2513e0c88a2f41e4` | `assets/mark-orange.png` |
| `88f4303749fe1382a404fc062792d320385abcb28133d73a18490508c825d428` | `assets/mark-slate.png` |
| `ea5656c09c637b7d341b55cdab33184285b48a76471d7325dbd4724b0819df27` | `assets/wordmark-letters.png` |
| `f1d8919e22212b176028a3572bf56464c5fd67fa073061f9876925595600cdcb` | `assets/wordmark.png` |
| `399a4279e6da9fb312e7510296ef0629a5a911f3f0a4de5f7a117054265ba3ef` | `README.md` |
| `e0a9032bc6e0158fe31f29857072290c6e9b3d132460c7f61520add0700f78eb` | `screenshots/01-sign-in.png` |
| `9d79c7f071b9b4600ea365ea884482a2454487f4a39f78fbf3d0ff5cddbe6c4b` | `screenshots/02-dashboard-top.png` |
| `e3433410a718826e6fe00ec947c0fd6b5557687a63c82114603a18b1fae385d4` | `screenshots/03-dashboard-contributions.png` |
| `eee3f350f31d666e231cdd0ef32f04b8ba21af3924f8df9b5bb98b1cf4064de1` | `screenshots/04-dashboard-90-days.png` |
| `41ccf74edab087940f91c8e3c005a68138fa508f4b901cc999e95aa2a638bde1` | `screenshots/05-dashboard-daily-values.png` |
| `7d569b7a7b1e4692fcc11719f9c0c51d5bc71d44159c4ceba39a8987f9e43bfd` | `screenshots/06-catalog.png` |
| `35de693558dd1fe8d3138f4c579859db56471c1a044e65d9c315e19fc3c3dd54` | `screenshots/07-table-facility.png` |
| `987dc3c7750bf3bcb49d02eff3eab3bececa19bb83fabeeffde177b1e1a5d03a` | `screenshots/08-table-generator.png` |
| `85a341de615515e5745cbca760a2a868be5cf326e51ec1415dd1cab4e8722dc3` | `screenshots/09-table-national.png` |
| `51307f8ef268e0d4df065a82bfa3fc3a076b858c0a9bf55e9e825efbc20acdc4` | `screenshots/10-sql-explorer.png` |
| `c5200ee571e8bd0f66c323bab95bf41a494281f72ad22febcab293dc726568ec` | `screenshots/11-sql-error.png` |
| `a448275521d9fddedb1eaa630adf69a9932e9b3423d73bb015590209a1c5acff` | `screenshots/12-refresh-runs.png` |
| `805d313b8c14f89fcf590fc7b9c8167997a31ecd83137a1d0957b8c0f25791ad` | `screenshots/13-run-review-ver-19c.png` |
| `2e951921faf422de40b8314f5730e0c5647f07ce8652a5e095bbef74b505426c` | `screenshots/14-run-discard-dialog.png` |
| `606ed7982be8baa261e92c848e6343fa2f8a5340736942a466c5a882c1ba798f` | `screenshots/15-run-failed.png` |
| `e59f76d696e4fcd373c2d389874aad4858fb089e89ec9c9043b180a607f7d96a` | `screenshots/16-settings-schedule.png` |
| `1d0a2252f3fd8aeee6eba966be569f74ef0057fc85f06e16725b6a2fdbede0c3` | `screenshots/17-viewer-unavailable.png` |
| `b88647ef5c95e24120d1fbdc2716ee525f954b3b966aea10129e63c729d960b3` | `screenshots/18-sign-in-after.png` |
| `be31dd0a6c67e792fb19dc669b289b56400a1c208115a3b24e85eb25fc40c6d6` | `Trinity.dc.html` |
