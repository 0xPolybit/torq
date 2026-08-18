# Security Policy

## Supported versions

Torq is pre-alpha. Only the latest commit on `main` receives security fixes.
No tagged releases exist yet, so no stable patch line is guaranteed.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security-sensitive reports.

Email security reports to the maintainer address listed in
`pyproject.toml`'s `authors` field (or the GitHub profile of the repository
owner). Use the subject line `torq security: <short summary>`.

A good report includes:

- A clear description of the issue and impact.
- Reproduction steps or a minimal proof of concept.
- Affected version/commit SHA.
- Whether you would like public acknowledgement.

We aim to acknowledge new reports within 7 days. Fix timelines depend on
severity; we will coordinate disclosure with you.

## Scope

In-scope issues include anything that can lead to:

- Remote code execution via crafted torrent metadata, magnet URIs, search
  results, or API payloads.
- Filesystem damage outside the intended download root.
- Loss of the user's torrent registry or resume data.
- Bypass of the local-only API authentication.
- Exposure of the daemon API token (logs, crash dumps, error pages).

Out of scope for now: issues in upstream dependencies (report those
upstream) and issues that require the user to opt-in to unsafe behavior.