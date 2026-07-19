# Security Policy

We take the security of Simulation Labs seriously.

## Reporting a vulnerability

Please **do not** open a public issue for security vulnerabilities. Instead, email
**satyam@agentmade.ai** with:

- a description of the issue and its impact,
- steps to reproduce (or a proof of concept), and
- any affected versions or components.

You'll get an acknowledgement within a few business days, and we'll coordinate a fix and
disclosure timeline with you. See [`docs/security-disclosure.md`](docs/security-disclosure.md)
for scope and what's in/out of bounds.

## Handling keys

Simulation Labs runs on **your** model provider's key — there is no Simulation Labs backend.
Keep keys in `.env` (git-ignored) or your CI secrets. Nothing leaves your machine except the
screenshots you send to the model provider you chose; see [`docs/data-policy.md`](docs/data-policy.md).
