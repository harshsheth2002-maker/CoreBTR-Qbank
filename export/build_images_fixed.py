#!/usr/bin/env python3
"""Build and maintain the single-file QBank page: `index.html`.

Everything the QBank needs at runtime lives inside that one file - the question
data, the app shell, and the image layer described below. No other file is
loaded, and no build step is required to view it.

Why the image layer exists
--------------------------
The original page sabotaged its own image loading:

    img.crossOrigin = "Anonymous";             // forces CORS mode
    img.referrerPolicy = "no-referrer";
    const dataUrl = await fetchToDataUrl(src); // fetch(url, { mode: "cors" })

`crossOrigin` puts the <img> request in CORS mode. Unless the CDN answers with
`Access-Control-Allow-Origin`, the browser discards the response and the image
stays blank - even though the same URL paints fine in a plain <img>. The
`fetch(..., {mode:"cors"})` probe fails for the same reason, and its fallback is
still in CORS mode, so it fails too.

What is injected into `index.html` (one <script> block, id
`corebtr-image-recovery`)
--------------------------------------------------------------------------
1. the `img.crossOrigin = "Anonymous"` line is removed from the page;
2. a failed image is retried across CoreBTR CDN -> public S3 origin -> image
   proxy, with a visible placeholder when all three fail;
3. whichever host first succeeds is promoted to every other image on the page;
4. a badge reports `images ok/total . host <mode>`; clicking it cycles host;
5. a built-in host probe (badge "test" button, or Ctrl/Cmd+Shift+H, or
   `__COREBTR_IMG.probe()`) loads real images from the bank through all three
   hosts and offers a one-click "use this host" per column.

Question text, options, answers and explanations are never touched.

Usage
    python3 export/build_images_fixed.py               # (re)inject into index.html
    python3 export/build_images_fixed.py --host s3     # + CoreBTR-QBank.s3.html variant
    python3 export/build_images_fixed.py --host proxy  # + CoreBTR-QBank.proxy.html
    node export/test_image_recovery.mjs                # test the injected script

Re-injection is idempotent: an existing block is replaced, not duplicated.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "index.html"

CDN_HOST = "assets.corebtr.com"
S3_HOST = "corebtr-assets-production.s3.ap-south-1.amazonaws.com"

IMAGE_URL_RE = re.compile(
    r"https://" + CDN_HOST + r"/(?:questions_image|question_explanation)/[^\"\\]+"
)

CROSS_ORIGIN_LINE = 'try { img.crossOrigin = "Anonymous"; } catch (e) {}'
REMOVAL_COMMENT = "/* removed: crossOrigin forced CORS mode and blanked every image */"
MARKER = 'id="corebtr-image-recovery"'
# matches the injected block exactly, with no surrounding whitespace, so that
# re-injecting an unchanged page reproduces byte-identical output
BLOCK_RE = re.compile(r'<script id="corebtr-image-recovery">[\s\S]*?</script>')

# ---------------------------------------------------------------- runtime JS
RUNTIME = r"""
<script id="corebtr-image-recovery">
/* Single-file image layer for the CoreBTR QBank.
   Self-contained: no external file, framework or build step.
   (a) retries failed images across three hosts,
   (b) promotes the first host that works to the whole page,
   (c) provides an in-page probe so you can see which host your network allows. */
