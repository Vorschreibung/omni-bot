#!/usr/bin/env python3
"""Cross-platform development entrypoint for omni-bot."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from collections.abc import Sequence


ROOT = Path(__file__).resolve().parent
PIXI_MANIFEST = ROOT / "pixi.toml"
OMNIBOT_SOURCE = ROOT / "Omnibot"
BUILD_ROOT = OMNIBOT_SOURCE / "build"
RELEASE_FILES = ROOT / "Installer" / "Files" / "rtcw"
DIST_DIRECTORY = ROOT / "dist"


@dataclass(frozen=True)
class BotBuildTarget:
    """Describe one cross-compiled ET module in the all-platform build."""

    name: str
    cross_file: Path | None
    output_name: str
    meson_output_name: str
    keeps_elf_loader: bool = False
    windows_arch: str | None = None


@dataclass(frozen=True)
class WindowsToolchain:
    """Paths required to combine Zig with the locally installed MSVC SDK."""

    target: str
    machine: str
    include_directories: tuple[Path, ...]
    vc_library_directory: Path
    ucrt_library_directory: Path
    system_library_directory: Path
    include_overlay: Path
    library_aliases: Path


def _bot_target(
    name: str,
    cross_file: str | None,
    output_name: str,
    meson_output_name: str,
    *,
    keeps_elf_loader: bool = False,
    windows_arch: str | None = None,
) -> BotBuildTarget:
    """Create a target using a cross file from the project's Meson directory."""
    return BotBuildTarget(
        name=name,
        cross_file=OMNIBOT_SOURCE / "meson" / cross_file if cross_file else None,
        output_name=output_name,
        meson_output_name=meson_output_name,
        keeps_elf_loader=keeps_elf_loader,
        windows_arch=windows_arch,
    )


