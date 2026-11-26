# Security and privacy review

Reviewed against the code before release. Each row names where it is enforced and tested.

| Area | What is done | Where | Test |
|---|---|---|---|
| Passwords | argon2, length and mix rules, same reply and timing for unknown accounts | `core/security.py` | `test_auth.py` |
| Registration | An address that already has an account gets a neutral refusal, after the same password hashing as a new one | `api/auth.py` | `test_auth.py` |
| Sessions | Opaque token, only its hash stored, HTTP-only, SameSite, Secure in production | `core/security.py` | `test_auth.py` |
| CSRF | Per-session token required on every unsafe request | `api/deps.py` | `test_auth.py` |
| Brute force | Progressive delay per account and address pair (five free tries, then 1 s doubling to 15 minutes), plus a cap per address across accounts | `core/security.py` | `test_auth.py` |
| Client address | `X-Forwarded-For` is believed only when the direct peer is in `TRUSTED_PROXIES`; otherwise the peer address is used | `api/deps.py` | `test_auth.py` |
| Roles | Every admin route is checked as a student (403) and a visitor (401) | `api/deps.py` | `test_auth.py` |
| Isolation | Saves, applications, searches, notifications, chats, actions and memory are owner-only | `api/student.py`, `api/chat.py` | `test_student.py`, `test_chat.py` |
| Uploads | Size limit, type read from content, zip size limit, generated file names | `core/uploads.py`, `core/storage.py` | `test_ingest.py` |
| Links | Only http and https links are accepted or rendered | `schemas/jobs.py`, `Answer.tsx` | `test_ingest.py`, `copilot.test.tsx` |
| SQL | Bound parameters only; search input is escaped for `tsquery` | `search/retrieval.py` | `test_search.py` |
| Browser | CSP without inline scripts, no framing, no sniffing | `Caddyfile` | checked by hand |
| Resume data | Identifiers removed before storage and before any LLM call | `core/redaction.py` | `test_student.py` |
| Consent | No LLM use of personal text before agreement; can be withdrawn | `api/chat.py`, `api/profile.py` | `test_chat.py`, `test_student.py` |
| Deletion | Removes every row that belongs to the account, its files and cached answers | `api/profile.py` | `test_student.py` |
| Staff access | Totals by default; opening a student needs a reason and is logged | `api/admin_insights.py` | `test_ingest.py` |
| Agent | No user id in any tool, writes need confirmation, posting text is treated as data | `agent/tools.py` | `test_agent.py` |
| Drafts | Skills, organisations, projects and numbers must come from the profile or the posting; an unchecked draft is never shown, and nothing is sent | `agent/outreach.py` | `test_outreach.py` |
| Behaviour events | Kind, posting and time only, no text; owner-only; deleted with the account; in the export | `api/events.py` | `test_taste.py` |
| Calendar feed | 256-bit secret in the URL, stored as a hash, replaced or revoked by the student; feed lists only saved and tracked deadlines | `api/calendar.py` | `test_calendar.py` |
| Agent traces | Coordinators see their own turns and turns a student rated and chose to share; opening a shared one is audited; sharing can be withdrawn | `api/admin_traces.py` | `test_traces.py` |
| Secrets | Key read from the environment as a secret, sent only to the configured base URL | `llm/client.py` | `test_llm.py` |
| Logs | Structured, no bodies, no exception messages, no personal data | `core/logging.py` | reviewed |
| Containers | Non-root; in production also read-only, no capabilities, no new privileges | `docker-compose.prod.yml` | run by hand |

## Known limits

- **Redaction is pattern based.** It removes the identifiers in the test suite and can miss unusual
  formats, or names of other people. Students see the exact stored text and can remove the resume.
- **The original resume file is kept** on the files volume until it is replaced, removed or the
  account is deleted. Disk encryption is left to the host.
- **Email addresses are not verified,** because email sending is out of scope. Only the domain is
  checked, so a deployment should add verification or single sign-on before real use.
- **Registration can still confirm that an account exists.** The reply no longer says so and takes
  the same time, but a new address still succeeds and signs in while a taken one is refused, so
  the outcome differs. Closing that needs email verification. What changed: no "already exists"
  code or text, equal timing, and the per-address limit on registration attempts.
- **Sign-in across many addresses.** The delay is per account and address, so a student cannot be
  locked out from someone else's machine. The cost is that an attacker with many addresses gets
  five free guesses at each. Strong password rules and the per-address cap limit this.
- **A calendar link is a bearer secret.** Anyone who has it can read those deadlines (titles,
  companies, dates, nothing else) until the student makes a new link or turns it off.
- **Rated answers are visible to coordinators** without a name. A student who types personal details
  into a question and rates the answer shares them. The rating dialog says so.
- **Provider cache.** The provider may answer identical requests from a shared cache.
- Audit rows about a deleted student keep the numeric id only.