(function () {
  var CDN = "assets.corebtr.com";
  var S3 = "corebtr-assets-production.s3.ap-south-1.amazonaws.com";
  var PROXY_PREFIX = "https://images.weserv.nl/?url=";

  /* real object paths from this bank, embedded at build time */
  var PROBE_SAMPLES = __PROBE_SAMPLES__;

  var MODES = ["cdn", "s3", "proxy"];
  var LABELS = { cdn: "CoreBTR CDN", s3: "S3 origin", proxy: "proxy" };
  var mode = window.COREBTR_IMG_MODE || "cdn";
  var switched = false;

  var stats = { seen: 0, ok: 0, failed: 0, recovered: 0 };
  window.__COREBTR_IMG_STATS = stats;

  function objectPath(src) {
    var s = String(src || "");
    /* proxy URLs carry the real path percent-encoded, so decode before matching */
    if (s.indexOf("%2F") !== -1 || s.indexOf("%2f") !== -1) {
      try { s = decodeURIComponent(s); } catch (e) {}
    }
    var m = /(questions_image|question_explanation)\/([^?#]+)/.exec(s);
    return m ? m[1] + "/" + m[2] : null;
  }

  function urlFor(path, m) {
    if (m === "s3") return "https://" + S3 + "/" + path;
    if (m === "proxy") return PROXY_PREFIX + encodeURIComponent(CDN + "/" + path);
    return "https://" + CDN + "/" + path;
  }

  function nextMode(m) {
    var i = MODES.indexOf(m);
    return MODES[(i + 1) % MODES.length];
  }

  function applyHost(img) {
    /* plain <img>: no crossOrigin, no referrer -> maximum chance of painting */
    try { img.removeAttribute("crossorigin"); } catch (e) {}
    try { img.referrerPolicy = "no-referrer"; } catch (e) {}
  }

  function triedOf(img, cur) {
    var list = (img.dataset.corebtrTried || "").split(",").filter(Boolean);
    if (cur && list.indexOf(cur) === -1) list.push(cur);
    return list;
  }

  function firstUntried(tried) {
    for (var i = 0; i < MODES.length; i++) {
      if (tried.indexOf(MODES[i]) === -1) return MODES[i];
    }
    return null;
  }

  /* image errors do not bubble - listen in the capture phase */
  document.addEventListener("error", function (ev) {
    var img = ev.target;
    if (!img || img.tagName !== "IMG") return;
    var path = objectPath(img.currentSrc || img.src || "");
    if (!path) return;
    if (img.dataset.corebtrPlaceholder === "1") return;   /* already given up on it */

    stats.seen++;
    var tried = triedOf(img, img.dataset.corebtrMode || mode);
    var next = firstUntried(tried);

    if (!next) {
      stats.failed++;
      img.dataset.corebtrPlaceholder = "1";
      img.alt = "Image unavailable (" + path.split("/")[1] + ")";
      img.style.minHeight = "48px";
      img.style.background = "#fee2e2";
      img.style.border = "1px dashed #ef4444";
      badge();
      return;
    }

    img.dataset.corebtrTried = tried.join(",");
    img.dataset.corebtrMode = next;
    applyHost(img);
    img.src = urlFor(path, next);
  }, true);

  document.addEventListener("load", function (ev) {
    var img = ev.target;
    if (!img || img.tagName !== "IMG") return;
    if (!objectPath(img.currentSrc || img.src || "")) return;
    stats.ok++;
    if (img.dataset.corebtrMode) {
      stats.recovered++;
      /* one image proved which host works - move everything else onto it once */
      if (!switched && img.dataset.corebtrMode !== mode) {
        switched = true;
        mode = img.dataset.corebtrMode;
        window.COREBTR_IMG_MODE = mode;
        rewriteAll(mode);
      }
    }
    badge();
  }, true);

  /* ------------------------------------------------------------------ badge */
  var el = null;
  function badge() {
    if (!document.body) return;
    if (!el) {
      el = document.createElement("div");
      el.id = "corebtr-img-badge";
      el.style.cssText = "position:fixed;right:10px;bottom:10px;z-index:2147483000;" +
        "font:12px/1.4 system-ui,-apple-system,Segoe UI,sans-serif;background:#0f172a;" +
        "color:#e2e8f0;padding:6px 9px;border-radius:8px;box-shadow:0 6px 20px rgba(0,0,0,.35);" +
        "user-select:none;opacity:.94;display:flex;gap:8px;align-items:center";
      var txt = document.createElement("span");
      txt.id = "corebtr-img-badge-text";
      txt.style.cssText = "cursor:pointer";
      txt.title = "Click to switch image host (cdn -> s3 -> proxy)";
      txt.addEventListener("click", function () {
        mode = nextMode(mode);
        window.COREBTR_IMG_MODE = mode;
        rewriteAll(mode);
        badge();
      });
      var btn = document.createElement("span");
      btn.id = "corebtr-img-probe-btn";
      btn.textContent = "test hosts";
      btn.style.cssText = "cursor:pointer;background:#1d4ed8;color:#fff;padding:2px 6px;" +
        "border-radius:6px;font-weight:600";
      btn.title = "Test which image host your network can reach (Ctrl/Cmd+Shift+H)";
      btn.addEventListener("click", function () { probe(); });
      el.appendChild(txt);
      el.appendChild(btn);
      document.body.appendChild(el);
    }
    var t = document.getElementById("corebtr-img-badge-text");
    if (t) {
      t.innerHTML = "images " + stats.ok + "/" + (stats.ok + stats.failed) +
        " &middot; host <b>" + mode + "</b>" +
        (stats.recovered ? " &middot; recovered " + stats.recovered : "");
    }
  }

  function rewriteAll(m) {
    var imgs = document.getElementsByTagName("img");
    for (var i = 0; i < imgs.length; i++) {
      var path = objectPath(imgs[i].currentSrc || imgs[i].src || "");
      if (!path) continue;
      applyHost(imgs[i]);
      imgs[i].dataset.corebtrTried = "";
      imgs[i].dataset.corebtrMode = m;
      imgs[i].src = urlFor(path, m);
    }
  }

  /* ------------------------------------------------------------------ probe */
  var overlay = null;

  function probe() {
    if (overlay) { overlay.style.display = "block"; return; }

    overlay = document.createElement("div");
    overlay.id = "corebtr-img-probe";
    overlay.style.cssText = "position:fixed;inset:0;z-index:2147483600;background:rgba(15,23,42,.55);" +
      "display:flex;align-items:center;justify-content:center;padding:16px;" +
      "font:13px/1.5 system-ui,-apple-system,Segoe UI,sans-serif";

    var box = document.createElement("div");
    box.style.cssText = "background:#fff;color:#0f172a;border-radius:12px;max-width:760px;width:100%;" +
      "max-height:86vh;overflow:auto;padding:18px 20px;box-shadow:0 24px 70px rgba(0,0,0,.35)";

    var head = document.createElement("div");
    head.style.cssText = "display:flex;justify-content:space-between;align-items:flex-start;gap:12px";
    head.innerHTML = "<div><div style='font-size:16px;font-weight:700'>Which image host works here?</div>" +
      "<div style='color:#475569;margin-top:2px'>Each cell loads a real image from this bank through one host. " +
      "Green means that host can serve your images.</div></div>";
    var close = document.createElement("button");
    close.textContent = "Close";
    close.style.cssText = "border:1px solid #cbd5e1;background:#f8fafc;border-radius:8px;" +
      "padding:4px 10px;cursor:pointer;font:inherit";
    close.addEventListener("click", function () { overlay.style.display = "none"; });
    head.appendChild(close);
    box.appendChild(head);

    var table = document.createElement("table");
    table.style.cssText = "border-collapse:collapse;width:100%;margin-top:12px";
    var thead = document.createElement("thead");
    var hr = document.createElement("tr");
    ["Object", LABELS.cdn, LABELS.s3, LABELS.proxy].forEach(function (h, i) {
      var th = document.createElement("th");
      th.textContent = h;
      th.style.cssText = "text-align:left;padding:6px 8px;background:#f1f5f9;font-weight:600;" +
        "border-bottom:1px solid #e2e8f0";
      if (i > 0) {
        var use = document.createElement("button");
        use.textContent = "use";
        use.style.cssText = "margin-left:6px;border:1px solid #93c5fd;background:#eff6ff;" +
          "color:#1d4ed8;border-radius:6px;padding:1px 6px;cursor:pointer;font:inherit;font-size:11px";
        use.addEventListener("click", (function (m) {
          return function () {
            mode = m;
            window.COREBTR_IMG_MODE = m;
            switched = true;
            rewriteAll(m);
            badge();
            use.textContent = "active";
          };
        })(MODES[i]));
        th.appendChild(use);
      }
      hr.appendChild(th);
    });
    thead.appendChild(hr);
    table.appendChild(thead);

    var counts = { cdn: 0, s3: 0, proxy: 0 };
    var tbody = document.createElement("tbody");
    PROBE_SAMPLES.forEach(function (path) {
      var tr = document.createElement("tr");
      var tdName = document.createElement("td");
      tdName.textContent = path.split("/")[1].slice(0, 34);
      tdName.style.cssText = "padding:6px 8px;border-bottom:1px solid #f1f5f9;" +
        "font-family:ui-monospace,Menlo,monospace;font-size:11px;color:#475569";
      tr.appendChild(tdName);

      MODES.forEach(function (m) {
        var td = document.createElement("td");
        td.style.cssText = "padding:6px 8px;border-bottom:1px solid #f1f5f9;white-space:nowrap";
        var im = document.createElement("img");
        im.style.cssText = "max-width:84px;max-height:56px;border:1px solid #e2e8f0;" +
          "border-radius:4px;background:#f1f5f9;vertical-align:middle;margin-right:6px";
        applyHost(im);
        var lab = document.createElement("span");
        lab.textContent = "...";
        lab.style.cssText = "color:#64748b";
        im.addEventListener("load", function () {
          counts[m]++;
          lab.textContent = "OK " + im.naturalWidth + "x" + im.naturalHeight;
          lab.style.color = "#15803d";
          lab.style.fontWeight = "600";
          summary();
        });
        im.addEventListener("error", function () {
          lab.textContent = "BLOCKED";
          lab.style.color = "#b91c1c";
          lab.style.fontWeight = "600";
          summary();
        });
        im.src = urlFor(path, m);
        td.appendChild(im);
        td.appendChild(lab);
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    box.appendChild(table);

    var foot = document.createElement("div");
    foot.id = "corebtr-img-probe-summary";
    foot.style.cssText = "margin-top:12px;padding:10px 12px;background:#fffbeb;" +
      "border:1px solid #fde68a;border-radius:10px";
    box.appendChild(foot);

    function summary() {
      var parts = MODES.map(function (m) {
        return LABELS[m] + " " + counts[m] + "/" + PROBE_SAMPLES.length;
      });
      var total = counts.cdn + counts.s3 + counts.proxy;
      var verdict;
      if (total === 0) {
        verdict = "Nothing loaded yet.";
      } else if (counts.cdn === PROBE_SAMPLES.length) {
        verdict = "The CDN works - no fallback needed.";
      } else if (total > 0) {
        verdict = "The CDN is blocked here; click \"use\" on a working column.";
      } else {
        verdict = "";
      }
      if (total === 0 && stats.failed > 0) {
        verdict = "All hosts blocked: the images are gated at the source and would have to be mirrored.";
      }
      foot.innerHTML = "<b>" + parts.join(" &middot; ") + "</b><br>" + verdict;
    }
    summary();

    overlay.appendChild(box);
    overlay.addEventListener("click", function (ev) {
      if (ev.target === overlay) overlay.style.display = "none";
    });
    document.body.appendChild(overlay);
  }

  document.addEventListener("keydown", function (ev) {
    if ((ev.ctrlKey || ev.metaKey) && ev.shiftKey && (ev.key === "H" || ev.key === "h")) {
      ev.preventDefault();
      probe();
    }
  });

  window.__COREBTR_IMG = {
    stats: stats,
    modes: MODES,
    samples: PROBE_SAMPLES,
    urlFor: urlFor,
    objectPath: objectPath,
    rewriteAll: rewriteAll,
    probe: probe,
    setMode: function (m) {
      if (MODES.indexOf(m) === -1) return false;
      mode = m;
      switched = true;
      window.COREBTR_IMG_MODE = m;
      rewriteAll(m);
      badge();
      return true;
    }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", badge);
  } else { badge(); }
})();
</script>
"""


def inject(html: str, samples: list[str]) -> tuple[str, bool]:
    """Insert (or replace) the recovery block. Returns (html, changed).

    Replacing an up-to-date block is a no-op at the byte level."""
    block = RUNTIME.replace("__PROBE_SAMPLES__", json.dumps(samples)).strip()
    if BLOCK_RE.search(html):
        new = BLOCK_RE.sub(lambda _m: block, html, count=1)
        return new, new != html
    idx = html.rindex("</body>")
    return html[:idx] + block + "\n" + html[idx:], True


def sample_paths(html: str, limit: int = 6) -> list[str]:
    urls = IMAGE_URL_RE.findall(html)
    picked, seen = [], set()
    for u in urls:
        path = "/".join(u.split("/")[-2:])
        if path in seen:
            continue
        seen.add(path)
        picked.append(path)
        if len(picked) >= limit:
            break
    return picked


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", choices=["cdn", "s3", "proxy"], default="cdn",
                    help="also write a variant with every image URL on this host")
    ap.add_argument("--samples", type=int, default=6,
                    help="how many real images the in-page probe should test")
    args = ap.parse_args()

    if not SOURCE.exists():
        raise SystemExit(f"{SOURCE} not found")

    html = SOURCE.read_text(encoding="utf-8")
    before_questions = html.count('"correct_answer"')

    removed = html.count(CROSS_ORIGIN_LINE)
    if removed:
        html = html.replace(CROSS_ORIGIN_LINE, REMOVAL_COMMENT)

    samples = sample_paths(html, args.samples)
    if not samples:
        raise SystemExit("no image URLs found in the page - is this the right file?")

    html, changed = inject(html, samples)

    # safety: the page must still be the same question bank
    after_questions = html.count('"correct_answer"')
    if after_questions != before_questions:
        raise SystemExit(f"question count changed {before_questions} -> {after_questions}; aborting")
    if html.count(MARKER) != 1:
        raise SystemExit(f"expected exactly 1 recovery block, found {html.count(MARKER)}")
    if not html.rstrip().endswith("</html>"):
        raise SystemExit("page no longer ends with </html>; aborting")

    if changed or removed:
        SOURCE.write_text(html, encoding="utf-8")
        print(f"updated {SOURCE.relative_to(ROOT)}  {SOURCE.stat().st_size:,} bytes")
        print(f"  crossOrigin lines removed : {removed}")
        print(f"  recovery block            : {'replaced' if removed or BLOCK_RE else 'injected'} (1)")
    else:
        print(f"{SOURCE.relative_to(ROOT)} already up to date")
    print(f"  questions                 : {after_questions:,}")
    print(f"  video.crossOrigin (kept)  : {html.count('video.crossOrigin')}")
    print(f"  probe samples embedded    : {len(samples)}")
    distinct = {"/".join(u.split("/")[-2:]) for u in IMAGE_URL_RE.findall(html)}
    print(f"  distinct image URLs       : {len(distinct):,}")

    if args.host != "cdn":
        variant = html
        if args.host == "s3":
            variant = variant.replace("https://" + CDN_HOST + "/", "https://" + S3_HOST + "/")
        else:
            variant = variant.replace(
                "https://" + CDN_HOST + "/",
                "https://images.weserv.nl/?url=" + CDN_HOST.replace(".", "%2E") + "%2F",
            )
        out = ROOT / f"CoreBTR-QBank.{args.host}.html"
        out.write_text(variant, encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)}  {out.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
