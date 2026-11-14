# Security and privacy

## Public site

The observer serves public observations only. It has a narrow GET/static allowlist and denies every POST. No private accounts, portfolios, original/managed/archive ledgers, AI invocations, admin sessions, transport tokens or signed app downloads are exposed.

The public website has no visitor login. Its data is intentionally public, and browser watchlist pins stay on the visitor's device. Do not submit credentials or personal account information.

Host checks permit loopback development hosts or the exact current Codespace forwarding hostname. Invalid symbols/queries do not become SQL or filesystem paths. Provider text is escaped in the browser; outgoing publisher links are restricted to HTTP/HTTPS and use noreferrer/noopener.

## Repository contents

Included: portable source, native source, tests, public vendor fixtures/licenses, roadmap, architecture and selected isolated verification summaries.

Excluded: data/, real databases/ledgers, credentials, private signing keys, APKs, backups, private deployment memory, delivery receipts, raw live financial reports, original private Git history and original machine login files.

Personal transport IDs are not embedded. Owner transport requires explicit private configuration and is not an observer endpoint. A disabled compatibility shim cannot connect an external AI API or accept API keys.

The detailed public planning export generalizes personal paths and contacts. Do not equate its modified document hashes with original private review hashes.

## Optional full backend and CLI use

The wider backend is a private, local paper-research system, not a public multi-user financial service. It has separate account/risk/privacy controls that are intentionally not exposed by the observer. Real-money brokerage is absent.

Developer CLI login is separate from GitHub login. Never put provider login files or secrets in a commit. No source-file or runtime setting change should infer permission to resume a personal deployment.

## Reporting

Use a GitHub issue for a non-sensitive report. Do not post secrets, private account data, personal deployment snapshots or exploit credentials in an issue.
