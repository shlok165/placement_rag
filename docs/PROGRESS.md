# Progress

## M0 Foundations

Compose stack (`db`, `backend`, `frontend`), initial migration with every table, health and metrics
endpoints, JSON logs, design tokens and base components, login page, CI skeleton. Verified from a
clean state: all services healthy and the login page is served.

## M1 Auth and roles

Email and password accounts (argon2), server-side sessions, CSRF tokens, login rate limiting,
institute email check, coordinator invites, route guards on both sides. One test walks every admin
route as a student (403) and as a visitor (401); another checks that every other route needs a
session.
