#!/usr/bin/env python3
"""Cross-platform development entrypoint for omni-bot."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import struct
import subprocess


ROOT = Path(__file__).resolve().parent
PIXI_MANIFEST = ROOT / "pixi.toml"
OMNIBOT_SOURCE = ROOT / "Omnibot"
# Tests and automation can isolate generated files without changing CLI behavior.
BUILD_ROOT = Path(
    os.environ.get("OMNIBOT_BUILD_ROOT", OMNIBOT_SOURCE / "build")
).resolve()
ZIG_TOOLCHAIN = OMNIBOT_SOURCE / "cmake" / "zig-toolchain.cmake"
RELEASE_FILES = ROOT / "Installer" / "Files" / "rtcw"
# Tests and automation can redirect packaging away from the working tree.
DIST_DIRECTORY = Path(
    os.environ.get("OMNIBOT_DIST_DIRECTORY", ROOT / "dist")
).resolve()


@dataclass(frozen=True)
class BotBuildTarget:
    """Describe one Zig target understood by the CMake project."""

    name: str
    system_name: str
    processor: str
    zig_target: str
    output_name: str
    keeps_elf_loader: bool = False


LEGACY_BOT_TARGET = BotBuildTarget(
    name="x86-linux",
    system_name="Linux",
    processor="x86",
    zig_target="x86-linux-gnu.2.3",
    output_name="omnibot_et.so",
)
ALL_BOT_TARGETS = (
    BotBuildTarget(
        name="aarch64-linux",
        system_name="Linux",
        processor="aarch64",
        zig_target="aarch64-linux-gnu.2.17",
        output_name="omnibot_et.aarch64.so",
        keeps_elf_loader=True,
    ),
    BotBuildTarget(
        name="x86-windows",
        system_name="Windows",
        processor="x86",
        zig_target="x86-windows-gnu",
        output_name="omnibot_et.dll",
    ),
    LEGACY_BOT_TARGET,
    BotBuildTarget(
        name="x86_64-linux",
        system_name="Linux",
        processor="x86_64",
        zig_target="x86_64-linux-gnu.2.17",
        output_name="omnibot_et.x86_64.so",
    ),
    BotBuildTarget(
        name="x86_64-macos",
        system_name="Darwin",
        processor="x86_64",
        zig_target="x86_64-macos-none",
        output_name="omnibot_et_mac.so",
    ),
    BotBuildTarget(
        name="x86_64-windows",
        system_name="Windows",
        processor="x86_64",
        zig_target="x86_64-windows-gnu",
        output_name="omnibot_et_x64.dll",
    ),
)
DIST_FILES = (
    "README.txt",
    "changelog.txt",
    *(target.output_name for target in ALL_BOT_TARGETS),
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


def _build_environment() -> dict[str, str]:
    """Return the shared Zig cache configuration for build subprocesses."""
    return {"ZIG_GLOBAL_CACHE_DIR": str(BUILD_ROOT / ".zig-cache")}


def _configure_bot_build(
    *, release: bool, target: BotBuildTarget, build_rtcw: bool
) -> Path:
    """Configure one Zig bot build through CMake."""
    build_mode = "release" if release else "debug"
    build_directory = BUILD_ROOT / f"cmake-{build_mode}-{target.name}"
    build_type = "Release" if release else "RelWithDebInfo"
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
        "-DOMNIBOT_ET=ON",
        f"-DOMNIBOT_RTCW={'ON' if build_rtcw else 'OFF'}",
        f"-DOMNIBOT_ZIG_SYSTEM_NAME={target.system_name}",
        f"-DOMNIBOT_ZIG_PROCESSOR={target.processor}",
        f"-DOMNIBOT_ZIG_TARGET={target.zig_target}",
    ]
    _run_in_pixi(configure_command, environment=_build_environment())
    return build_directory


def _build_bot_target(*, release: bool, target: BotBuildTarget) -> Path:
    """Build one ET module and return its path in the CMake tree."""
    build_directory = _configure_bot_build(
        release=release,
        target=target,
        build_rtcw=False,
    )
    _run_in_pixi(
        ["cmake", "--build", str(build_directory), "--target", "omnibot-et"],
        environment=_build_environment(),
    )
    return build_directory / "ET" / target.output_name


def _conform_zig_elf_dependencies(path: Path, *, keep_loader: bool) -> None:
    """Normalize Zig's broad glibc dependency group to the release ABI manifest."""
    data = bytearray(path.read_bytes())
    if data[:4] != b"\x7fELF" or data[5] != 1:
        raise RuntimeError(f"expected a little-endian ELF module: {path}")

    elf_class = data[4]
    if elf_class == 1:
        phoff = struct.unpack_from("<I", data, 28)[0]
        phentsize, phnum = struct.unpack_from("<HH", data, 42)
        ph_format = "<IIIIIIII"
        dynamic_format = "<II"
    elif elf_class == 2:
        phoff = struct.unpack_from("<Q", data, 32)[0]
        phentsize, phnum = struct.unpack_from("<HH", data, 54)
        ph_format = "<IIQQQQQQ"
        dynamic_format = "<QQ"
    else:
        raise RuntimeError(f"unsupported ELF class in {path}")

    loads: list[tuple[int, int, int]] = []
    dynamic: tuple[int, int] | None = None
    for index in range(phnum):
        fields = struct.unpack_from(ph_format, data, phoff + index * phentsize)
        if elf_class == 1:
            segment_type, file_offset, virtual_address, _, file_size = fields[:5]
        else:
            segment_type, _, file_offset, virtual_address, _, file_size = fields[:6]
        if segment_type == 1:
            loads.append((virtual_address, file_offset, file_size))
        elif segment_type == 2:
            dynamic = (file_offset, file_size)
    if dynamic is None:
        raise RuntimeError(f"ELF module has no dynamic table: {path}")

    entry_size = struct.calcsize(dynamic_format)
    entries: list[tuple[int, int, int]] = []
    string_table_address: int | None = None
    dynamic_offset, dynamic_size = dynamic
    for offset in range(dynamic_offset, dynamic_offset + dynamic_size, entry_size):
        tag, value = struct.unpack_from(dynamic_format, data, offset)
        if tag == 0:
            break
        entries.append((offset, tag, value))
        if tag == 5:
            string_table_address = value
    if string_table_address is None:
        raise RuntimeError(f"ELF module has no dynamic string table: {path}")

    string_table_offset: int | None = None
    for virtual_address, file_offset, file_size in loads:
        if virtual_address <= string_table_address < virtual_address + file_size:
            string_table_offset = file_offset + string_table_address - virtual_address
            break
    if string_table_offset is None:
        raise RuntimeError(f"ELF dynamic string table is not loadable: {path}")

    def dependency_name(value: int) -> str:
        """Read a dependency name from the ELF dynamic string table."""
        start = string_table_offset + value
        end = data.index(0, start)
        return data[start:end].decode()

    needed_entries = [entry for entry in entries if entry[1] == 1]
    dependency_offsets = {
        dependency_name(value): value for _, _, value in needed_entries
    }
    replacements = {
        "libresolv.so.2": "libstdc++.so.6",
        "libpthread.so.0": "libgcc_s.so.1",
    }
    for old_name, new_name in replacements.items():
        if old_name not in dependency_offsets:
            raise RuntimeError(f"Zig ELF dependency {old_name} is missing from {path}")
        start = string_table_offset + dependency_offsets[old_name]
        old_size = len(old_name.encode())
        replacement = new_name.encode()
        data[start : start + old_size] = replacement.ljust(old_size, b"\0")

    dependency_offsets = {
        dependency_name(value): value for _, _, value in needed_entries
    }
    expected = {"libc.so.6", "libgcc_s.so.1", "libm.so.6", "libstdc++.so.6"}
    if keep_loader:
        expected.add("ld-linux-aarch64.so.1")
    missing = expected - dependency_offsets.keys()
    if missing:
        raise RuntimeError(
            f"expected ELF dependencies are missing from {path}: {sorted(missing)}"
        )

    # Duplicate libc entries are harmless and avoid retaining Zig's unused glibc group.
    fallback_offset = dependency_offsets["libc.so.6"]
    value_format = "<I" if elf_class == 1 else "<Q"
    value_field_offset = struct.calcsize(value_format)
    for offset, _, value in needed_entries:
        if dependency_name(value) not in expected:
            struct.pack_into(value_format, data, offset + value_field_offset, fallback_offset)

    path.write_bytes(data)


