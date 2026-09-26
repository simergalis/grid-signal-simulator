"""Capture GridSignal commit provenance during the production build."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


def _git_output(repo_root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo_root), *args],
        cwd=repo_root,
        text=True,
    ).strip()


def write_build_info(
    repo_root: Path,
    output_path: Path,
) -> tuple[dict[str, str], bool]:
    repo_root = Path(repo_root).resolve()
    output_path = Path(output_path).resolve()
    commit = _git_output(repo_root, "rev-parse", "HEAD")
    if not commit:
        raise RuntimeError("git rev-parse HEAD returned an empty commit")

    dirty = bool(
        _git_output(repo_root, "status", "--porcelain", "--untracked-files=all")
    )
    captured_commit = f"{commit}-dirty" if dirty else commit
    build_info = {
        "engine_commit": captured_commit,
        "harness_commit": captured_commit,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            delete=False,
        ) as handle:
            json.dump(build_info, handle, sort_keys=True)
            handle.write("\n")
            temp_path = Path(handle.name)
        os.replace(temp_path, output_path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()

    return build_info, dirty


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    build_info, dirty = write_build_info(args.repo_root, args.output)
    print(
        "[build_prod] captured commit provenance: "
        f"engine_commit={build_info['engine_commit']} "
        f"harness_commit={build_info['harness_commit']} "
        f"working_tree_dirty={str(dirty).lower()} "
        f"file={args.output}"
    )


if __name__ == "__main__":
    main()