"""CLI argument parser for Vibemus.

Builds a subcommand-based CLI with four groups:
  artist   – Manage tracked artists
  sync     – Discovery and synchronization
  playlist – Playlist operations and maintenance
  system   – Cache, reset, and authentication
"""

import argparse
import sys
import warnings


def build_parser() -> argparse.ArgumentParser:
    """Build and return the main argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="vibemus",
        description="🌌 Vibemus: YouTube Music Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  vibemus artist add \"Radiohead\" --playlist \"Rock\"\n"
            "  vibemus sync deep --auto\n"
            "  vibemus playlist cleanup-inbox\n"
            "  vibemus system refresh-cache\n"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    _register_artist(subparsers)
    _register_sync(subparsers)
    _register_playlist(subparsers)
    _register_system(subparsers)

    return parser


# ── Artist ────────────────────────────────────────────────────────────────────


def _register_artist(subparsers: argparse._SubParsersAction) -> None:
    artist_parser = subparsers.add_parser(
        "artist",
        help="Manage tracked artists",
        description="Add, remove, list, and maintain your tracked artists.",
    )
    artist_sub = artist_parser.add_subparsers(dest="action")

    # artist list
    artist_sub.add_parser("list", help="List all tracked artists and their status")

    # artist search
    search_p = artist_sub.add_parser("search", help="Search for artists in YT/Sheet")
    search_p.add_argument("query", type=str, help="Search string")

    # artist add
    add_p = artist_sub.add_parser(
        "add",
        help="Add an artist by name",
        description="Search YouTube Music and start tracking an artist.",
    )
    add_p.add_argument("name", type=str, help="Artist name to add")
    add_p.add_argument(
        "--playlist", type=str, metavar="PL",
        help="Assign a target playlist and migrate songs",
    )
    add_p.add_argument(
        "--api", type=str, choices=["lastfm", "musicbrainz"], default="lastfm",
        help="Metadata API to use for initial discovery (default: lastfm)",
    )

    # artist remove
    rm_p = artist_sub.add_parser("remove", help="Remove an artist by name")
    rm_p.add_argument("name", type=str, help="Artist name to remove")





    # artist cleanup-collabs
    artist_sub.add_parser(
        "cleanup-collabs",
        help="Interactive cleanup of collaborative artists",
    )

    # artist sync
    artist_sub.add_parser(
        "sync",
        help="Synchronize tracked artists with the 'Songs' catalog, performing onboarding for new ones",
    )

    # artist import
    artist_sub.add_parser(
        "import",
        help="Import artists from the YouTube library (based on count of your tracks they have)",
    )

    # artist reset-empty
    artist_sub.add_parser(
        "reset-empty",
        help="Reset 'Last Checked' for artists with NO songs yet (useful to retry scanning)",
    )

    # artist archive-inactive
    artist_sub.add_parser(
        "archive-inactive",
        help="Move artists with no activity in Last.fm/YT for X years to Archives",
    )


# ── Sync ──────────────────────────────────────────────────────────────────────


def _register_sync(subparsers: argparse._SubParsersAction) -> None:
    sync_parser = subparsers.add_parser(
        "sync",
        help="Discovery and synchronization",
        description="Check for new releases and synchronize playlists.",
    )
    sync_sub = sync_parser.add_subparsers(dest="action")

    # sync deep (was --deep-sync)
    deep_p = sync_sub.add_parser(
        "deep",
        help="Deep sync all artists not checked in 6 months",
    )
    deep_p.add_argument(
        "--auto", action="store_true",
        help="Skip interactive prompts and auto-add all candidates",
    )

    # sync releases / new-releases
    rel_p = sync_sub.add_parser(
        "releases",
        help="Check for new releases from tracked artists",
    )
    rel_p.add_argument(
        "--force", action="store_true",
        help="Force re-scan even if checked recently",
    )
    rel_p.add_argument(
        "--auto", action="store_true",
        help="Skip interactive prompts and auto-add all found songs",
    )

    nr_p = sync_sub.add_parser(
        "new-releases",
        help="Scan global new releases from YouTube Music for tracked artists",
    )
    nr_p.add_argument(
        "--auto", action="store_true",
        help="Skip interactive prompts and auto-add all found songs",
    )

    # sync playlist (was --sync-playlist)
    sp_p = sync_sub.add_parser(
        "playlist",
        help="Sync playlist(s) with Songs sheet and enrich with Last.fm",
    )
    sp_p.add_argument(
        "--name", type=str, metavar="PL",
        help="Sync only this playlist (default: all source playlists)",
    )
    sp_p.add_argument(
        "--skip-lastfm", action="store_true",
        help="Skip Last.fm enrichment (faster)",
    )
    sp_p.add_argument(
        "--no-covers", action="store_true",
        help="Skip playlist cover generation (reordering)",
    )


    # sync genre
    sync_sub.add_parser(
        "genre",
        help="Update the 'Genre' summary sheet with counts from the 'Songs' catalog",
    )



# ── Playlist ──────────────────────────────────────────────────────────────────


def _register_playlist(subparsers: argparse._SubParsersAction) -> None:
    pl_parser = subparsers.add_parser(
        "playlist",
        help="Playlist operations and maintenance",
        description="Clean, export, and process playlists.",
    )
    pl_sub = pl_parser.add_subparsers(dest="action")



    # playlist cleanup-inbox (was --cleanup-inbox)
    pl_sub.add_parser(
        "cleanup-inbox",
        help="Remove songs from '#' already in other playlists",
    )

    # playlist clean
    pl_sub.add_parser(
        "clean",
        help="Remove songs from playlists that are not in the 'Songs' sheet",
    )

    # playlist undo-old
    pl_sub.add_parser(
        "undo-old",
        help="Experimental: undoing old processing tasks",
    )

    # playlist export
    ex_p = pl_sub.add_parser(
        "export",
        help="Export a YT playlist to a Google sheet page",
    )
    ex_p.add_argument(
        "playlist_id", nargs="?",
        help="YouTube ID of the playlist to export (defaults to current target)",
    )

    # playlist cleanup-likes
    pl_sub.add_parser(
        "cleanup-likes",
        help="Interactively unlike songs from 'LM' (or Liked Songs) if plays > threshold",
    )

    # playlist cleanup-library
    pl_sub.add_parser(
        "cleanup-library",
        help="Remove songs from library that are NOT in any playlist (respects LIKE status)",
    )

    # playlist apply-moves
    am_p = pl_sub.add_parser(
        "apply-moves",
        help="Apply manual playlist changes from the Songs sheet to YouTube Music",
    )
    am_p.add_argument(
        "--artist", type=str, metavar="NAME",
        help="Apply moves only for this artist",
    )
    am_p.add_argument(
        "--refresh-cache", action="store_true",
        help="Refresh local source playlist cache before scanning",
    )
    am_p.add_argument(
        "--playlist", type=str, metavar="NAME",
        help="Apply moves only for this target playlist in the sheet (e.g. 'Crank')",
    )
    am_p.add_argument(
        "--api", type=str, choices=["lastfm", "musicbrainz"], default="lastfm",
        help="API service to use for metadata (default: lastfm)",
    )

    # playlist split
    split_p = pl_sub.add_parser(
        "split",
        help="Split a main playlist (and its archives) into N balanced parts by year",
    )
    split_p.add_argument(
        "--name", type=str, metavar="PL", required=True,
        help="Base playlist to split (e.g. 'Pop')",
    )
    split_p.add_argument(
        "--parts", type=int, required=True,
        help="Divide the entire collection into N approximately equal parts",
    )

    # playlist list
    pl_sub.add_parser(
        "list",
        help="List all playlists with their song counts in YouTube Music and Google Sheet",
    )




# ── System ────────────────────────────────────────────────────────────────────


def _register_system(subparsers: argparse._SubParsersAction) -> None:
    sys_parser = subparsers.add_parser(
        "system",
        help="Cache, reset, and utility operations",
        description="System-level utilities for Vibemus.",
    )
    sys_sub = sys_parser.add_subparsers(dest="action")



    # system refresh-cache
    sys_sub.add_parser(
        "refresh-cache",
        help="Refresh local cache of source playlists",
    )

    # system auth
    sys_sub.add_parser(
        "auth",
        help="Run authentication helper (grab_cookies.js)",
    )


# ── Legacy Aliases ────────────────────────────────────────────────────────────

# Mapping: old flag -> (new command words, extra processing-key or None)
_LEGACY_MAP = {
    "--list-artists": ("artist", "list"),
    "--add-artist": ("artist", "add"),
    "--remove-artist": ("artist", "remove"),
    "--import-artists": ("artist", "import"),
    "--archive-inactive": ("artist", "archive-inactive"),
    "--reset-empty-artists": ("artist", "reset-empty"),

    "--deep-sync": ("sync", "deep"),
    "--sync-new-releases": ("sync", "new-releases"),
    "--sync-playlist": ("sync", "playlist"),

    "--cleanup-inbox": ("playlist", "cleanup-inbox"),
    "--clean-playlist": ("playlist", "clean"),
    "--cleanup-library": ("playlist", "cleanup-library"),
    "--apply-moves": ("playlist", "apply-moves"),
    "--refresh-source-cache": ("system", "refresh-cache"),

}


def rewrite_legacy_args(argv: list[str]) -> list[str]:
    """Rewrite legacy flat-flags to subcommand syntax.

    Returns the (potentially rewritten) argv list.
    Emits a DeprecationWarning for each legacy flag found.
    """
    if not argv:
        return argv

    # If the first arg already looks like a subcommand, skip
    if argv[0] in ("artist", "sync", "playlist", "system"):
        return argv

    new_argv: list[str] = []
    i = 0
    rewritten = False

    while i < len(argv):
        arg = argv[i]

        if arg in _LEGACY_MAP:
            cmd, action = _LEGACY_MAP[arg]
            new_cmd = f"vibemus {cmd} {action}"

            # Flags that consume a value argument
            if arg in ("--add-artist", "--remove-artist"):
                i += 1
                if i < len(argv):
                    name_val = argv[i]
                    new_argv = [cmd, action, name_val] + new_argv
                    warnings.warn(
                        f"'{arg}' is deprecated. "
                        f"Use: {new_cmd} \"{name_val}\"",
                        DeprecationWarning,
                        stacklevel=2,
                    )
                else:
                    new_argv = [cmd, action] + new_argv
                    warnings.warn(
                        f"'{arg}' is deprecated. Use: {new_cmd} NAME",
                        DeprecationWarning,
                        stacklevel=2,
                    )
                rewritten = True



            else:
                new_argv = [cmd, action] + new_argv
                warnings.warn(
                    f"'{arg}' is deprecated. Use: {new_cmd}",
                    DeprecationWarning,
                    stacklevel=2,
                )
                rewritten = True

        # Map modifier flags to new names
        elif arg == "--playlist" and rewritten:
            # If this follows an artist add, keep as-is
            new_argv.append("--playlist")
        elif arg == "--auto":
            new_argv.append("--auto")
        elif arg == "--force":
            new_argv.append("--force")
        elif arg == "--skip-lastfm":
            new_argv.append("--skip-lastfm")
        elif arg == "--refresh-source-cache" and not rewritten:
            # Standalone usage
            new_argv = ["system", "refresh-cache"] + new_argv
            warnings.warn(
                "'--refresh-source-cache' is deprecated. "
                "Use: vibemus system refresh-cache",
                DeprecationWarning,
                stacklevel=2,
            )
            rewritten = True
        else:
            new_argv.append(arg)

        i += 1

    return new_argv
