#!/usr/bin/env python3
"""Cross-platform development entrypoint for omni-bot."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
from collections.abc import Sequence


ROOT = Path(__file__).resolve().parent
PIXI_MANIFEST = ROOT / "pixi.toml"
OMNIBOT_SOURCE = ROOT / "Omnibot"
BUILD_ROOT = OMNIBOT_SOURCE / "build"


def _is_project_pixi_environment() -> bool:
    """Return whether this process already runs in this project's Pixi environment."""
    manifest = os.environ.get("PIXI_PROJECT_MANIFEST")
    return bool(manifest and Path(manifest).resolve() == PIXI_MANIFEST)


def _clean_environment_for_pixi() -> dict[str, str]:
    """Remove an activated foreign Pixi/Conda environment before entering ours."""
    environment = os.environ.copy()
    old_prefix = environment.get("CONDA_PREFIX")

    for name in tuple(environment):
        if name.startswith(("PIXI_", "CONDA_")):
            environment.pop(name)

    if old_prefix:
        old_bin = Path(old_prefix) / ("Scripts" if os.name == "nt" else "bin")
        environment["PATH"] = os.pathsep.join(
            entry
            for entry in environment.get("PATH", "").split(os.pathsep)
            if Path(entry) != old_bin
        )

    return environment


def _run_in_pixi(
    command: Sequence[str], *, environment: dict[str, str] | None = None
) -> None:
    """Run a command with the dependencies pinned by this project's Pixi manifest."""
    child_environment = os.environ.copy()
    if _is_project_pixi_environment():
        invocation = list(command)
    else:
        pixi = shutil.which("pixi")
        if not pixi:
            raise RuntimeError("pixi is required to run project commands")
        child_environment = _clean_environment_for_pixi()
        invocation = [
            pixi,
            "run",
            "--manifest-path",
            str(PIXI_MANIFEST),
            *command,
        ]

    if environment:
        child_environment.update(environment)

    subprocess.run(invocation, cwd=ROOT, env=child_environment, check=True)


def _configure_bot_build(*, release: bool, tests: bool) -> tuple[Path, dict[str, str]]:
    """Configure a 32-bit Linux bot build and return its path and environment."""
    if not sys.platform.startswith("linux"):
        raise RuntimeError("32-bit bot builds currently require Linux")

    build_mode = "release" if release else "debug"
    # Tests use their own tree so enabling them never changes the bot build outputs.
    meson_build_name = "meson-tests-x86" if tests else f"meson-{build_mode}-x86"
    meson_build = BUILD_ROOT / meson_build_name
    zig_cache = BUILD_ROOT / ".zig-cache"
    cross_files = [OMNIBOT_SOURCE / "meson" / "zig-x86-linux.ini"]
    if tests:
        cross_files.append(OMNIBOT_SOURCE / "tests" / "x86-linux.ini")

    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    build_environment = {
        "ZIG_GLOBAL_CACHE_DIR": str(zig_cache),
    }

    coredata = meson_build / "meson-private" / "coredata.dat"
    configuration_stamp = meson_build / ".meson-configuration"
    # Cross files and the project-option schema are immutable after initial setup.
    configuration_files = [*cross_files, OMNIBOT_SOURCE / "meson.options"]
    configuration_state = b"\0".join(
        path.read_bytes() for path in configuration_files
    )
    # Meson cannot reuse a build directory left behind by a failed setup.
    if meson_build.exists() and not coredata.exists():
        shutil.rmtree(meson_build)
    # Recreate build trees when setup-time configuration becomes stale.
    elif coredata.exists() and (
        not configuration_stamp.exists()
        or configuration_stamp.read_bytes() != configuration_state
    ):
        shutil.rmtree(meson_build)

    setup_arguments = [
        "meson",
        "setup",
        str(meson_build),
        str(OMNIBOT_SOURCE),
        "-Dc_std=gnu99",
        f"--buildtype={'release' if release else 'debugoptimized'}",
        f"-Db_ndebug={'true' if release else 'false'}",
        f"-Dtests={'true' if tests else 'false'}",
    ]
    setup_arguments.extend(f"--cross-file={path}" for path in cross_files)
    if coredata.exists():
        setup_arguments.append("--reconfigure")

    _run_in_pixi(setup_arguments, environment=build_environment)
    configuration_stamp.write_bytes(configuration_state)

    return meson_build, build_environment


def build_bot(*, release: bool) -> None:
    """Build the legacy 32-bit Linux bot modules with Meson and Zig."""
    meson_build, build_environment = _configure_bot_build(
        release=release,
        tests=False,
    )
    _run_in_pixi(
        ["meson", "compile", "-C", str(meson_build)],
        environment=build_environment,
    )


def test_bot() -> None:
    """Build and run the 32-bit Linux behavior tests through Meson."""
    meson_build, build_environment = _configure_bot_build(
        release=False,
        tests=True,
    )
    _run_in_pixi(
        ["meson", "test", "-C", str(meson_build), "--print-errorlogs"],
        environment=build_environment,
    )


def _parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    build_bot_parser = subcommands.add_parser(
        "build-bot", help="build the 32-bit Linux bot modules"
    )
    build_bot_parser.add_argument(
        "--release",
        action="store_true",
        help="build optimized modules without debug information",
    )
    subcommands.add_parser("test", help="run the 32-bit Linux behavior tests")
    return parser


def main() -> None:
    """Dispatch the requested development command."""
    arguments = _parser().parse_args()
    if arguments.command == "build-bot":
        build_bot(release=arguments.release)
    elif arguments.command == "test":
        test_bot()


if __name__ == "__main__":
    main()
