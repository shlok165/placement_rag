import { test, type Page } from '@playwright/test';
import { COORDINATOR, signIn, STUDENT } from './helpers';

const OUT = process.env.SHOT_DIR ?? '/img';

async function shot(page: Page, path: string, name: string, fullPage = false) {
  await page.goto(path);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage });
}

test.use({ viewport: { width: 1280, height: 860 } });

test('student pages', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' });
  await shot(page, '/login', 'login');
  await signIn(page, STUDENT);
  await shot(page, '/', 'student-home');
  await shot(page, '/jobs?q=build+reliable+APIs+in+python', 'student-search');
  await page.getByRole('region', { name: 'Results' }).getByRole('heading').first().getByRole('link').click();
  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: `${OUT}/student-job.png` });
  await page.request.get('/api/auth/me');
  await shot(page, '/applications', 'student-applications');
  await shot(page, '/account', 'student-account');
});

test('student on a phone and in the dark', async ({ page }) => {
  await signIn(page, STUDENT);
  await page.emulateMedia({ colorScheme: 'dark' });
  await shot(page, '/', 'student-home-dark');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ colorScheme: 'light' });
  await shot(page, '/jobs', 'student-search-mobile');
});

test('coordinator pages', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' });
  await signIn(page, COORDINATOR);
  await shot(page, '/admin', 'admin-dashboard');
  await shot(page, '/admin/postings', 'admin-postings');
  await shot(page, '/admin/postings/1', 'admin-posting');
  await shot(page, '/admin/usage', 'admin-usage');
  await shot(page, '/admin/postings/new?tab=form', 'admin-add');
});
