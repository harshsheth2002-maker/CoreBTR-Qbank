// Functional test for the image layer that lives inside index.html.
// It extracts the real <script id="corebtr-image-recovery"> block from the page
// and drives it through a stub DOM, so what is tested is exactly what ships.
// Exits non-zero on any failed check.
//
//   node export/test_image_recovery.mjs
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const pagePath = path.join(here, '..', 'index.html');
if (!fs.existsSync(pagePath)) {
  console.error('missing ' + pagePath);
  process.exit(2);
}
const page = fs.readFileSync(pagePath, 'utf8');
const m = /<script id="corebtr-image-recovery">([\s\S]*?)<\/script>/.exec(page);
if (!m) { console.error('recovery script not found in the page'); process.exit(2); }
const src = m[1];

let failures = 0, passed = 0;
function check(cond, msg) {
  if (cond) { passed++; console.log('  ok  ', msg); }
  else { failures++; console.log('  FAIL', msg); }
}

/* ---------------------------------------------------------------- stub DOM */
const docListeners = {};
const created = [];
let pageImgs = [];

function makeEl(tag) {
  const el = {
    tagName: String(tag).toUpperCase(),
    style: {}, dataset: {}, children: [], _h: {}, _html: '',
    textContent: '',
    set innerHTML(v) { this._html = v; }, get innerHTML() { return this._html; },
    appendChild(c) { this.children.push(c); return c; },
    addEventListener(t, fn) { (this._h[t] ||= []).push(fn); },
    removeAttribute() {},
    set src(v) { this._src = v; }, get src() { return this._src; },
    get currentSrc() { return this._src; },
    naturalWidth: 640, naturalHeight: 480,
  };
  created.push(el);
  return el;
}

global.document = {
  readyState: 'complete',
  body: makeEl('body'),
  addEventListener(t, fn) { (docListeners[t] ||= []).push(fn); },
  getElementsByTagName() { return pageImgs; },
  getElementById(id) { return created.find((e) => e.id === id) || null; },
  createElement: makeEl,
};
global.window = global;
new Function(src)();

const mkImg = (s) => {
  const img = makeEl('img');
  img.src = s;
  return img;
};
const fire = (type, img) => (docListeners[type] || []).forEach((fn) => fn({ target: img }));
const S = () => window.__COREBTR_IMG.stats;
const CDN = 'https://assets.corebtr.com/';
const S3 = 'https://corebtr-assets-production.s3.ap-south-1.amazonaws.com/';
const PROXY = 'https://images.weserv.nl/?url=';

console.log('testing', src.length, 'chars of the injected image layer\n');

console.log('[1] page-level integrity');
check(page.indexOf('id="corebtr-image-recovery"') !== -1, 'recovery script is inside index.html');
check(page.match(/id="corebtr-image-recovery"/g).length === 1, 'exactly one recovery block (no duplicates)');
check(page.indexOf('img.crossOrigin') === -1, 'the CORS-mode line is gone from the page');
check((page.match(/video\.crossOrigin/g) || []).length === 5, 'video crossOrigin uses are untouched (5)');
check(page.indexOf('viewer/image-probe') === -1 && page.indexOf('image-probe.html') === -1,
      'page does not depend on any external probe file');
const scriptSrcs = [...page.matchAll(/<script[^>]+src="([^"]+)"/g)].map((x) => x[1]);
check(scriptSrcs.length > 0 && scriptSrcs.every((u) => u.startsWith('https://')),
      'all ' + scriptSrcs.length + ' script tags are remote CDNs - no local .js file is required');
check(!/href="(?!https?:|#|data:)[^"]+\.(css|js)"/.test(page),
      'no local stylesheet or script is referenced');

console.log('\n[2] fallback chain: cdn -> s3 -> proxy -> give up');
const img = mkImg(CDN + 'questions_image/01KX8EXNQKNHBE7Y77DCHSY09R.jpg');
fire('error', img);
check(img.src.startsWith(S3), 'error 1 falls back to the public S3 origin');
fire('error', img);
check(img.src.startsWith(PROXY), 'error 2 falls back to the image proxy');
fire('error', img);
check(img.dataset.corebtrPlaceholder === '1', 'error 3 marks the placeholder (no retry loop)');
check(img.alt.startsWith('Image unavailable'), 'placeholder alt text set: ' + img.alt);
check(img.dataset.corebtrTried === 'cdn,s3', 'tried list records the modes it left');
check(S().seen === 3 && S().failed === 1, 'stats: 3 attempts, 1 failure -> ' + JSON.stringify(S()));
fire('error', img);
check(S().seen === 3 && S().failed === 1, 'further errors neither re-loop nor double-count');

