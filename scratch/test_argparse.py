import argparse

parser = argparse.ArgumentParser()
subparsers = parser.add_subparsers(dest="command")
art_parser = subparsers.add_parser("artist", aliases=["art"])
art_sub = art_parser.add_subparsers(dest="action")
art_sub.add_parser("list", aliases=["ls"])

args = parser.parse_args(["art", "ls"])
print(f"Command: {args.command}")
print(f"Action: {args.action}")
