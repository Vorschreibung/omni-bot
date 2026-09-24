#!/usr/bin/env python3
"""Check an Omni-bot directory against an embedded release manifest."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path


class BinaryFormatError(ValueError):
    """Raised when a shared library's dependency table cannot be read safely."""


# This manifest snapshots the top-level files and linked libraries from the
# reference omni-bot directory at the time this standalone checker was created.
EXPECTED_FILES = frozenset(
    {
        "README.txt",
        "changelog.txt",
        "omnibot_et.aarch64.so",
        "omnibot_et.dll",
        "omnibot_et.so",
        "omnibot_et.x86_64.so",
        "omnibot_et_mac.so",
        "omnibot_et_x64.dll",
    }
)

EXPECTED_DEPENDENCIES = {
    "omnibot_et.aarch64.so": frozenset(
        {
            "ld-linux-aarch64.so.1",
            "libc.so.6",
            "libgcc_s.so.1",
            "libm.so.6",
            "libstdc++.so.6",
        }
    ),
    "omnibot_et.dll": frozenset(
        {
            "advapi32.dll",
            "kernel32.dll",
            "user32.dll",
        }
    ),
    "omnibot_et.so": frozenset(
        {
            "libc.so.6",
            "libgcc_s.so.1",
            "libm.so.6",
            "libstdc++.so.6",
        }
    ),
    "omnibot_et.x86_64.so": frozenset(
        {
            "libc.so.6",
            "libgcc_s.so.1",
            "libm.so.6",
            "libstdc++.so.6",
        }
    ),
    "omnibot_et_mac.so": frozenset(
        {
            "/System/Library/Frameworks/ApplicationServices.framework/Versions/A/ApplicationServices",
            "/System/Library/Frameworks/Carbon.framework/Versions/A/Carbon",
            "/System/Library/Frameworks/CoreFoundation.framework/Versions/A/CoreFoundation",
            "/System/Library/Frameworks/CoreServices.framework/Versions/A/CoreServices",
            "/System/Library/Frameworks/IOKit.framework/Versions/A/IOKit",
            "/usr/lib/libSystem.B.dylib",
            "/usr/lib/libc++.1.dylib",
        }
    ),
    "omnibot_et_x64.dll": frozenset(
        {
            "advapi32.dll",
            "kernel32.dll",
            "user32.dll",
        }
    ),
}


def unpack_from(fmt: str, data: bytes, offset: int, context: str) -> tuple[int, ...]:
    """Unpack a structure while turning truncated data into a useful error."""
    try:
        return struct.unpack_from(fmt, data, offset)
    except struct.error as error:
        raise BinaryFormatError(f"truncated {context}") from error


def c_string(data: bytes, offset: int, context: str, limit: int | None = None) -> str:
    """Read a bounded, UTF-8-compatible C string from a binary image."""
    if offset < 0 or offset >= len(data):
        raise BinaryFormatError(f"invalid {context} string offset 0x{offset:x}")
    end_limit = min(len(data), limit) if limit is not None else len(data)
    end = data.find(b"\0", offset, end_limit)
    if end == -1:
        raise BinaryFormatError(f"unterminated {context} string")
    return data[offset:end].decode("utf-8", errors="surrogateescape")


def elf_dependencies(data: bytes) -> set[str]:
    """Return DT_NEEDED entries from a 32-bit or 64-bit ELF image."""
    if len(data) < 16 or data[:4] != b"\x7fELF":
        raise BinaryFormatError("not an ELF image")

    elf_class, encoding = data[4], data[5]
    if elf_class not in (1, 2) or encoding not in (1, 2):
        raise BinaryFormatError("unsupported ELF class or byte order")
    endian = "<" if encoding == 1 else ">"

    if elf_class == 1:
        phoff = unpack_from(endian + "I", data, 28, "ELF header")[0]
        phentsize, phnum = unpack_from(endian + "HH", data, 42, "ELF header")
        expected_phentsize = 32
    else:
        phoff = unpack_from(endian + "Q", data, 32, "ELF header")[0]
        phentsize, phnum = unpack_from(endian + "HH", data, 54, "ELF header")
        expected_phentsize = 56
    if phentsize < expected_phentsize:
        raise BinaryFormatError("invalid ELF program-header size")

    loads: list[tuple[int, int, int]] = []
    dynamic: tuple[int, int] | None = None
    for index in range(phnum):
        offset = phoff + index * phentsize
        if elf_class == 1:
            fields = unpack_from(endian + "IIIIIIII", data, offset, "ELF program header")
            p_type, p_offset, p_vaddr, _, p_filesz = fields[:5]
        else:
            fields = unpack_from(endian + "IIQQQQQQ", data, offset, "ELF program header")
            p_type, _, p_offset, p_vaddr, _, p_filesz = fields[:6]
        if p_offset + p_filesz > len(data):
            raise BinaryFormatError("ELF segment extends beyond the file")
        if p_type == 1:  # PT_LOAD maps dynamic virtual addresses to file offsets.
            loads.append((p_vaddr, p_offset, p_filesz))
        elif p_type == 2:  # PT_DYNAMIC contains DT_NEEDED and DT_STRTAB entries.
            dynamic = (p_offset, p_filesz)

    if dynamic is None:
        return set()

    entry_size = 8 if elf_class == 1 else 16
    entry_format = endian + ("II" if elf_class == 1 else "QQ")
    needed_offsets: list[int] = []
    string_table_address: int | None = None
    dynamic_offset, dynamic_size = dynamic
    for offset in range(dynamic_offset, dynamic_offset + dynamic_size, entry_size):
        tag, value = unpack_from(entry_format, data, offset, "ELF dynamic entry")
        if tag == 0:  # DT_NULL terminates the dynamic array.
            break
        if tag == 1:  # DT_NEEDED values are offsets within DT_STRTAB.
            needed_offsets.append(value)
        elif tag == 5:  # DT_STRTAB is a virtual address.
            string_table_address = value

    if needed_offsets and string_table_address is None:
        raise BinaryFormatError("ELF DT_NEEDED entries have no DT_STRTAB")
    if string_table_address is None:
        return set()

    for address, file_offset, file_size in loads:
        if address <= string_table_address < address + file_size:
            string_table_offset = file_offset + string_table_address - address
            return {
                c_string(data, string_table_offset + offset, "ELF dependency")
                for offset in needed_offsets
            }
    raise BinaryFormatError("ELF string table is not in a loadable segment")