console.log('\n[3] healthy and unrelated images are left alone');
const ok = mkImg(CDN + 'question_explanation/7ba8f50d-6549-459c-bed6-0734512e3ad5.jpg');
fire('load', ok);
check(ok.src.startsWith(CDN) && !ok.dataset.corebtrMode, 'a loading image is not rewritten');
const dataUri = mkImg('data:image/png;base64,AAAA');
fire('error', dataUri);
check(dataUri.src.startsWith('data:'), 'data: URIs are ignored');
const thumb = mkImg('https://video.gumlet.io/69882c/thumbnail-1-0.png?v=1');
fire('error', thumb);
check(thumb.src.includes('gumlet'), 'video thumbnails are not rewritten');

console.log('\n[4] one working host is promoted to the whole page');
pageImgs = [];
const rec = mkImg(CDN + 'questions_image/01KN44AV4RP251AY7VHGVG5FCH.jpg');
fire('error', rec);
check(rec.src.includes('amazonaws.com'), 'recovery image moved to S3');
fire('load', rec);
check(window.COREBTR_IMG_MODE === 's3', 'global mode promoted to s3');
check(S().recovered === 1, 'recovery counted');

console.log('\n[5] explicit host switch rewrites every bank image');
pageImgs = [mkImg(CDN + 'questions_image/A.jpg'), mkImg(S3 + 'questions_image/B.png'),
            mkImg('https://example.com/unrelated.png')];
window.__COREBTR_IMG.rewriteAll('proxy');
check(pageImgs[0].src.startsWith(PROXY) && pageImgs[1].src.startsWith(PROXY),
      'cdn and s3 URLs both rewritten to the proxy');
check(pageImgs[2].src === 'https://example.com/unrelated.png', 'unrelated images are skipped');

console.log('\n[6] the built-in host probe (no external file needed)');
const api = window.__COREBTR_IMG;
check(typeof api.probe === 'function', 'probe() is exposed on __COREBTR_IMG');
check(Array.isArray(api.samples) && api.samples.length === 6, 'six real sample paths embedded: ' + api.samples.length);
check(api.samples.every((p) => /^(questions_image|question_explanation)\//.test(p)),
      'every sample is a real bank object path');
const createdBefore = created.length;
api.probe();
const overlay = created.find((e) => e.id === 'corebtr-img-probe');
check(!!overlay, 'probe() builds an in-page overlay');
const probeImgs = created.slice(createdBefore).filter((e) => e.tagName === 'IMG' && e._src);
check(probeImgs.length === 18, 'probe loads 6 samples x 3 hosts = ' + probeImgs.length + ' images');
check(probeImgs.filter((i) => i.src.startsWith(CDN)).length === 6, '6 through the CoreBTR CDN');
check(probeImgs.filter((i) => i.src.startsWith(S3)).length === 6, '6 through the S3 origin');
check(probeImgs.filter((i) => i.src.startsWith(PROXY)).length === 6, '6 through the proxy');
check(probeImgs.every((i) => i.referrerPolicy === 'no-referrer'), 'probe images send no referrer');
check(probeImgs.every((i) => !('crossorigin' in i) || i.crossorigin === undefined),
      'probe images do not request CORS mode');
const first = probeImgs[0];
first._h.load.forEach((fn) => fn());
check(created.some((e) => e.textContent && /^OK \d+x\d+$/.test(e.textContent)),
      'a loading probe image is labelled OK with its dimensions');
const second = probeImgs[1];
second._h.error.forEach((fn) => fn());
check(created.some((e) => e.textContent === 'BLOCKED'), 'a failing probe image is labelled BLOCKED');
const summaryEl = created.find((e) => e.id === 'corebtr-img-probe-summary');
check(!!summaryEl && /CoreBTR CDN 1\/6/.test(summaryEl.innerHTML),
      'summary tallies per host: ' + (summaryEl ? summaryEl.innerHTML.replace(/<[^>]+>/g, '') : 'none'));

console.log('\n[7] keyboard shortcut and programmatic host switch');
check((docListeners.keydown || []).length === 1, 'Ctrl/Cmd+Shift+H handler registered');
pageImgs = [mkImg(CDN + 'questions_image/C.jpg')];
check(api.setMode('s3') === true, 'setMode("s3") accepted');
check(pageImgs[0].src.startsWith(S3), 'setMode rewrote the page images');
check(api.setMode('nonsense') === false, 'setMode rejects an unknown host');

console.log(failures ? `\n${failures} of ${passed + failures} CHECK(S) FAILED`
                     : `\nALL ${passed} CHECKS PASSED`);
process.exit(failures ? 1 : 0);
