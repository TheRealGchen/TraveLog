"""Write the API's OpenAPI spec to a file, or with --check fail if the file is out of date."""

import argparse
import json
import sys
from pathlib import Path

from travel_api.config import Settings
from travel_api.main import create_app


def render() -> str:
    app = create_app(Settings(mongodb_uri="mongodb://unused", api_token="unused"))
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="where the spec lives, e.g. ../../openapi.json")
    parser.add_argument("--check", action="store_true", help="only check, do not write")
    args = parser.parse_args()
    spec = render()
    if args.check:
        if not args.path.exists() or args.path.read_text(encoding="utf-8") != spec:
            print(f"{args.path} is out of date. Run `make openapi` and commit it.", file=sys.stderr)
            return 1
        print(f"{args.path} is up to date.")
        return 0
    args.path.write_text(spec, encoding="utf-8")
    print(f"Wrote {args.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