def pe_dependencies(data: bytes) -> set[str]:
    """Return normal and delay-loaded imports from a PE32 or PE32+ image."""
    if len(data) < 64 or data[:2] != b"MZ":
        raise BinaryFormatError("not a PE image")
    pe_offset = unpack_from("<I", data, 0x3C, "DOS header")[0]
    if data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise BinaryFormatError("invalid PE signature")

    coff_offset = pe_offset + 4
    _, section_count, _, _, _, optional_size, _ = unpack_from(
        "<HHIIIHH", data, coff_offset, "PE COFF header"
    )
    optional_offset = coff_offset + 20
    magic = unpack_from("<H", data, optional_offset, "PE optional header")[0]
    if magic == 0x10B:
        image_base = unpack_from("<I", data, optional_offset + 28, "PE image base")[0]
        directory_count_offset, directories_offset = 92, 96
    elif magic == 0x20B:
        image_base = unpack_from("<Q", data, optional_offset + 24, "PE image base")[0]
        directory_count_offset, directories_offset = 108, 112
    else:
        raise BinaryFormatError(f"unsupported PE optional-header magic 0x{magic:x}")
    if optional_size < directories_offset:
        raise BinaryFormatError("truncated PE optional header")

    directory_count = unpack_from(
        "<I", data, optional_offset + directory_count_offset, "PE data-directory count"
    )[0]
    section_offset = optional_offset + optional_size
    sections: list[tuple[int, int, int]] = []
    for index in range(section_count):
        offset = section_offset + index * 40
        virtual_size, virtual_address, raw_size, raw_offset = unpack_from(
            "<IIII", data, offset + 8, "PE section header"
        )
        sections.append((virtual_address, max(virtual_size, raw_size), raw_offset))

    def rva_to_offset(rva: int) -> int:
        """Translate a relative virtual address through the PE section table."""
        for virtual_address, mapped_size, raw_offset in sections:
            if virtual_address <= rva < virtual_address + mapped_size:
                result = raw_offset + rva - virtual_address
                if result >= len(data):
                    break
                return result
        raise BinaryFormatError(f"PE RVA 0x{rva:x} is not backed by file data")

    def directory(index: int) -> tuple[int, int]:
        """Read one optional-header data-directory entry when it is present."""
        if index >= directory_count or directories_offset + (index + 1) * 8 > optional_size:
            return (0, 0)
        return unpack_from(
            "<II",
            data,
            optional_offset + directories_offset + index * 8,
            "PE data directory",
        )

    dependencies: set[str] = set()
    import_rva, import_size = directory(1)
    if import_rva:
        offset = rva_to_offset(import_rva)
        end = min(len(data), offset + import_size) if import_size else len(data)
        while offset + 20 <= end:
            descriptor = unpack_from("<IIIII", data, offset, "PE import descriptor")
            if not any(descriptor):
                break
            dependencies.add(c_string(data, rva_to_offset(descriptor[3]), "PE import"))
            offset += 20
        else:
            raise BinaryFormatError("unterminated PE import directory")

    delay_rva, delay_size = directory(13)
    if delay_rva:
        offset = rva_to_offset(delay_rva)
        end = min(len(data), offset + delay_size) if delay_size else len(data)
        while offset + 32 <= end:
            descriptor = unpack_from("<IIIIIIII", data, offset, "PE delay-import descriptor")
            if not any(descriptor):
                break
            attributes, name_address = descriptor[:2]
            name_rva = name_address if attributes & 1 else name_address - image_base
            dependencies.add(c_string(data, rva_to_offset(name_rva), "PE delay import"))
            offset += 32
        else:
            raise BinaryFormatError("unterminated PE delay-import directory")

    # Windows DLL lookup is case-insensitive, so spelling case is not semantic.
    return {dependency.casefold() for dependency in dependencies}


