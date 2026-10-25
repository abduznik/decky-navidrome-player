# Contributing to Navidrome Player

Thanks for helping improve the plugin. This document covers the development
setup, project rules and release flow.

## Requirements

- Node.js 22+ and pnpm 9
- Python 3.11+ (the plugin also runs on newer Python versions, including the
  3.14 runtime on some arm64 handhelds)
- A Decky Loader installation on a Deck, handheld or Linux machine for manual
  testing (optional but strongly recommended)

## Setup

```bash
pnpm install
pnpm typecheck
pnpm test:backend
pnpm build
```

`pnpm watch` rebuilds the frontend bundle on change. To test on a device from
source:

```bash
./scripts/dev-install.sh
```

This installs, typechecks, builds, runs the backend tests, packages for the
current architecture and copies the plugin to `~/homebrew/plugins`. Set
`DECKY_PLUGINS_DIR` if Decky lives elsewhere.

You can also build a zip without installing:

```bash
./scripts/package.sh arm64
```

## Repository layout

```text
src/index.tsx                 plugin entry, tab shell, download events
src/api.ts                    typed decky callables and local media URLs
src/state/player.ts           module-level <audio> player store
src/components/               NowPlaying / Library / Downloads / Settings
py_modules/plugin.py          Decky-facing async API
py_modules/subsonic.py        dependency-free Subsonic client
py_modules/cache.py           LRU cache + pinned downloads + JSON manifest
py_modules/downloads.py       background download worker
py_modules/server.py          loopback media server with Range support
py_modules/config.py          settings validation and persistence
tests/                        backend unittest suite, no external services
scripts/                      package / deploy / dev-install
```

## Design rules

Please keep these invariants when changing code:

1. **No native binaries, no architecture-specific dependencies.** The plugin
   must run unchanged on arm64 and x86_64. Use the Python standard library for
   backend work, and do not pin `@rollup/rollup-linux-x64-*` or similar
   platform packages in `package.json`.
2. **Pinned downloads are sacred.** Automatic cache entries are LRU-evicted;
   manual downloads (`pinned: true`) must never be deleted automatically. The
   UI may show an over-limit state instead.
3. **Keep the default cache at 1 GiB.** New installs must start at
   `1024 ** 3` bytes. The UI exposes 0.25–32 GB; the backend clamps to
   64 MB–512 GB.
4. **Never expose credentials to the frontend media URLs.** Playback and cover
   art always go through the tokenized loopback server. Subsonic requests use
   `md5(password + salt)`, not the raw password.
5. **Do not block the Decky event loop.** Network and disk calls from
   `py_modules/plugin.py` go through `asyncio.to_thread`.
6. **Controller-first UI.** Every action must be reachable with the D-pad and
   A/B buttons. Use `Focusable`-based components (`ActionButton`, `ButtonRow`,
   `IconButton`, `SongRow`) and never raw `<button>` elements. A horizontal
   group of buttons must be wrapped in a `flow-children="row"` group so the
   user can leave it vertically.
7. **Range requests stay supported.** Cached audio is served by
   `py_modules/server.py`; preserve the `Range`/`Content-Range` behavior or
   seeking breaks.

## Adding a backend method

1. Add the async method to `py_modules/plugin.py`.
2. Add a typed callable in `src/api.ts`.
3. Add or update tests in `tests/` (use `FakeClient` / `FakeResponse` rather
   than a live server).
4. Run `pnpm typecheck`, `pnpm build` and `pnpm test:backend`.

## Tests

The backend suite is dependency-free and runs without Navidrome:

```bash
python3 -m unittest discover -s tests -v
```

CI runs the same tests on native x86_64 and arm64 runners, then builds the
plugin zip on each. A pull request that cannot pass both jobs will not be
merged.

## Release process

1. Bump `version` in `package.json`.
2. Add a section to `CHANGELOG.md`.
3. Commit and push to `main`.
4. Create and push an annotated tag:

   ```bash
   git tag -a v0.1.3 -m "Navidrome Player 0.1.3"
   git push origin main v0.1.3
   ```

5. The release workflow builds both architectures, publishes the zips and
   `SHA256SUMS`. Do not upload artifacts manually; tags are the source of truth.

## Pull request checklist

- [ ] `pnpm typecheck` passes
- [ ] `pnpm test:backend` passes
- [ ] `pnpm build` passes
- [ ] No native binary or platform-specific dependency was added
- [ ] New actions are focusable and rows can be exited with the D-pad
- [ ] Cache/download behavior keeps pinned files safe
- [ ] README or CHANGELOG updated when user-visible behavior changes
