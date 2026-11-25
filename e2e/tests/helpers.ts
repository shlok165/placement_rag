import { expect, type Page } from '@playwright/test';

export const PASSWORD = 'demo-pass-2026';
export const COORDINATOR = 'coordinator@example.com';
export const STUDENT = 'asha@example.com';

export async function signIn(page: Page, email: string) {
  await page.goto('/login');
  await page.getByLabel('Institute email').fill(email);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).not.toHaveURL(/login/);
}

/** A short random word, so repeated runs on the same database never collide. */
export function unique(): string {
  const letters = 'abcdefghijklmnopqrstuvwxyz';
  return Array.from({ length: 8 }, () => letters[Math.floor(Math.random() * 26)]).join('');
}

export async function register(page: Page) {
  const email = `student-${unique()}@example.com`;
  await page.goto('/register');
  await page.getByLabel('Full name').fill('Synthetic Student');
  await page.getByLabel('Institute email').fill(email);
  await page.getByLabel('Password').fill('long-enough-1');
  await page.getByRole('button', { name: 'Create account' }).click();
  await expect(page).toHaveURL(/onboarding/);
  return email;
}