def thin_macho_dependencies(data: bytes, image_offset: int, image_size: int) -> set[str]:
    """Return dylib load commands from one thin image inside a Mach-O file."""
    magic = data[image_offset : image_offset + 4]
    formats = {
        b"\xce\xfa\xed\xfe": ("<", 28),
        b"\xfe\xed\xfa\xce": (">", 28),
        b"\xcf\xfa\xed\xfe": ("<", 32),
        b"\xfe\xed\xfa\xcf": (">", 32),
    }
    if magic not in formats:
        raise BinaryFormatError("unsupported Mach-O image magic")
    endian, header_size = formats[magic]
    ncmds, sizeofcmds = unpack_from(
        endian + "II", data, image_offset + 16, "Mach-O header"
    )
    commands_offset = image_offset + header_size
    commands_end = commands_offset + sizeofcmds
    image_end = image_offset + image_size
    if commands_end > image_end or image_end > len(data):
        raise BinaryFormatError("Mach-O load commands extend beyond the image")

    # These are the load commands that introduce runtime dylib dependencies.
    dylib_commands = {0xC, 0x80000018, 0x8000001F, 0x20, 0x80000023}
    dependencies: set[str] = set()
    offset = commands_offset
    for _ in range(ncmds):
        command, command_size = unpack_from(endian + "II", data, offset, "Mach-O load command")
        if command_size < 8 or offset + command_size > commands_end:
            raise BinaryFormatError("invalid Mach-O load-command size")
        if command in dylib_commands:
            name_offset = unpack_from(endian + "I", data, offset + 8, "Mach-O dylib command")[0]
            if name_offset >= command_size:
                raise BinaryFormatError("invalid Mach-O dylib name offset")
            dependencies.add(
                c_string(data, offset + name_offset, "Mach-O dependency", offset + command_size)
            )
        offset += command_size
    return dependencies


def macho_dependencies(data: bytes) -> set[str]:
    """Return dylib dependencies from a thin or universal Mach-O file."""
    magic = data[:4]
    if magic in {b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xce", b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf"}:
        return thin_macho_dependencies(data, 0, len(data))

    fat_formats = {
        b"\xca\xfe\xba\xbe": (">", False),
        b"\xbe\xba\xfe\xca": ("<", False),
        b"\xca\xfe\xba\xbf": (">", True),
        b"\xbf\xba\xfe\xca": ("<", True),
    }
    if magic not in fat_formats:
        raise BinaryFormatError("not a Mach-O image")
    endian, is_64_bit = fat_formats[magic]
    architecture_count = unpack_from(endian + "I", data, 4, "Mach-O fat header")[0]
    architecture_size = 32 if is_64_bit else 20
    dependencies: set[str] = set()
    for index in range(architecture_count):
        offset = 8 + index * architecture_size
        if is_64_bit:
            _, _, image_offset, image_size, _, _ = unpack_from(
                endian + "IIQQII", data, offset, "Mach-O fat architecture"
            )
        else:
            _, _, image_offset, image_size, _ = unpack_from(
                endian + "IIIII", data, offset, "Mach-O fat architecture"
            )
        dependencies.update(thin_macho_dependencies(data, image_offset, image_size))
    return dependencies


def binary_dependencies(path: Path) -> set[str]:
    """Detect a shared-library format and return its direct dependencies."""
    data = path.read_bytes()
    if data.startswith(b"\x7fELF"):
        return elf_dependencies(data)
    if data.startswith(b"MZ"):
        return pe_dependencies(data)
    return macho_dependencies(data)


def compare_directory(target: Path) -> list[str]:
    """Return all missing files and dependency mismatches in one pass."""
    errors: list[str] = []
    for filename in sorted(EXPECTED_FILES):
        target_file = target / filename
        if not target_file.is_file():
            errors.append(f"missing top-level file: {target_file}")
            continue
        if filename not in EXPECTED_DEPENDENCIES:
            continue
        try:
            actual = binary_dependencies(target_file)
        except (BinaryFormatError, OSError) as error:
            errors.append(f"cannot inspect target {target_file}: {error}")
            continue
        expected = EXPECTED_DEPENDENCIES[filename]
        if expected != actual:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if extra:
                details.append("extra " + ", ".join(extra))
            errors.append(f"dependency mismatch for {target_file}: {'; '.join(details)}")
    return errors


def main() -> int:
    """Parse the target directory, run all checks, and provide a shell-friendly status."""
    parser = argparse.ArgumentParser(
        description=(
            "Check that a directory contains every file in the embedded Omni-bot "
            "manifest and that its .dll/.so files have the expected dependencies."
        )
    )
    parser.add_argument("directory", type=Path, help="Omni-bot directory to check")
    args = parser.parse_args()

    target = args.directory.resolve()
    if not target.is_dir():
        parser.error(f"target directory does not exist: {target}")

    errors = compare_directory(target)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"OK: {target} matches the embedded Omni-bot manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
