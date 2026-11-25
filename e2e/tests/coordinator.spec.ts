import { expect, test } from '@playwright/test';
import { COORDINATOR, signIn, STUDENT, unique } from './helpers';

test('a pasted posting is reviewed, published and then found by a student', async ({
  page,
  browser,
}) => {
  const word = unique();
  const company = `Company ${word}`;
  await signIn(page, COORDINATOR);
  await page.getByRole('link', { name: 'Add posting' }).first().click();
  await page.getByRole('tab', { name: 'Paste text' }).click();
  await page.getByLabel('Posting text').fill(
    [
      `Company: ${company}`,
      'Role: Hydrology Data Intern',
      'Location: Chandigarh',
      'Stipend: 30,000 per month',
      'Deadline: 2031-05-01',
      'Skills: Python, GIS',
      '',
      'About the role:',
      `Model river flow for the ${word} basin and publish maps.`,
    ].join('\n'),
  );
  await page.getByRole('button', { name: 'Read posting' }).click();

  await expect(page.getByText('Review before publishing')).toBeVisible({ timeout: 20_000 });
  await expect(page.getByLabel(/^Company/)).toHaveValue(company);
  await expect(page.getByRole('region', { name: 'Original text' })).toContainText(word);
  await page.getByRole('button', { name: 'Publish' }).click();
  await expect(page.getByText('Live', { exact: true })).toBeVisible({ timeout: 20_000 });

  const context = await browser.newContext();
  const student = await context.newPage();
  await signIn(student, STUDENT);
  await student.goto(`/jobs?q=${word}&personal=0`);
  await expect(student.getByRole('link', { name: 'Hydrology Data Intern' }).first()).toBeVisible();
  await context.close();

  await page.getByRole('button', { name: 'More actions' }).click();
  await page.getByRole('menuitem', { name: 'Archive' }).click();
  await page.getByRole('button', { name: 'Archive' }).click();
  await expect(page.getByText('Archived', { exact: true }).first()).toBeVisible();
  await page.getByRole('button', { name: 'Undo' }).click();
  await expect(page.getByText('Live', { exact: true })).toBeVisible();
});

test('an exact duplicate is refused with a link to the original', async ({ page }) => {
  const word = unique();
  const text = `Company: Dup ${word}\nRole: QA Intern\nDeadline: 2031-01-01\nAbout the role:\nTest things.`;
  await signIn(page, COORDINATOR);
  for (const attempt of [1, 2]) {
    await page.goto('/admin/postings/new?tab=paste');
    await page.getByLabel('Posting text').fill(text);
    await page.getByRole('button', { name: 'Read posting' }).click();
    if (attempt === 1) await expect(page).toHaveURL(/postings\/\d+/);
  }
  await expect(page.getByText(/already added/)).toBeVisible();
  await page.getByRole('link', { name: /Open posting/ }).click();
  await expect(page).toHaveURL(/postings\/\d+/);
});

test('the postings table filters and shows a card layout on phones', async ({ page }) => {
  await signIn(page, COORDINATOR);
  await page.goto('/admin/postings');
  await page.getByLabel('Search').fill('structural');
  await expect(page.getByRole('table').getByRole('link').first()).toContainText(/Structural/);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('table')).toBeHidden();
  await expect(page.getByRole('listitem').getByRole('link').first()).toBeVisible();
});
