const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');

(async () => {
  let browser;
  try {
    browser = await puppeteer.launch({
      headless: 'new',
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    });
    const page = await browser.newPage();

    // Wide viewport so flexbox renders horizontally; 2x for retina-quality PNG
    await page.setViewport({ width: 1600, height: 1200, deviceScaleFactor: 2 });

    // Load HTML as data URL to avoid file:// path issues with spaces
    const htmlPath = path.resolve(__dirname, 'mindmap.html');
    const html = fs.readFileSync(htmlPath, 'utf8');
    await page.setContent(html, { waitUntil: 'networkidle0' });

    // Wait for web fonts
    await page.evaluate(() => document.fonts.ready);

    // Screenshot only the diagram container — auto-crops to its bounding box
    const element = await page.$('.mindmap-container');
    if (!element) {
      console.error('ERROR: Could not find .mindmap-container element');
      process.exit(1);
    }

    const box = await element.boundingBox();
    console.log('Bounding box:', JSON.stringify(box));
    if (!box || box.width === 0 || box.height === 0) {
      console.error('ERROR: Element has zero-size bounding box');
      process.exit(1);
    }

    const outputPath = path.resolve(__dirname, '..', 'mindmap.png');
    await element.screenshot({ path: outputPath, omitBackground: false });

    console.log('Saved:', outputPath);
  } catch (err) {
    console.error('ERROR:', err.message);
    process.exit(1);
  } finally {
    if (browser) await browser.close();
  }
})();
