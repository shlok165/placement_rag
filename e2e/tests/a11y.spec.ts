import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { COORDINATOR, signIn, STUDENT } from './helpers';

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'];

async function check(page: Page, path: string) {
  await page.goto(path);
  await page.waitForLoadState('networkidle');
  const { violations } = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  const found = violations.map((v) => `${path} ${v.id}: ${v.nodes.map((n) => n.target).join(', ')}`);
  expect(found).toEqual([]);
}

const studentPages = [
  '/',
  '/jobs',
  '/jobs/1',
  '/copilot',
  '/applications',
  '/saved',
  '/notifications',
  '/account',
  '/account?tab=preferences',
  '/account?tab=privacy',
  '/memory',
  '/help',
  '/privacy',
  '/survey',
];
const adminPages = [
  '/admin',
  '/admin/postings',
  '/admin/postings/1',
  '/admin/postings/new',
  '/admin/postings/new?tab=upload',
  '/admin/students',
  '/admin/evals',
  '/admin/evals?tab=cases',
  '/admin/usage',
  '/admin/announcements',
  '/admin/team',
];

for (const colorScheme of ['light', 'dark'] as const) {
  test(`axe finds nothing on public and student pages, ${colorScheme}`, async ({ page }) => {
    test.setTimeout(120_000);
    await page.emulateMedia({ colorScheme, reducedMotion: 'reduce' });
    await check(page, '/login');
    await check(page, '/register');
    await signIn(page, STUDENT);
    for (const path of studentPages) await check(page, path);
  });

  test(`axe finds nothing on coordinator pages, ${colorScheme}`, async ({ page }) => {
    test.setTimeout(120_000);
    await page.emulateMedia({ colorScheme, reducedMotion: 'reduce' });
    await signIn(page, COORDINATOR);
    for (const path of adminPages) await check(page, path);
  });
}

test('axe finds nothing on a phone, with the menu and dialogs open', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await signIn(page, STUDENT);
  for (const path of ['/', '/jobs', '/jobs/1', '/copilot', '/applications'])
    await check(page, path);
  await page.getByRole('button', { name: 'Open menu' }).click();
  await expect(page.getByRole('dialog', { name: 'Menu' })).toBeVisible();
  expect((await new AxeBuilder({ page }).withTags(TAGS).analyze()).violations).toEqual([]);
  await page.keyboard.press('Escape');
  await page.keyboard.press('Control+k');
  await expect(page.getByPlaceholder('Type a page or a posting')).toBeFocused();
  expect((await new AxeBuilder({ page }).withTags(TAGS).analyze()).violations).toEqual([]);
});

test('no page scrolls sideways on a narrow phone', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 });
  await signIn(page, STUDENT);
  for (const path of studentPages) {
    await page.goto(path);
    await page.waitForLoadState('networkidle');
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow, path).toBeLessThanOrEqual(0);
  }
});

test('targets are at least 24 pixels', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, STUDENT);
  for (const path of ['/', '/jobs', '/jobs/1', '/copilot', '/applications', '/account']) {
    await page.goto(path);
    await page.waitForLoadState('networkidle');
    const small = await page.$$eval(
      'button, input:not([type=file]), [role=combobox], [role=checkbox], [role=switch], [role=tab]',
      (nodes) =>
        nodes
          .map((n) => ({ box: n.getBoundingClientRect(), html: n.outerHTML.slice(0, 120) }))
          .filter(({ box }) => box.width > 1 && box.height > 1)
          .filter(({ box }) => box.width < 24 || box.height < 24)
          .map(({ html }) => html),
    );
    expect(small, path).toEqual([]);
  }
});

test('the main student journey works with the keyboard alone', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('tour-seen', '1'));
  await page.goto('/login');
  await page.keyboard.press('Tab');
  await expect(page.getByLabel('Institute email')).toBeFocused();
  await page.keyboard.type(STUDENT);
  await page.keyboard.press('Tab');
  await page.keyboard.type('demo-pass-2026');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: /^Hello/ })).toBeVisible();

  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#main')).toBeFocused();

  await page.keyboard.press('Control+k');
  await page.keyboard.type('browse');
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/jobs$/);
  await expect(page.getByRole('searchbox')).toBeVisible();

  await page.keyboard.press('/');
  await expect(page.getByRole('searchbox')).toBeFocused();
  await page.keyboard.type('firmware');
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/q=firmware/);

  const firstJob = page.getByRole('region', { name: 'Results' }).getByRole('heading', { level: 3 });
  await firstJob.first().getByRole('link').focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Why this fits' })).toBeVisible();

  // A repeated run finds the posting already tracked.
  const stage = page.getByRole('combobox', { name: 'Stage' });
  const interested = page.getByRole('button', { name: 'I am interested' });
  await expect(stage.or(interested)).toBeVisible();
  if (await interested.isVisible()) {
    await interested.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByText('Moved to Interested')).toBeVisible();
  }

  await stage.focus();
  await page.keyboard.press('Enter');
  await page.keyboard.type('Interview');
  await page.keyboard.press('Enter');
  await expect(stage).toContainText('Interview');
});

test('focus is always visible', async ({ page }) => {
  await page.goto('/login');
  for (let i = 0; i < 4; i++) {
    await page.keyboard.press('Tab');
    const outline = await page.evaluate(() => {
      const style = getComputedStyle(document.activeElement!);
      return { width: parseFloat(style.outlineWidth), style: style.outlineStyle };
    });
    expect(outline.style).not.toBe('none');
    expect(outline.width).toBeGreaterThanOrEqual(2);
  }
});
