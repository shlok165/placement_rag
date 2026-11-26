import { expect, test } from '@playwright/test';
import { freshStudent, register, signIn, STUDENT } from './helpers';

test('a new student onboards, searches, saves and tracks', async ({ page }) => {
  await register(page);

  await expect(page.getByText('Step 1 of 3')).toBeVisible();
  await page.getByRole('button', { name: 'Skip this step' }).click();
  await page.getByLabel('Skills').fill('Python');
  await page.getByLabel('Skills').press('Enter');
  await page.getByLabel('Skills').fill('Machine Learning');
  await page.getByLabel('Skills').press('Enter');
  await page.getByRole('button', { name: 'Save and continue' }).click();
  await page.getByLabel('Roles').fill('Machine Learning');
  await page.getByLabel('Roles').press('Enter');
  await page.getByLabel('Internship', { exact: true }).click();
  await page.getByRole('button', { name: 'Save and finish' }).click();

  await expect(page.getByRole('heading', { name: 'Recommended for you' })).toBeVisible();
  await expect(page.getByText('Ranked by your skills')).toBeVisible();

  await page.getByRole('link', { name: 'Browse', exact: true }).click();
  await page.getByRole('searchbox').fill('train models that learn from behaviour');
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  // The search is in the address bar; wait for it before acting on results.
  await expect(page).toHaveURL(/q=train/);
  const first = page.getByRole('region', { name: 'Results' }).getByRole('heading', { level: 3 }).first();
  await expect(first).toContainText(/ML|Machine Learning|AI/);

  await page.getByRole('button', { name: /^Save:/ }).first().click();
  await expect(page.getByRole('button', { name: /^Remove from saved/ }).first()).toBeVisible();

  await first.getByRole('link').click();
  await expect(page.getByRole('heading', { name: 'Why this fits' })).toBeVisible();
  await page.getByRole('button', { name: 'I have applied' }).click();
  await expect(page.getByText('Moved to Applied')).toBeVisible();

  await page.getByRole('link', { name: 'Applications', exact: true }).click();
  await page.getByRole('button', { name: 'List' }).click();
  await page.getByRole('combobox', { name: /^Stage for/ }).click();
  await page.getByRole('option', { name: 'Interview' }).click();
  await expect(page.getByText('Moved to Interview')).toBeVisible();
  await page.getByRole('button', { name: 'Undo' }).first().click();
  await expect(page.getByRole('combobox', { name: /^Stage for/ })).toContainText('Applied');

  await page.getByRole('link', { name: 'Saved', exact: true }).click();
  await expect(page.getByRole('button', { name: /^Remove from saved/ })).toHaveCount(1);
});

test('a student cannot open the coordinator portal', async ({ page }) => {
  await signIn(page, STUDENT);
  for (const path of ['/admin', '/admin/postings', '/admin/usage']) {
    await page.goto(path);
    await expect(page.getByText('403: This area is for CAPS coordinators only')).toBeVisible();
  }
  const response = await page.request.get('/api/admin/jobs');
  expect(response.status()).toBe(403);
});

test('visitors are sent to sign in and returned afterwards', async ({ page }) => {
  await page.goto('/applications');
  await expect(page).toHaveURL(/login\?next=%2Fapplications/);
  await page.getByLabel('Institute email').fill(STUDENT);
  await page.getByLabel('Password').fill('demo-pass-2026');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/applications$/);
});

test('filters survive reload and can be removed one by one', async ({ page }) => {
  await signIn(page, STUDENT);
  await page.goto('/jobs?type=internship&remote=1');
  const chips = page.getByRole('button', { name: /Remove filter/ });
  await expect(chips).toHaveCount(2);
  await page.reload();
  await expect(chips).toHaveCount(2);
  await chips.first().click();
  await expect(chips).toHaveCount(1);
});

test('an unusual search explains that matches are weak', async ({ page }) => {
  await signIn(page, STUDENT);
  await page.goto('/jobs?q=pizza+recipe');
  await expect(
    page.getByText('Nothing is a close match').or(page.getByText('No postings match')),
  ).toBeVisible();
});

test('a student can delete the account', async ({ page }) => {
  const email = await freshStudent(page);
  await page.goto('/account?tab=privacy');
  await page.getByRole('button', { name: 'Delete my account' }).click();
  await page.getByLabel('Password').fill('long-enough-1');
  await page.getByRole('button', { name: 'Delete everything' }).click();
  await expect(page).toHaveURL(/login/);
  await page.getByLabel('Institute email').fill(email);
  await page.getByLabel('Password').fill('long-enough-1');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('alert')).toContainText('do not match');
});
