# Security Policy

## Reporting a vulnerability

Please report security issues **privately** — do not open a public issue or pull
request for anything security-sensitive.

- Preferred: open a [GitHub private security advisory](https://github.com/emuehlstein/chioff-rns/security/advisories/new).
- Alternatively, contact the maintainer directly (see the GitHub profile for
  `emuehlstein`).

Include enough detail to reproduce the issue (affected file, steps, and impact).
We will acknowledge your report and keep you updated on remediation.

## Scope

This repository operates a public Reticulum transport node. Relevant trust
boundaries:

- **Deploy pipeline** — pushes to `main` are deployed to the production node via
  GitHub Actions over SSH. Changes to `main` run with elevated privileges on the
  server, so all changes go through reviewed pull requests.
- **Public status page / visualizer** — anonymizes peer IPs and destination
  hashes when `public_mode = true`. Only nodes explicitly listed in
  `consented-nodes.config` are shown un-anonymized.
- **Network data** — node names and announce data originate from untrusted mesh
  peers and are treated as such.

## Supported versions

This is a single-deployment project; only the latest `main` is supported.
