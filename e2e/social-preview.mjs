// Renders docs/img/social-preview.png (1280x640) from social-preview.html and two screenshots.
// GitHub cannot set a social preview through its API: upload the file under
// Settings > General > Social preview.
import { chromium } from 'playwright';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 640 } });
await page.goto(new URL('./social-preview.html', import.meta.url).href);
await page.waitForLoadState('networkidle');
// In the e2e container docs/img is mounted at /img.
await page.screenshot({ path: '/img/social-preview.png' });
await browser.close();
