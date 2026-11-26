import { expect, test, type Page } from '@playwright/test';
import { COORDINATOR, signIn, STUDENT } from './helpers';

// Run against freshly seeded demo data. Everything shown is synthetic.
const OUT = process.env.SHOT_DIR ?? '/img';

async function settle(page: Page) {
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(400);
}

async function shot(page: Page, path: string, name: string) {
  await page.goto(path);
  await settle(page);
  await page.screenshot({ path: `${OUT}/${name}.png` });
}

async function ask(page: Page, text: string) {
  const box = page.getByLabel('Message the copilot');
  await box.fill(text);
  await box.press('Enter');
  await expect(page.getByRole('button', { name: 'Send' })).toBeVisible();
  await settle(page);
}

async function track(page: Page, jobId: number, status: string) {
  const token = (await page.context().cookies()).find((c) => c.name === 'csrf_token')!.value;
  const response = await page.request.put(`/api/applications/${jobId}`, {
    headers: { 'X-CSRF-Token': token },
    data: { status },
  });
  expect(response.ok()).toBe(true);
}

test.use({ viewport: { width: 1280, height: 820 }, colorScheme: 'light' });

test('student portal', async ({ page }) => {
  test.setTimeout(120_000);
  await shot(page, '/login', 'login');
  await signIn(page, STUDENT);
  for (const [id, status] of [
    [1, 'interview'],
    [4, 'applied'],
    [13, 'interested'],
    [16, 'oa'],
  ] as const)
    await track(page, id, status);
  await shot(page, '/', 'student-home');
  await shot(page, '/jobs?q=build+reliable+APIs+in+python&type=internship', 'student-search');
  const results = page.getByRole('region', { name: 'Results' });
  await results.getByRole('heading', { level: 3 }).first().getByRole('link').click();
  await expect(page.getByRole('heading', { name: 'Why this fits' })).toBeVisible();
  await settle(page);
  await page.screenshot({ path: `${OUT}/student-job.png` });
  await shot(page, '/applications', 'student-applications');
  await page.goto('/copilot');
  await ask(page, 'Compare #1 and #13');
  await ask(page, 'I prefer remote roles. Save the first one');
  await page.screenshot({ path: `${OUT}/student-copilot.png` });
  await page.keyboard.press('Control+k');
  await page.getByPlaceholder('Type a page or a posting').fill('robot');
  await settle(page);
  await page.screenshot({ path: `${OUT}/command-palette.png` });
  await page.keyboard.press('Escape');
  await shot(page, '/account?tab=privacy', 'student-privacy');
  await shot(page, '/jobs?q=pizza+recipe', 'student-weak-match');
});

test('student portal on a phone', async ({ page }) => {
  await signIn(page, STUDENT);
  await page.setViewportSize({ width: 390, height: 820 });
  await shot(page, '/jobs', 'mobile-search');
  await shot(page, '/jobs/1', 'mobile-job');
});

test('student portal in the dark', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  await signIn(page, STUDENT);
  await shot(page, '/', 'student-home-dark');
});

test('onboarding', async ({ page }) => {
  await signIn(page, 'ravi@example.com');
  await shot(page, '/onboarding', 'onboarding');
});

test('coordinator portal', async ({ page }) => {
  test.setTimeout(120_000);
  await signIn(page, COORDINATOR);
  await page.goto('/admin/postings/new?tab=paste');
  await page.getByLabel('Posting text').fill(
    [
      'Kiteway Agritech is hiring a Remote Sensing Intern in Chandigarh.',
      '',
      'Stipend: 35,000 - 45,000 per month',
      'Duration: 6 months',
      'Skills: Python, GIS, Computer Vision',
      '',
      'About the role:',
      'Map crop health from satellite images and explain the maps to farmers.',
      // A new reference each run, so a rerun is not rejected as an exact duplicate.
      `Reference: KA-${Date.now() % 100000}`,
    ].join('\n'),
  );
  await page.getByRole('button', { name: 'Read posting' }).click();
  await expect(page.getByText('Review before publishing')).toBeVisible({ timeout: 20_000 });
  await settle(page);
  await page.screenshot({ path: `${OUT}/admin-review.png` });
  await shot(page, '/admin', 'admin-dashboard');
  await shot(page, '/admin/postings', 'admin-postings');
  await page.goto('/admin/evals');
  await page.getByRole('button', { name: 'Run retrieval eval' }).click();
  await expect(page.getByRole('table').first()).toBeVisible({ timeout: 60_000 });
  await settle(page);
  await page.screenshot({ path: `${OUT}/admin-evals.png` });
  await shot(page, '/admin/usage', 'admin-usage');
});
