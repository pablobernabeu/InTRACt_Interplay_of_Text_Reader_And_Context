// Rasterise a standalone SVG to a high-DPI PNG using the Chromium bundled with
// puppeteer (installed as a mermaid-cli dependency). No extra tooling required.
//
//   node render_svg.js <input.svg> <output.png> [scale]
//
// `scale` is the device pixel ratio (default 3) for a crisp raster suitable for
// print. The PNG is cropped tightly to the SVG's own width/height.

const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer');

async function main() {
  const [, , inPath, outPath, scaleArg] = process.argv;
  if (!inPath || !outPath) {
    console.error('usage: node render_svg.js <input.svg> <output.png> [scale]');
    process.exit(1);
  }
  const scale = Number(scaleArg) || 3;
  const svg = fs.readFileSync(inPath, 'utf8');

  // Pull the intrinsic pixel size from the SVG's width/height (fallback: viewBox).
  let w, h;
  const wM = svg.match(/<svg[^>]*\bwidth="([\d.]+)/);
  const hM = svg.match(/<svg[^>]*\bheight="([\d.]+)/);
  if (wM && hM) { w = Math.ceil(+wM[1]); h = Math.ceil(+hM[1]); }
  else {
    const vb = svg.match(/viewBox="[\d.]+ [\d.]+ ([\d.]+) ([\d.]+)"/);
    w = Math.ceil(+vb[1]); h = Math.ceil(+vb[2]);
  }

  const html = `<!doctype html><html><head><meta charset="utf-8">
<style>html,body{margin:0;padding:0;background:#fff}#wrap{width:${w}px;height:${h}px}</style>
</head><body><div id="wrap">${svg}</div></body></html>`;

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--force-color-profile=srgb'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: w, height: h, deviceScaleFactor: scale });
  await page.setContent(html, { waitUntil: 'networkidle0' });
  const el = await page.$('#wrap');
  await el.screenshot({ path: outPath, omitBackground: false });
  await browser.close();
  console.log(`wrote ${outPath} (${w}x${h} @${scale}x)`);
}

main().catch(e => { console.error(e); process.exit(1); });
