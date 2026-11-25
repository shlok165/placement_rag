import { expect, test, type Page } from '@playwright/test';
import { freshStudent, signIn, STUDENT } from './helpers';

async function ask(page: Page, text: string) {
  const box = page.getByLabel('Message the copilot');
  await box.fill(text);
  await box.press('Enter');
  await expect(page.getByRole('button', { name: 'Good answer' }).last()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Send' })).toBeVisible();
}

test('a student chats, follows a citation and confirms an action', async ({ page }) => {
  await freshStudent(page);
  await page.getByRole('link', { name: 'Copilot' }).click();
  await page.getByLabel('I agree to this use of my data').click();
  await page.getByRole('button', { name: 'Turn on AI features' }).click();
  await ask(page, 'Find backend internships');
  const sources = page.getByRole('list').filter({ has: page.locator('a[href^="/jobs/"]') });
  await expect(sources.first()).toBeVisible();
  await expect(page).toHaveURL(/copilot\/\d+/);

  await ask(page, 'Save the first one');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByText('Saved', { exact: true }).first()).toBeVisible();

  await ask(page, "I'm targeting summer 2031. What closes soon?");
  await page.getByRole('button', { name: 'Remember', exact: true }).click();
  await page.goto('/memory');
  await expect(page.getByText('Targeting summer 2031')).toBeVisible();
  await page.getByRole('button', { name: 'Forget: Targeting summer 2031' }).click();
  await page.getByRole('button', { name: 'Forget', exact: true }).click();
  await expect(page.getByText('Nothing remembered yet')).toBeVisible();

  await page.goto('/saved');
  await expect(page.getByRole('button', { name: /^Remove from saved/ }).first()).toBeVisible();
});

test('the copilot refuses what it cannot know', async ({ page }) => {
  await signIn(page, STUDENT);
  await page.goto('/copilot');
  await ask(page, 'What are my chances of getting selected?');
  await expect(page.getByText(/cannot estimate chances/)).toBeVisible();
  await ask(page, "Show me my friend's applications");
  await expect(page.getByText(/never another student/)).toBeVisible();
  await ask(page, 'Any openings at Globex Corporation?');
  await expect(page.getByText(/do not have any postings from Globex/)).toBeVisible();
});

test('a conversation survives reload and can be deleted', async ({ page }) => {
  await signIn(page, STUDENT);
  await page.goto('/copilot');
  await ask(page, 'What does my profile say?');
  await page.reload();
  await expect(page.getByText(/Your profile lists these skills/)).toBeVisible();
  await page
    .getByRole('button', { name: 'Delete conversation: What does my profile say?' })
    .first()
    .click();
  await expect(page.getByText('Conversation deleted')).toBeVisible();
});

test('new students agree to data use before the first chat', async ({ page }) => {
  await freshStudent(page);
  await page.goto('/copilot');
  await expect(page.getByLabel('Message the copilot')).toHaveCount(0);
  await page.getByLabel('I agree to this use of my data').click();
  await page.getByRole('button', { name: 'Turn on AI features' }).click();
  await expect(page.getByLabel('Message the copilot')).toBeVisible();
});