LEGACY_BOT_TARGET = _bot_target(
    "x86-linux",
    "zig-x86-linux.ini",
    "omnibot_et.so",
    "omnibot_et.so",
)
ALL_BOT_TARGETS = (
    _bot_target(
        "aarch64-linux",
        "zig-aarch64-linux.ini",
        "omnibot_et.aarch64.so",
        "omnibot_et.so",
        keeps_elf_loader=True,
    ),
    _bot_target(
        "x86-windows",
        None,
        "omnibot_et.dll",
        "omnibot_et.dll",
        windows_arch="x86",
    ),
    LEGACY_BOT_TARGET,
    _bot_target(
        "x86_64-linux",
        "zig-x86_64-linux.ini",
        "omnibot_et.x86_64.so",
        "omnibot_et.so",
    ),
    _bot_target(
        "x86_64-macos",
        "zig-x86_64-macos.ini",
        "omnibot_et_mac.so",
        "omnibot_et.dylib",
    ),
    _bot_target(
        "x86_64-windows",
        None,
        "omnibot_et_x64.dll",
        "omnibot_et.dll",
        windows_arch="x64",
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


def _posix_lmsvc_path(value: str) -> Path:
    """Convert the Wine paths reported by lmsvc into host filesystem paths."""
    if len(value) >= 3 and value[1:3] == ":\\":
        if value[0].upper() != "Z":
            raise RuntimeError(f"unsupported lmsvc drive in path: {value}")
        value = "/" + value[3:]
    return Path(value.replace("\\", "/"))


def _matching_path(
    paths: Sequence[Path], marker: str, description: str
) -> Path:
    """Select one lmsvc path by a stable directory marker."""
    matches = [path for path in paths if marker in path.as_posix()]
    if len(matches) != 1:
        raise RuntimeError(f"could not identify the {description} from lmsvc")
    return matches[0]


def _link_alias(alias: Path, target: Path) -> None:
    """Create a generated case-correcting link without replacing real files."""
    if alias.is_symlink():
        if Path(os.readlink(alias)) == target:
            return
        # Refresh generated links when lmsvc installs a newer SDK toolchain.
        alias.unlink()
    elif alias.exists():
        return
    alias.symlink_to(target)


def _windows_toolchain(arch: str) -> WindowsToolchain:
    """Discover MSVC headers and static runtime libraries through lmsvc."""
    lmsvc = shutil.which("lmsvc")
    if not lmsvc:
        raise RuntimeError(
            "lmsvc with a Visual Studio 2022 toolchain is required for Windows builds"
        )
    environment_output = subprocess.run(
        [lmsvc, "env", "--arch", arch, "--plain"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    environment = dict(
        line.split("=", 1)
        for line in environment_output.splitlines()
        if "=" in line
    )
    try:
        include_directories = tuple(
            _posix_lmsvc_path(value)
            for value in environment["INCLUDE"].split(";")
        )
        library_directories = tuple(
            _posix_lmsvc_path(value) for value in environment["LIB"].split(";")
        )
    except KeyError as error:
        raise RuntimeError("lmsvc did not report INCLUDE and LIB paths") from error

    vc_library_directory = _matching_path(
        library_directories, "/VC/Tools/MSVC/", "MSVC library directory"
    )
    ucrt_library_directory = _matching_path(
        library_directories, "/ucrt/", "UCRT library directory"
    )
    system_library_directory = _matching_path(
        library_directories, "/um/", "Windows SDK library directory"
    )
    include_overlay = BUILD_ROOT / "msvc-include-overlay"
    library_aliases = BUILD_ROOT / f"msvc-{arch}-libraries"
    include_overlay.mkdir(parents=True, exist_ok=True)
    library_aliases.mkdir(parents=True, exist_ok=True)

    # Windows headers assume a case-insensitive filesystem. Lowercase aliases cover
    # their includes while preserving the SDK installed by lmsvc outside the repo.
    for include_directory in include_directories[:4]:
        for header in include_directory.iterdir():
            if header.is_file():
                _link_alias(include_overlay / header.name.lower(), header)
    for spelling in ("DriverSpecs.h", "SpecStrings.h"):
        _link_alias(include_overlay / spelling, Path(spelling.lower()))

    # The SDK also mixes filename case in its .lib files, while Meson emits
    # lowercase library names for Windows system dependencies.
    system_libraries = tuple(system_library_directory.iterdir())
    for name in (
        "kernel32.lib",
        "user32.lib",
        "gdi32.lib",
        "winspool.lib",
        "shell32.lib",
        "ole32.lib",
        "oleaut32.lib",
        "uuid.lib",
        "comdlg32.lib",
        "advapi32.lib",
    ):
        candidates = [path for path in system_libraries if path.name.lower() == name]
        if len(candidates) != 1:
            raise RuntimeError(f"could not find {name} in the Windows SDK")
        _link_alias(library_aliases / name, candidates[0])

    if arch == "x86":
        target, machine = "x86-windows-msvc", "x86"
    elif arch == "x64":
        target, machine = "x86_64-windows-msvc", "x64"
    else:
        raise ValueError(f"unsupported Windows architecture: {arch}")
    return WindowsToolchain(
        target=target,
        machine=machine,
        include_directories=include_directories,
        vc_library_directory=vc_library_directory,
        ucrt_library_directory=ucrt_library_directory,
        system_library_directory=system_library_directory,
        include_overlay=include_overlay,
        library_aliases=library_aliases,
    )


def _windows_cross_file(target: BotBuildTarget) -> Path:
    """Generate a Meson machine file for Zig's MSVC-compatible target ABI."""
    if target.windows_arch is None:
        raise ValueError(f"{target.name} is not a Windows target")
    toolchain = _windows_toolchain(target.windows_arch)
    compile_arguments = [
        f"--target={toolchain.target}",
        "-nostdlib",
        *(
            argument
            for directory in (toolchain.include_overlay, *toolchain.include_directories[:4])
            for argument in ("-isystem", str(directory))
        ),
    ]
    runtime_libraries = [
        toolchain.vc_library_directory / "libcmt.lib",
        toolchain.vc_library_directory / "libvcruntime.lib",
        toolchain.vc_library_directory / "oldnames.lib",
        toolchain.ucrt_library_directory / "libucrt.lib",
    ]
    link_arguments = [
        f"--target={toolchain.target}",
        "-nostdlib",
        f"-L{toolchain.library_aliases}",
        *(str(path) for path in runtime_libraries),
    ]
    cpp_link_arguments = [
        *link_arguments[:3],
        str(toolchain.vc_library_directory / "libcpmt.lib"),
        *link_arguments[3:],
    ]
    machine_file = BUILD_ROOT / "machine-files" / f"zig-{target.name}.ini"
    machine_file.parent.mkdir(parents=True, exist_ok=True)
    # repr() produces the quoted list syntax accepted by Meson machine files.
    machine_file.write_text(
        "\n".join(
            (
                "[binaries]",
                "c = ['zig', 'cc']",
                "cpp = ['zig', 'c++']",
                "ar = ['zig', 'ar']",
                "strip = ['zig', 'strip']",
                "",
                "[properties]",
                "needs_exe_wrapper = true",
                "",
                "[built-in options]",
                f"c_args = {compile_arguments!r}",
                f"c_link_args = {link_arguments!r}",
                f"cpp_args = {compile_arguments!r}",
                f"cpp_link_args = {cpp_link_arguments!r}",
                "",
                "[host_machine]",
                "system = 'windows'",
                f"cpu_family = '{'x86' if target.windows_arch == 'x86' else 'x86_64'}'",
                f"cpu = '{'x86' if target.windows_arch == 'x86' else 'x86_64'}'",
                "endian = 'little'",
                "",
            )
        )
    )
    return machine_file


def _cross_file_for_target(target: BotBuildTarget) -> Path:
    """Return the static or generated Meson machine file for a build target."""
    if target.windows_arch:
        return _windows_cross_file(target)
    if target.cross_file is None:
        raise RuntimeError(f"no cross file is configured for {target.name}")
    return target.cross_file


def _configure_bot_build(
    *, release: bool, tests: bool, target: BotBuildTarget = LEGACY_BOT_TARGET
) -> tuple[Path, dict[str, str]]:
    """Configure a bot build and return its path and environment."""
    if not sys.platform.startswith("linux"):
        raise RuntimeError("Zig bot cross builds currently require Linux")
    if tests and target != LEGACY_BOT_TARGET:
        raise ValueError("bot tests only support the legacy 32-bit Linux target")

    build_mode = "release" if release else "debug"
    # Tests use their own tree so enabling them never changes the bot build outputs.
    meson_build_name = (
        "meson-tests-x86"
        if tests
        else f"meson-{build_mode}-{target.name}"
    )
    meson_build = BUILD_ROOT / meson_build_name
    zig_cache = BUILD_ROOT / ".zig-cache"
    cross_files = [_cross_file_for_target(target)]
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

    # Restrict the host fallback to Boost so cross builds never see host libc headers.
    host_include = meson_build / "host-include"
    host_include.mkdir(parents=True, exist_ok=True)
    boost_include = host_include / "boost"
    if not boost_include.exists():
        boost_include.symlink_to("/usr/include/boost", target_is_directory=True)

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


def _build_bot_target(*, release: bool, target: BotBuildTarget) -> Path:
    """Build one ET module and return its path in the Meson tree."""
    meson_build, build_environment = _configure_bot_build(
        release=release,
        tests=False,
        target=target,
    )
    if target.windows_arch:
        # Zig 0.16 currently crashes while driving a large MSVC-ABI DLL link.
        # Compile every object with Zig, then invoke the same LLD COFF backend
        # directly to link against the static Microsoft runtime.
        object_directory = "omnibot_et.dll.p"
        _run_in_pixi(
            [
                "ninja",
                "-C",
                str(meson_build),
                "libomnibot-common.a",
                f"{object_directory}/ET_ET_BatchBuild.cpp.obj",
                f"{object_directory}/meson_windows_dependency_anchor.c.obj",
            ],
            environment=build_environment,
        )
        _link_windows_bot(meson_build, target)
    else:
        _run_in_pixi(
            ["meson", "compile", "-C", str(meson_build), "omnibot_et"],
            environment=build_environment,
        )
    return meson_build / target.meson_output_name


def _link_windows_bot(meson_build: Path, target: BotBuildTarget) -> None:
    """Link Zig-produced COFF objects with the MSVC static runtime."""
    if target.windows_arch is None:
        raise ValueError(f"{target.name} is not a Windows target")
    linker = shutil.which("lld-link")
    if not linker:
        raise RuntimeError("lld-link is required for Windows bot builds")
    toolchain = _windows_toolchain(target.windows_arch)
    object_directory = meson_build / "omnibot_et.dll.p"
    runtime_libraries = [
        toolchain.vc_library_directory / "libcpmt.lib",
        toolchain.vc_library_directory / "libcmt.lib",
        toolchain.vc_library_directory / "libvcruntime.lib",
        toolchain.vc_library_directory / "oldnames.lib",
        toolchain.ucrt_library_directory / "libucrt.lib",
    ]
    command = [
        linker,
        "/dll",
        f"/out:{meson_build / target.meson_output_name}",
        f"/machine:{toolchain.machine}",
        "/subsystem:console",
        "/opt:ref",
        "/opt:icf",
        str(object_directory / "ET_ET_BatchBuild.cpp.obj"),
        str(object_directory / "meson_windows_dependency_anchor.c.obj"),
        str(meson_build / "libomnibot-common.a"),
        *(str(path) for path in runtime_libraries),
        f"/libpath:{toolchain.library_aliases}",
        "kernel32.lib",
        "user32.lib",
        "advapi32.lib",
    ]
    subprocess.run(command, cwd=ROOT, check=True)


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
        if target.output_name.endswith(".so") and "mac" not in target.output_name:
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
    """Build legacy bot modules for one or all supported platforms."""
    if build_all:
        _build_all_bots(release=release)
        return
    meson_build, build_environment = _configure_bot_build(
        release=release,
        tests=False,
    )
    _run_in_pixi(
        ["meson", "compile", "-C", str(meson_build)],
        environment=build_environment,
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
    DIST_DIRECTORY.mkdir()
    for name in DIST_FILES:
        shutil.copy2(built_release / name, DIST_DIRECTORY / name)
    print(f"Distribution is in {DIST_DIRECTORY}")


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
    subcommands.add_parser("test", help="run the 32-bit Linux behavior tests")
    return parser


def main() -> None:
    """Dispatch the requested development command."""
    arguments = _parser().parse_args()
    if arguments.command == "build-bot":
        build_bot(release=arguments.release, build_all=arguments.all)
    elif arguments.command == "dist":
        dist()
    elif arguments.command == "test":
        test_bot()


if __name__ == "__main__":
    main()
