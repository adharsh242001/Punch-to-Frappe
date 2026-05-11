"""Generate shared secrets for distributed edge/server sync."""
import argparse
import secrets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate node secrets for PC A / PC B distributed sync."
    )
    parser.add_argument(
        "--nodes",
        nargs="+",
        default=["pc-a", "pc-b"],
        help="Node IDs to generate secrets for. Default: pc-a pc-b",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pairs = [(node, secrets.token_urlsafe(32)) for node in args.nodes]

    print("Central server .env:")
    print("SERVER_NODE_KEYS=" + ",".join(f"{node}:{secret}" for node, secret in pairs))
    print()

    for node, secret in pairs:
        print(f"{node} .env:")
        print(f"EDGE_NODE_ID={node}")
        print(f"EDGE_NODE_SECRET={secret}")
        print()


if __name__ == "__main__":
    main()
