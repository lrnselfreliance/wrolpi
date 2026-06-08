#!/usr/bin/env node
/**
 * Render a live URL to a PNG screenshot using Puppeteer.
 *
 * Chrome's CLI `--screenshot` captures before a WebGL canvas (MapLibre) composites,
 * producing a blank image.  Puppeteer with the new headless mode + SwiftShader renders
 * WebGL correctly, and lets us wait for the page to signal it is done painting.
 *
 * Usage: node screenshot_url.js <url> <output_path> [width] [height] [timeout_ms]
 *
 * The page may set `window.__wrolpiMapIdle = true` (see modules/map/static/embed.html)
 * to indicate rendering is complete; we wait for that flag, falling back to a fixed
 * settle delay when it is absent.
 */
const puppeteer = require('puppeteer');

(async () => {
  const url = process.argv[2];
  const out = process.argv[3];
  const width = parseInt(process.argv[4] || '1280', 10);
  const height = parseInt(process.argv[5] || '720', 10);
  const timeoutMs = parseInt(process.argv[6] || '45000', 10);

  if (!url || !out) {
    console.error('Usage: node screenshot_url.js <url> <output_path> [width] [height] [timeout_ms]');
    process.exit(2);
  }

  const browser = await puppeteer.launch({
    headless: 'new',
    executablePath: '/usr/bin/google-chrome',
    args: [
      '--no-sandbox',
      '--disable-dev-shm-usage',
      '--ignore-certificate-errors',
      // SwiftShader software rendering so WebGL works without a GPU.
      '--use-gl=angle',
      '--use-angle=swiftshader',
      '--enable-unsafe-swiftshader',
      `--window-size=${width},${height}`,
    ],
    ignoreHTTPSErrors: true,
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width, height });
    page.on('pageerror', e => console.error('PAGEERROR', e.message));

    await page.goto(url, { waitUntil: 'networkidle0', timeout: timeoutMs });

    // Wait for the page's render-complete flag if it exposes one; otherwise settle briefly.
    const hasFlag = await page.evaluate(() => typeof window.__wrolpiMapIdle !== 'undefined'
      || typeof window.__wrolpiMap !== 'undefined');
    if (hasFlag) {
      await page.waitForFunction(() => window.__wrolpiMapIdle === true, { timeout: timeoutMs })
        .catch(() => console.error('WARN map idle flag not set before timeout; capturing anyway'));
    } else {
      await new Promise(res => setTimeout(res, 3000));
    }

    await page.screenshot({ path: out });
    console.error('OK wrote', out);
  } finally {
    await browser.close();
  }
})().catch(e => { console.error('FATAL', e && e.stack || e); process.exit(1); });
