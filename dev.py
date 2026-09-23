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


def build_bot() -> None:
    """Build the legacy 32-bit Linux bot modules with Conan, Meson, and Zig."""
    if not sys.platform.startswith("linux"):
        raise RuntimeError("build-bot currently ports Omnibot/linux/buildbot.sh and requires Linux")

    conan_output = BUILD_ROOT / "conan-release-x86"
    meson_build = BUILD_ROOT / "meson-release-x86"
    conan_home = BUILD_ROOT / ".conan2"
    zig_cache = BUILD_ROOT / ".zig-cache"
    host_profile = OMNIBOT_SOURCE / "conan" / "profiles" / "linux-x86-zig"
    build_profile = OMNIBOT_SOURCE / "conan" / "profiles" / "linux-x86_64-zig"

    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    build_environment = {
        "CONAN_HOME": str(conan_home),
        "ZIG_GLOBAL_CACHE_DIR": str(zig_cache),
    }

    _run_in_pixi(
        [
            "conan",
            "install",
            str(OMNIBOT_SOURCE),
            f"--output-folder={conan_output}",
            f"--profile:host={host_profile}",
            f"--profile:build={build_profile}",
            "--build=missing",
        ],
        environment=build_environment,
    )

    toolchain = conan_output / "conan_meson_cross.ini"
    coredata = meson_build / "meson-private" / "coredata.dat"
    # Meson cannot reuse a build directory left behind by a failed setup.
    if meson_build.exists() and not coredata.exists():
        shutil.rmtree(meson_build)

    setup_arguments = [
        "meson",
        "setup",
        str(meson_build),
        str(OMNIBOT_SOURCE),
        f"--cross-file={toolchain}",
        "-Dc_std=gnu99",
    ]
    if coredata.exists():
        setup_arguments.append("--reconfigure")

    _run_in_pixi(setup_arguments, environment=build_environment)
    _run_in_pixi(
        ["meson", "compile", "-C", str(meson_build)],
        environment=build_environment,
    )


def _parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("build-bot", help="build the 32-bit Linux bot modules")
    return parser


def main() -> None:
    """Dispatch the requested development command."""
    arguments = _parser().parse_args()
    if arguments.command == "build-bot":
        build_bot()


if __name__ == "__main__":
    main()
