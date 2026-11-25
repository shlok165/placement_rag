# Security and privacy review

Reviewed against the code before release. Each row names where it is enforced and tested.

| Area | What is done | Where | Test |
|---|---|---|---|
| Passwords | argon2, length and mix rules, same reply and timing for unknown accounts | `core/security.py` | `test_auth.py` |
| Sessions | Opaque token, only its hash stored, HTTP-only, SameSite, Secure in production | `core/security.py` | `test_auth.py` |
| CSRF | Per-session token required on every unsafe request | `api/deps.py` | `test_auth.py` |
| Brute force | Attempts limited per account and per address | `core/security.py` | `test_auth.py` |
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
- **Rated answers are visible to coordinators** without a name. A student who types personal details
  into a question and rates the answer shares them. The rating dialog says so.
- **Provider cache.** The provider may answer identical requests from a shared cache.
- Audit rows about a deleted student keep the numeric id only.
