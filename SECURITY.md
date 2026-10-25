# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Instead use
GitHub's private vulnerability reporting:

1. Open the repository's **Security** tab.
2. Click **Advisories → Report a vulnerability**.
3. Include affected version, steps to reproduce and impact.

You will get a response as soon as possible. This is a hobby plugin, so please
allow a reasonable amount of time before disclosing publicly.

## Security model and known limitations

- **Password storage.** The Navidrome password is stored in the plugin's local
  settings JSON because the Subsonic API requires deriving
  `md5(password + salt)` for every request. It is not sent to the frontend or
  any third party, but it is plain text on disk. Protect the settings directory
  and use a dedicated Navidrome account if that matters to you.
- **Loopback media server.** Cached tracks are served from `127.0.0.1` on a
  random port with a random per-session token in the path. Any local process
  that can read the token can read the cache; the server is not exposed on the
  network.
- **TLS.** Python's default certificate verification is used for HTTPS
  Navidrome servers. Self-signed certificates are not supported.
- **No telemetry.** The plugin talks only to the configured Navidrome server.
- **Scrobbling** sends the played song id and submission flag to the same
  server, only when online.

## Supported versions

Only the latest tagged release receives security fixes.
