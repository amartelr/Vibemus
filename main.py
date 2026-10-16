"""Vibemus – YouTube Music Automation.

Entry point for the CLI. Delegates all logic to ``src.cli``.
"""

import sys
import warnings

from src.cli.commands import (
    handle_artist,
    handle_playlist,
    handle_library,
    handle_releases,
    handle_system,
    handle_recom,
    handle_genre,
    handle_youtube,
    handle_web,
)
from src.cli.parser import build_parser, rewrite_legacy_args
from src.config import Config


_HANDLERS = {
    "artist": handle_artist,
    "releases": handle_releases,
    "playlist": handle_playlist,
    "library": handle_library,
    "recom": handle_recom,
    "genre": handle_genre,
    "system": handle_system,
    "youtube": handle_youtube,
    "web": handle_web,
}


def main() -> None:
    # 1. Validate configuration
    try:
        Config.validate()
    except FileNotFoundError as exc:
        print(f"Configuration Error: {exc}")
        print(
            "Please ensure 'oauth.json' and 'service_account.json' "
            "are in the 'config' directory."
        )
        sys.exit(1)

    Config.ensure_directories()

    # 2. Parse arguments (rewrite legacy flags first)
    parser = build_parser()
    argv = rewrite_legacy_args(sys.argv[1:])

    # Show deprecation warnings to stderr
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        args = parser.parse_args(argv)
        for w in caught:
            print(f"\033[93m⚠ {w.message}\033[0m", file=sys.stderr)

    command = getattr(args, "command", None)
    # Normalize command aliases
    _CMD_MAP = {
        "art": "artist",
        "rel": "releases",
        "pl": "playlist",
        "lib": "library",
        "rec": "recom",
        "gen": "genre",
        "sys": "system",
        "yt": "youtube",
        "serve": "web",
    }
    command = _CMD_MAP.get(command, command)

    if not command:
        parser.print_help()
        sys.exit(0)

    # 3. Initialise Manager
    try:
        from src.services.yt_service import AuthenticationError, YTMusicService
        from src.services.sheets_service import SheetsService
        from src.services.lastfm_service import LastFMService
        from src.services.musicbrainz_service import MusicBrainzService
        from src.core.manager import Manager

        # Initialize services
        is_system_auth = (command == "system" and getattr(args, "action", None) in ("auth",))

        if is_system_auth or command == "web":
            # system auth only runs grab_cookies.js and the web app has its own credentials:
            # no CLI services needed.
            # Skip initialization entirely so a fully expired token doesn't block the command.
            yt = None
            sheets = None
            lastfm = None
            musicbrainz = None
        else:
            yt = YTMusicService()
            sheets = SheetsService()
            lastfm = LastFMService()
            musicbrainz = MusicBrainzService()

        # Initialize manager with required services
        manager = Manager(yt, sheets, lastfm, musicbrainz)
        
    except AuthenticationError:
        print("\n\033[91m" + "=" * 50)
        print("AUTHENTICATION ERROR")
        print("=" * 50 + "\033[0m")
        print("\nYour YouTube Music session has expired or is invalid.")
        print("\n\033[93mTO FIX THIS:\033[0m")
        print("  Run: \033[92mvibemus system auth\033[0m")
        sys.exit(1)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(f"Failed to initialize services: {exc}")
        sys.exit(1)

    # 4. Dispatch to handler
    handler = _HANDLERS.get(command)
    if handler:
        if command == "web":
            exit_code = handler(args, manager)
        else:
            from src.services.sheet_lock import cli_session
            with cli_session(" ".join(filter(None, [command, getattr(args, "action", None)]))):
                exit_code = handler(args, manager)
        sys.exit(exit_code or 0)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
