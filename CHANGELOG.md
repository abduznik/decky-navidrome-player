# Changelog

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
