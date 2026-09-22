# Security

## Reporting a vulnerability

Report security issues in this SDK, or anywhere else in the Dregs service, to
[security@dregs.com](mailto:security@dregs.com). Dregs's
[security page](https://dregs.com/legal/security/) describes how reports are handled. Please
don't open a public GitHub issue for security reports.

## Handling keys

- The **secret key** (`sk_…`) this SDK authenticates with acts as an administrator of the team
  that owns it. Treat it like a password: keep it in your server's environment or secret manager,
  never in source control, and never anywhere a browser can reach it.
- The **public key** (`pk_…`) is the one that belongs in a browser. It is a different credential
  and cannot read identities or scores. This SDK refuses one with an explanation rather than
  letting you discover the difference through confusing 401s.
- A credential's **webhook signing secret** is a third value again. It proves a payload came from
  Dregs; it does not authenticate you to Dregs. Rotate it separately.
- Revoke a leaked credential under **Settings → Credentials** in the dashboard. Revocation takes
  effect immediately.

## Verifying webhooks

Verify every webhook before acting on it, against the **raw request body**. `dregs.webhooks.verify`
does the HMAC comparison in constant time and rejects stale payloads as replays. Verifying a
re-serialized dict instead of the received bytes will not match, and working around that by
skipping verification would leave the endpoint open to anyone who learns its URL.

## Treating scored data as untrusted

The identity attributes, display names, and event data this SDK returns were written by the users
being scored. Treat them as untrusted input: escape them before rendering, and do not feed them to
an LLM or an agent as instructions. This matters more than usual here, because the people writing
that data are, by construction, the ones trying to get something past you.
