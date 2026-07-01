# Security Policy

## Supported versions

This is a community integration under active development. Security fixes are
applied to the latest release on the `main` branch only.

| Version | Supported |
| ------- | --------- |
| latest (`main`) | :white_check_mark: |
| older releases | :x: |

## Reporting a vulnerability

Please **do not** open a public issue for security vulnerabilities.

Instead, report privately using GitHub's
[private vulnerability reporting](https://github.com/raunosr/ha-amazing-linktap/security/advisories/new).
You should receive an acknowledgement within a few days. Once a fix is
available, a new release will be published and the advisory disclosed.

## Scope and notes

- This integration talks to a LinkTap gateway **only over the local network**
  (HTTP API on the LAN). It sends no data to third-party or cloud services.
- The push endpoint (`/api/linktap/push`) is intentionally unauthenticated
  because the gateway cannot present a Home Assistant token. It only acts on
  payloads that match a known gateway/device ID. Expose Home Assistant to the
  internet only behind a reverse proxy / VPN, never directly.
- Do not commit secrets (tokens, passwords, gateway credentials). Diagnostics
  output is redacted, and secret scanning with push protection is enabled on
  this repository.
