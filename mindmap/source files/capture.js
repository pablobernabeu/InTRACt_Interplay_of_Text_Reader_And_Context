// Renders mindmap.html in headless Chromium and saves the .mindmap-container
// element as ../mindmap.png, the framework figure the root README embeds.
//
// Run from mindmap/source files:
//   npm ci
//   npm run capture
//
// mindmap.html loads its font from Google Fonts, so the capture needs network
// access, and the PNG can change if that font changes upstream.

const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');

(async () => {
  let browser;
  try {
    browser = await puppeteer.launch({
      headless: 'new',
      // TODO: justify. No reason is recorded for disabling the Chromium sandbox.
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    });
    const page = await browser.newPage();

    // Wide viewport so flexbox renders horizontally; 2x for retina-quality PNG
    await page.setViewport({ width: 1600, height: 1200, deviceScaleFactor: 2 });

    // Inject the HTML with setContent, so the space in "source files" cannot
    // break a file:// URL. The page has no local assets, only the remote font.
    const htmlPath = path.resolve(__dirname, 'mindmap.html');
    const html = fs.readFileSync(htmlPath, 'utf8');
    await page.setContent(html, { waitUntil: 'networkidle0' });

    // Wait for web fonts
    await page.evaluate(() => document.fonts.ready);

    // Screenshot only the diagram container, which crops to its bounding box.
    const element = await page.$('.mindmap-container');
    if (!element) {
      console.error('ERROR: Could not find .mindmap-container element');
      process.exitCode = 1;
      return;
    }

    const box = await element.boundingBox();
    console.log('Bounding box:', JSON.stringify(box));
    if (!box || box.width === 0 || box.height === 0) {
      console.error('ERROR: Element has zero-size bounding box');
      process.exitCode = 1;
      return;
    }

    const outputPath = path.resolve(__dirname, '..', 'mindmap.png');
    await element.screenshot({ path: outputPath, omitBackground: false });

    console.log('Saved:', outputPath);
  } catch (err) {
    // exitCode, not process.exit(), so the finally block still closes Chromium.
    console.error('ERROR:', err.message);
    process.exitCode = 1;
  } finally {
    if (browser) await browser.close();
  }
})();