def _build_all_bots(*, release: bool) -> Path:
    """Cross-build and collect all release-compatible ET modules."""
    build_mode = "release" if release else "debug"
    output_directory = BUILD_ROOT / f"omnibot-{build_mode}"
    output_directory.mkdir(parents=True, exist_ok=True)

    for target in ALL_BOT_TARGETS:
        built_module = _build_bot_target(release=release, target=target)
        output_module = output_directory / target.output_name
        shutil.copy2(built_module, output_module)
        if target.system_name == "Linux":
            _conform_zig_elf_dependencies(
                output_module,
                keep_loader=target.keeps_elf_loader,
            )

    # Package the same user-facing metadata as the established bot release.
    shutil.copy2(RELEASE_FILES / "readme.txt", output_directory / "README.txt")
    shutil.copy2(RELEASE_FILES / "changelog.txt", output_directory / "changelog.txt")
    print(f"All bot modules are in {output_directory}")
    return output_directory


def build_bot(*, release: bool, build_all: bool = False) -> None:
    """Build the legacy ET and RTCW bot modules through CMake."""
    if build_all:
        _build_all_bots(release=release)
        return
    build_directory = _configure_bot_build(
        release=release,
        target=LEGACY_BOT_TARGET,
        build_rtcw=True,
    )
    _run_in_pixi(
        [
            "cmake",
            "--build",
            str(build_directory),
            "--target",
            "omnibot-et",
            "omnibot-rtcw",
        ],
        environment=_build_environment(),
    )


