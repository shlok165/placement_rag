import { expect, type Page } from '@playwright/test';

export const PASSWORD = 'demo-pass-2026';
export const COORDINATOR = 'coordinator@example.com';
export const STUDENT = 'asha@example.com';

async function skipTour(page: Page) {
  await page.addInitScript(() => localStorage.setItem('tour-seen', '1'));
}

export async function signIn(page: Page, email: string) {
  await skipTour(page);
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

/** Registers a student and skips onboarding. */
export async function freshStudent(page: Page) {
  const email = await register(page);
  for (let step = 0; step < 3; step++)
    await page.getByRole('button', { name: 'Skip this step' }).click();
  await expect(page.getByRole('heading', { name: /^Hello/ })).toBeVisible();
  return email;
}

export async function register(page: Page) {
  const email = `student-${unique()}@example.com`;
  await skipTour(page);
  await page.goto('/register');
  await page.getByLabel('Full name').fill('Synthetic Student');
  await page.getByLabel('Institute email').fill(email);
  await page.getByLabel('Password').fill('long-enough-1');
  await page.getByRole('button', { name: 'Create account' }).click();
  await expect(page).toHaveURL(/onboarding/);
  return email;
}
