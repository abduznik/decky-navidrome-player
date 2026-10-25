# Changelog

## 0.1.3

- Fixed album filtering: the dropdown is now a grid of controller-friendly
  filter buttons, so choosing **Recently added / Recently played / Most played /
  Random / By artist / Alphabetical** no longer closes or resets the plugin and
  the list refreshes in place.
- The Library remembers whether playlists should be shown. Toggle it from the
  Library or Settings; persisted as `show_playlists` in the settings file.
- Added a download queue panel in the Offline tab with queued/downloading/done/
  failed states, per-track progress and error messages. Removed per-download
  completion/failure toasts to avoid notification spam; the queue badge and
  panel carry that information instead.
- Backend: `get_download_queue`, `clear_download_queue`, queue state tracking in
  the download worker, and tests for queue snapshots/failures (39 tests total).

## 0.1.2

- Added a verified Retroid Pocket Nova (arm64) screenshot to the README and
  release notes.
- Repository polish: contributor guide, security policy, issue/PR templates,
  editor/git attributes, architecture and release documentation.
- Packaging now ships the full `assets/` directory so README images work from
  an installed plugin. No runtime behavior changes.

## 0.1.1

- Always return to the Player tab after the first successful login; the player
  is the default tab whenever the plugin opens while configured.
- Password field is masked by default using `-webkit-text-security`, which
  works even on Steam clients where `bIsPassword` is ignored.
- Multi-button rows are now explicit `flow-children="row"` focus groups with
  `Focusable` action buttons, so controller navigation can enter and leave
  each row in all four directions.
- Album filters: recently added, recently played, most played, random,
  artist and alphabetical.

## 0.1.0

- Initial release: Navidrome/Subsonic client, QAM player, volume, shuffle,
  repeat, search, playlists, albums, 1 GiB default LRU cache, pinned manual
  downloads, offline playback, native arm64 and x86_64 CI builds.
