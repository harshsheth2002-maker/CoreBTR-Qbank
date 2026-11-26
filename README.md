# CoreBTR QBank

The entire question bank is **one self-contained file**: `index.html`
(49,979,268 bytes / 47.7 MiB). It holds the app shell, all question data, and the
image layer. Nothing else is loaded — no local script, stylesheet, JSON or probe
file. Serve it and open it.

**284 tests / 19,137 questions.**

| | |
| --- | --- |
| Written explanations | 19,137 (100%) |
| Video solutions | 9,588 (Gumlet DASH/HLS, DRM-protected) |
| Question images | 4,005 (2,442 distinct URLs on `assets.corebtr.com`) |

Earlier revisions stored the same page as ten 5 MB chunks (`part1.txt … part10.txt`)
plus a loader that concatenated them at runtime, to work around GitHub's
web-uploader file-size cap. Those are removed; the pristine pre-fix page is still
recoverable from git history at commit `2a844a8`.

## Running it

```bash
python3 -m http.server 8123 --bind 0.0.0.0     # from the repo root
# http://localhost:8123/
```

HTTP is required: from `file://` the page renders but the DRM video player's CORS
requests are blocked.

## The image layer (built into `index.html`)

The original page sabotaged its own image loading:

```js
img.crossOrigin = "Anonymous";             // <-- forces CORS mode
img.referrerPolicy = "no-referrer";
const dataUrl = await fetchToDataUrl(src); // fetch(url, { mode: "cors" })
if (dataUrl) img.src = dataUrl; else img.src = src;
```

`crossOrigin` puts the `<img>` request in CORS mode. Unless the CDN answers with
`Access-Control-Allow-Origin`, the browser discards the response and the image
stays blank — even though the same URL paints fine in a plain `<img>`. The
`fetch(..., {mode:"cors"})` probe fails for the same reason, and its fallback is
still in CORS mode, so it fails too.

Everything below lives in a single injected block,
`<script id="corebtr-image-recovery">`, near the end of `index.html`:

1. **The `img.crossOrigin = "Anonymous"` line is removed** from the page.
2. **A failed image is retried across three hosts** — CoreBTR CDN →
   public S3 origin (`corebtr-assets-production.s3.ap-south-1.amazonaws.com`) →
   image proxy (`images.weserv.nl`). After all three fail it gets a visible
   dashed placeholder instead of a silent blank.
3. **The first host that works is promoted** to every other image on the page.
4. **A badge** in the bottom-right reports `images 41/45 · host s3 · recovered 12`;
   click it to cycle host.
5. **A built-in host probe** — click **test hosts** on the badge, press
   <kbd>Ctrl</kbd>/<kbd>⌘</kbd>+<kbd>Shift</kbd>+<kbd>H</kbd>, or call
   `__COREBTR_IMG.probe()`. It loads six real images from this bank through all
   three hosts, labels each cell `OK 640x480` or `BLOCKED`, tallies per host, and
   offers a one-click **use** button per column.

Console API: `__COREBTR_IMG` → `{ stats, modes, samples, urlFor, objectPath,
rewriteAll, probe, setMode }`.

Nothing about question text, options, answers or explanations is touched: the
question count is unchanged at 19,137, and the five `video.crossOrigin` uses
(which Shaka DRM genuinely needs) are left alone.

### If all three hosts come back BLOCKED

The images are gated at the source (auth or referer rules) and no rewrite will
help — they would have to be mirrored. No public copy of this bank bundles the
image files.

## Repository tooling (optional, not needed at runtime)

```bash
python3 export/build_export.py               # catalog.json, qbank.jsonl, stats.json
python3 export/build_export.py --full-json   # + tests_list.json (raw array, ~50 MB)
python3 export/build_images_fixed.py         # re-apply/refresh the image layer in index.html
python3 export/build_images_fixed.py --host s3     # + CoreBTR-QBank.s3.html (URLs rewritten up front)
python3 export/build_images_fixed.py --host proxy  # + CoreBTR-QBank.proxy.html
node export/test_image_recovery.mjs          # 39 checks against the injected script
```

| File | In git? | Contents |
| --- | --- | --- |
| `export/catalog.json` | yes | 284 rows: `test_id`, `title`, `num_questions`, `total_marks`, `duration` |
| `export/stats.json` | yes | Totals, per-subject breakdown, source MD5 |
| `export/qbank.jsonl` | ignored (11 MB) | 19,137 lines: `question`, `options` A–D, `answer`, `images`, `video` |
| `export/tests_list.json` | ignored (~50 MB) | Raw `TESTS_LIST` array with every field, incl. `video_metadata` and DRM keys |
| `CoreBTR-QBank.{s3,proxy}.html` | ignored | Single-host variants, if you would rather skip the failing hosts |

`build_export.py` aborts if the parsed question count differs from the sum of the
per-test `num_questions`. `build_images_fixed.py` is byte-idempotent — re-running
it on an up-to-date page reports "already up to date" and changes nothing — and it
refuses to write if the question count changes, if there is not exactly one
recovery block, or if the page no longer ends in `</html>`.

`export/test_image_recovery.mjs` extracts the real script block out of
`index.html` and drives it through a stub DOM, so what it tests is exactly what
ships. It covers page integrity (one block, no CORS line, no local file
dependencies), the three-host fallback chain, placeholder marking, adaptive host
promotion, `rewriteAll`, and the probe overlay (18 images = 6 samples × 3 hosts,
per-host tallies, `setMode`).

### Verification status

Reachability of `assets.corebtr.com` and the S3 bucket **cannot** be checked from
the build environment (no route to either), so whether your images actually load
is something only your browser can confirm — that is what the built-in probe is
for. The code path itself is covered: `node export/test_image_recovery.mjs`
reports `ALL 39 CHECKS PASSED`.

## Subject breakdown

| Subject | Tests | Questions | | Subject | Tests | Questions |
| --- | --- | --- | --- | --- | --- | --- |
| obstetrics | 22 | 1,961 | | radiology | 9 | 571 |
| surgery | 15 | 1,708 | | orthopedics | 12 | 568 |
| microbiology | 12 | 1,301 | | hematology | 7 | 557 |
| preventive | 11 | 1,284 | | anesthesia | 9 | 509 |
| neurology | 24 | 1,238 | | endocrine | 8 | 470 |
| biochemistry | 11 | 1,112 | | respiratory | 10 | 449 |
| pediatrics | 11 | 937 | | renal | 8 | 430 |
| anatomy | 12 | 861 | | gi | 11 | 342 |
| forensic | 11 | 801 | | rheumatology | 8 | 283 |
| ent | 12 | 756 | | immunology | 6 | 177 |
| dermatology | 13 | 753 | | general | 20 | 744 |
| ophthalmology | 12 | 711 | | psychiatry | 10 | 614 |

## Provenance / rights

The question bank is CoreBTR's (Cerebellum Academy / Dr. Zainab Vora) paid
content, mirrored publicly on GitHub. This repository repackages what was already
here — treat hosting, redistribution or resale as a rights question, not a
technical one.