def dist() -> None:
    """Copy an existing all-platform release build into the distribution tree."""
    built_release = BUILD_ROOT / "omnibot-release"
    missing = [name for name in DIST_FILES if not (built_release / name).is_file()]
    if missing:
        missing_files = ", ".join(missing)
        raise RuntimeError(
            f"release artifacts are missing: {missing_files}; "
            "run './dev.py build-bot --all --release' first"
        )

    if DIST_DIRECTORY.is_symlink() or (
        DIST_DIRECTORY.exists() and not DIST_DIRECTORY.is_dir()
    ):
        raise RuntimeError(f"distribution path is not a directory: {DIST_DIRECTORY}")
    if DIST_DIRECTORY.exists():
        # Recreate the package so stale artifacts cannot leak into a release.
        shutil.rmtree(DIST_DIRECTORY)
    DIST_DIRECTORY.mkdir(parents=True)
    for name in DIST_FILES:
        shutil.copy2(built_release / name, DIST_DIRECTORY / name)
    print(f"Distribution is in {DIST_DIRECTORY}")


def _parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    build_bot_parser = subcommands.add_parser(
        "build-bot", help="build bot modules for one or all release platforms"
    )
    build_bot_parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="cross-build ET modules for every release platform",
    )
    build_bot_parser.add_argument(
        "--release",
        action="store_true",
        help="build optimized modules without debug information",
    )
    subcommands.add_parser(
        "dist", help="copy an existing all-platform release build into dist"
    )
    return parser


def main() -> None:
    """Dispatch the requested development command."""
    arguments = _parser().parse_args()
    if arguments.command == "build-bot":
        build_bot(release=arguments.release, build_all=arguments.all)
    elif arguments.command == "dist":
        dist()


if __name__ == "__main__":
    main()
