from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATHS = (
    ROOT / "docs" / "latest.json",
    ROOT / "docs" / "strategy_a_latest.json",
    ROOT / "docs" / "strategy_b_latest.json",
    ROOT / "data" / "latest.json",
    ROOT / "data" / "strategy_a_latest.json",
    ROOT / "data" / "strategy_b_latest.json",
)
REQUEST_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")


def stamp_scan_outputs(request_sha: str, paths: Iterable[Path | str]) -> None:
    """Bind each JSON result object to the commit that requested its scan."""
    if not isinstance(request_sha, str) or REQUEST_SHA_PATTERN.fullmatch(request_sha) is None:
        raise ValueError("request SHA must be 40 lowercase hexadecimal characters")

    loaded_outputs: list[tuple[Path, dict]] = []
    for supplied_path in paths:
        path = Path(supplied_path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"{path} must contain a JSON object") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{path} must contain a JSON object")
        payload["request_commit_sha"] = request_sha
        loaded_outputs.append((path, payload))

    if not loaded_outputs:
        raise ValueError("at least one JSON object path is required")

    for path, payload in loaded_outputs:
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stamp A/B/C scan outputs with their request commit SHA.")
    parser.add_argument("request_sha")
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args(argv)

    try:
        stamp_scan_outputs(args.request_sha, args.paths or DEFAULT_OUTPUT_PATHS)
    except ValueError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
