#!/usr/bin/env python3
"""Cross-platform development entrypoint for omni-bot."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
PIXI_MANIFEST = ROOT / "pixi.toml"
OMNIBOT_SOURCE = ROOT / "Omnibot"
BUILD_ROOT = OMNIBOT_SOURCE / "build"
ZIG_TOOLCHAIN = OMNIBOT_SOURCE / "cmake" / "zig-toolchain.cmake"


@dataclass(frozen=True)
class BotBuildTarget:
    """Describe one Zig target understood by the CMake project."""

    name: str
    system_name: str
    processor: str
    zig_target: str


LEGACY_BOT_TARGET = BotBuildTarget(
    name="x86-linux",
    system_name="Linux",
    processor="x86",
    zig_target="x86-linux-gnu.2.3",
)


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
    """Run a command with the dependencies pinned by this project's Pixi lockfile."""
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


def _configure_bot_build(*, release: bool) -> Path:
    """Configure the legacy 32-bit Linux bot build through Zig and CMake."""
    if not sys.platform.startswith("linux"):
        raise RuntimeError("Zig bot cross builds currently require Linux")

    build_mode = "release" if release else "debug"
    build_directory = BUILD_ROOT / f"cmake-{build_mode}-{LEGACY_BOT_TARGET.name}"
    build_type = "Release" if release else "RelWithDebInfo"
    build_environment = {
        "ZIG_GLOBAL_CACHE_DIR": str(BUILD_ROOT / ".zig-cache"),
    }
    configure_command = [
        "cmake",
        "-S",
        str(OMNIBOT_SOURCE),
        "-B",
        str(build_directory),
        "-G",
        "Ninja",
        f"-DCMAKE_BUILD_TYPE={build_type}",
        f"-DCMAKE_TOOLCHAIN_FILE={ZIG_TOOLCHAIN}",
        f"-DOMNIBOT_ZIG_SYSTEM_NAME={LEGACY_BOT_TARGET.system_name}",
        f"-DOMNIBOT_ZIG_PROCESSOR={LEGACY_BOT_TARGET.processor}",
        f"-DOMNIBOT_ZIG_TARGET={LEGACY_BOT_TARGET.zig_target}",
    ]
    _run_in_pixi(configure_command, environment=build_environment)
    return build_directory


def build_bot(*, release: bool) -> None:
    """Build the legacy ET and RTCW bot modules through CMake."""
    build_directory = _configure_bot_build(release=release)
    _run_in_pixi(
        [
            "cmake",
            "--build",
            str(build_directory),
            "--target",
            "omnibot-et",
            "omnibot-rtcw",
        ],
        environment={"ZIG_GLOBAL_CACHE_DIR": str(BUILD_ROOT / ".zig-cache")},
    )


def _parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    build_bot_parser = subcommands.add_parser(
        "build-bot", help="cross-build the legacy Linux bot modules"
    )
    build_bot_parser.add_argument(
        "--release",
        action="store_true",
        help="build optimized modules without debug information",
    )
    return parser


def main() -> None:
    """Dispatch the requested development command."""
    arguments = _parser().parse_args()
    if arguments.command == "build-bot":
        build_bot(release=arguments.release)


if __name__ == "__main__":
    main()
