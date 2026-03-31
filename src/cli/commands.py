"""Command handlers for Vibemus CLI subcommands.

Each ``handle_*`` function receives the parsed ``argparse.Namespace`` and an
initialised ``Manager`` instance, executes the corresponding business logic,
and returns an integer exit code (0 = success).
"""

import subprocess
import sys
from datetime import datetime

from ..config import Config


# ── Artist ────────────────────────────────────────────────────────────────────


def handle_artist(args, manager) -> int:
    """Dispatch artist sub-actions."""
    action = getattr(args, "action", None)

    if action == "add":
        return _artist_add(args, manager)
    elif action == "remove":
        return _artist_remove(args, manager)


    elif action == "cleanup-collabs":
        return _artist_cleanup_collabs(manager)
    else:
        print("Usage: vibemus artist <add|remove|cleanup-collabs>")
        print("Run 'vibemus artist --help' for details.")
        return 1


def _artist_add(args, manager) -> int:
    """Add or update an artist and run its search logic."""
    status, artist_data = manager.add_artist(
        args.name, 
        target_playlist=args.playlist, 
        api_choice=args.api
    )

    if not artist_data:
        return 1

    name = artist_data.get("Artist Name", args.name)
    
    if status == "added":
        print(f"✅ Successfully added '{name}' to tracking.")
    elif status == "exists":
        if args.playlist:
            print(f"ℹ️ Artist '{name}' already exists. Updating its target playlist to '{args.playlist}'...")
            manager.sheets.update_artist_playlist(name, args.playlist)
        else:
            print(f"ℹ️ Artist '{name}' is already being tracked.")

    return 0


def _artist_remove(args, manager) -> int:
    manager.remove_artist(args.name)
    return 0








def _artist_cleanup_collabs(manager) -> int:
    manager.cleanup_collab_artists()
    return 0


# ── Sync ──────────────────────────────────────────────────────────────────────


def handle_sync(args, manager) -> int:
    """Dispatch sync sub-actions."""
    action = getattr(args, "action", None)

    if action == "deep":
        return _sync_deep(args, manager)
    elif action == "playlist":
        return _sync_playlist(args, manager)
    else:
        print("Usage: vibemus sync <deep|playlist>")
        print("Run 'vibemus sync --help' for details.")
        return 1


def _sync_deep(args, manager) -> int:
    manager.deep_sync_all_artists(interactive=not args.auto)
    return 0


def _sync_playlist(args, manager) -> int:
    print("Starting playlist sync...")
    manager.sync_playlist(
        playlist_name=getattr(args, "name", None),
        skip_lastfm=args.skip_lastfm,
    )
    return 0


# ── Playlist ──────────────────────────────────────────────────────────────────


def handle_playlist(args, manager) -> int:
    """Dispatch playlist sub-actions."""
    action = getattr(args, "action", None)

    if action == "cleanup-inbox":
        return _playlist_cleanup_inbox(manager)
    elif action == "cleanup-likes":
        return _playlist_cleanup_likes(args, manager)
    elif action == "apply-moves":
        return _playlist_apply_moves(args, manager)
    elif action == "archive":
        return _playlist_archive(args, manager)
    else:
        print(
            "Usage: vibemus playlist "
            "<cleanup-inbox|cleanup-likes|apply-moves|archive>"
        )
        print("Run 'vibemus playlist --help' for details.")
        return 1





def _playlist_cleanup_inbox(manager) -> int:
    manager.cleanup_inbox_duplicates()
    return 0

def _playlist_cleanup_likes(args, manager) -> int:
    manager.cleanup_likes()
    return 0
def _playlist_apply_moves(args, manager) -> int:
    manager.apply_manual_moves(
        refresh_cache=args.refresh_cache,
        target_artist_name=args.artist,
        api_choice=args.api
    )
    return 0






def _playlist_archive(args, manager) -> int:
    manager.archive_playlist_by_year(
        playlist_name=getattr(args, "name", None),
        year=args.year,
    )
    return 0





# ── System ────────────────────────────────────────────────────────────────────


def handle_system(args, manager) -> int:
    """Dispatch system sub-actions."""
    action = getattr(args, "action", None)

    if action == "refresh-cache":
        return _system_refresh_cache(manager)
    elif action == "auth":
        return _system_auth()
    else:
        print("Usage: vibemus system <refresh-cache|auth>")
        print("Run 'vibemus system --help' for details.")
        return 1





def _system_refresh_cache(manager) -> int:
    manager.refresh_source_cache_only()
    return 0


def _system_auth() -> int:
    """Run the grab_cookies.js authentication helper."""
    import os

    script_path = os.path.join(Config.BASE_DIR, "grab_cookies.js")
    if not os.path.exists(script_path):
        print(f"Error: Authentication script not found at {script_path}")
        return 1

    print("Launching authentication helper...")
    try:
        subprocess.run(["node", script_path], check=True)
    except FileNotFoundError:
        print("Error: Node.js is required. Install it via 'brew install node'.")
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"Authentication failed with exit code {exc.returncode}.")
        return exc.returncode

    return 0
