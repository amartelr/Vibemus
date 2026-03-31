"""Tests for the Vibemus CLI parser and legacy alias rewriter."""

import warnings

import pytest

from src.cli.parser import build_parser, rewrite_legacy_args


@pytest.fixture
def parser():
    return build_parser()


# ── Subcommand parsing ────────────────────────────────────────────────────────


class TestSubcommands:
    """Verify that the parser accepts all documented subcommands."""

    def test_artist_add(self, parser):
        args = parser.parse_args(["artist", "add", "Radiohead", "--playlist", "Rock"])
        assert args.command == "artist"
        assert args.action == "add"
        assert args.name == "Radiohead"
        assert args.playlist == "Rock"

    def test_artist_add_no_playlist(self, parser):
        args = parser.parse_args(["artist", "add", "Radiohead"])
        assert args.command == "artist"
        assert args.action == "add"
        assert args.name == "Radiohead"
        assert args.playlist is None

    def test_artist_remove(self, parser):
        args = parser.parse_args(["artist", "remove", "Radiohead"])
        assert args.command == "artist"
        assert args.action == "remove"
        assert args.name == "Radiohead"

    def test_artist_list(self, parser):
        args = parser.parse_args(["artist", "list"])
        assert args.command == "artist"
        assert args.action == "list"

    def test_artist_import(self, parser):
        args = parser.parse_args(["artist", "import"])
        assert args.command == "artist"
        assert args.action == "import"

    def test_artist_reset_empty(self, parser):
        args = parser.parse_args(["artist", "reset-empty"])
        assert args.command == "artist"
        assert args.action == "reset-empty"

    def test_artist_archive_inactive(self, parser):
        args = parser.parse_args(["artist", "archive-inactive"])
        assert args.command == "artist"
        assert args.action == "archive-inactive"

    def test_sync_releases(self, parser):
        args = parser.parse_args(["sync", "releases"])
        assert args.command == "sync"
        assert args.action == "releases"
        assert not args.force

    def test_sync_releases_force(self, parser):
        args = parser.parse_args(["sync", "releases", "--force"])
        assert args.force is True

    def test_sync_deep(self, parser):
        args = parser.parse_args(["sync", "deep"])
        assert args.command == "sync"
        assert args.action == "deep"
        assert not args.auto

    def test_sync_deep_auto(self, parser):
        args = parser.parse_args(["sync", "deep", "--auto"])
        assert args.auto is True

    def test_sync_new_releases(self, parser):
        args = parser.parse_args(["sync", "new-releases"])
        assert args.command == "sync"
        assert args.action == "new-releases"

    def test_sync_playlist(self, parser):
        args = parser.parse_args(["sync", "playlist", "--name", "Indie"])
        assert args.command == "sync"
        assert args.action == "playlist"
        assert args.name == "Indie"

    def test_sync_playlist_skip_lastfm(self, parser):
        args = parser.parse_args(["sync", "playlist", "--skip-lastfm"])
        assert args.skip_lastfm is True

    def test_playlist_clean(self, parser):
        args = parser.parse_args(["playlist", "clean"])
        assert args.command == "playlist"
        assert args.action == "clean"

    def test_playlist_cleanup_inbox(self, parser):
        args = parser.parse_args(["playlist", "cleanup-inbox"])
        assert args.command == "playlist"
        assert args.action == "cleanup-inbox"

    def test_playlist_undo_old(self, parser):
        args = parser.parse_args(["playlist", "undo-old"])
        assert args.command == "playlist"
        assert args.action == "undo-old"

    def test_playlist_export(self, parser):
        args = parser.parse_args(["playlist", "export", "PL123"])
        assert args.command == "playlist"
        assert args.action == "export"
        assert args.playlist_id == "PL123"

    def test_playlist_export_default(self, parser):
        args = parser.parse_args(["playlist", "export"])
        assert args.playlist_id is None







    def test_system_refresh_cache(self, parser):
        args = parser.parse_args(["system", "refresh-cache"])
        assert args.command == "system"
        assert args.action == "refresh-cache"

    def test_system_auth(self, parser):
        args = parser.parse_args(["system", "auth"])
        assert args.command == "system"
        assert args.action == "auth"


# ── Legacy alias rewriting ────────────────────────────────────────────────────


class TestLegacyAliases:
    """Verify that old flags get rewritten and emit DeprecationWarning."""

    def test_list_artists(self):
        result = rewrite_legacy_args(["--list-artists"])
        assert result[:2] == ["artist", "list"]

    def test_add_artist(self):
        result = rewrite_legacy_args(["--add-artist", "Radiohead"])
        assert "artist" in result
        assert "add" in result
        assert "Radiohead" in result

    def test_add_artist_with_playlist(self):
        result = rewrite_legacy_args(
            ["--add-artist", "Radiohead", "--playlist", "Rock"]
        )
        assert "artist" in result
        assert "add" in result
        assert "Radiohead" in result
        assert "--playlist" in result

    def test_deep_sync(self):
        result = rewrite_legacy_args(["--deep-sync"])
        assert result[:2] == ["sync", "deep"]

    def test_deep_sync_auto(self):
        result = rewrite_legacy_args(["--deep-sync", "--auto"])
        assert "sync" in result
        assert "deep" in result
        assert "--auto" in result

    def test_sync_playlist(self):
        result = rewrite_legacy_args(["--sync-playlist"])
        assert result[:2] == ["sync", "playlist"]

    def test_cleanup_inbox(self):
        result = rewrite_legacy_args(["--cleanup-inbox"])
        assert result[:2] == ["playlist", "cleanup-inbox"]



    def test_empty_argv_shows_help(self):
        result = rewrite_legacy_args([])
        assert result == []

    def test_new_syntax_passes_through(self):
        result = rewrite_legacy_args(["artist", "list"])
        assert result == ["artist", "list"]

    def test_deprecation_warning_emitted(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            rewrite_legacy_args(["--list-artists"])
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "--list-artists" in str(w[0].message)
