# Windows dynamic dependencies

## Summary

The current Zig Windows builds have a larger dynamic dependency surface than
the reference Omni-bot binaries. This is not caused by new Omni-bot features.
It is a consequence of building the Windows modules for Zig's MinGW ABI, which
uses the Universal C Runtime (UCRT) API-set contracts.

The additional dependencies can reduce compatibility with older Windows
installations. Windows 10 and later include the UCRT as an operating-system
component. Windows 7 SP1 can provide it through Windows Update or the Visual
C++ Redistributable, but an unpatched installation cannot be assumed to have
it. Windows 7 RTM is not supported by the UCRT redistributable.

For a plugin such as Omni-bot, copying the UCRT DLLs beside the plugin is not a
reliable substitute. Microsoft documents that, before Windows 8, app-local
UCRT deployment may fail when a plugin is outside the main executable's
directory.

The recommended solution is to continue using Zig for compilation, target the
MSVC ABI for Windows, and link explicitly against Microsoft's static CRT with
Zig's bundled `lld-link`. This most closely reproduces the original `/MT`
release builds and avoids requiring the UCRT API-set DLLs at runtime.

## Reference and current dependency sets

The reference Windows modules had these dynamic dependencies:

```text
advapi32.dll
kernel32.dll
user32.dll
```

The current 32-bit Zig/MinGW module additionally imports:

```text
api-ms-win-crt-convert-l1-1-0.dll
api-ms-win-crt-environment-l1-1-0.dll
api-ms-win-crt-heap-l1-1-0.dll
api-ms-win-crt-locale-l1-1-0.dll
api-ms-win-crt-math-l1-1-0.dll
api-ms-win-crt-multibyte-l1-1-0.dll
api-ms-win-crt-private-l1-1-0.dll
api-ms-win-crt-runtime-l1-1-0.dll
api-ms-win-crt-stdio-l1-1-0.dll
api-ms-win-crt-string-l1-1-0.dll
api-ms-win-crt-time-l1-1-0.dll
api-ms-win-crt-utility-l1-1-0.dll
```

The current 64-bit module imports the same UCRT contracts plus:

```text
api-ms-win-core-synch-l1-2-0.dll
```

The imports correspond to real runtime use. Examples include allocation,
standard I/O, string conversion, locale handling, time functions, math
functions, and C/C++ runtime initialization. They are not merely unused names
left in the PE import table.

## Why the dependency surface changed

The historical MSVC release configuration selects the static multithreaded
runtime through CMake's `MultiThreaded` setting, which is equivalent to MSVC's
`/MT` option. That setting applies only when the compiler ABI is MSVC.

The cross-build targets are currently:

```text
x86-windows-gnu
x86_64-windows-gnu
```

Those targets select Zig's bundled MinGW environment. Zig 0.15.2 adds a fixed
set of UCRT API-set import libraries to MinGW links. The linker removes wholly
unused contracts, but every contract containing a referenced function remains
in the finished DLL. `CMAKE_MSVC_RUNTIME_LIBRARY` has no effect on these GNU
ABI builds.

Zig's MinGW library list is visible in the
[Zig 0.15.2 source](https://github.com/ziglang/zig/blob/0.15.2/src/libs/mingw.zig#L1015-L1035).

## Older Windows impact

The current binaries are not necessarily unusable on every older Windows
installation, but they no longer have the same self-contained compatibility
properties as the reference binaries.

- Windows 10 and later include the UCRT.
- Windows 7 SP1 can satisfy the UCRT contracts after installing the applicable
  Windows update or Visual C++ Redistributable.
- Windows 7 RTM cannot install the supported UCRT redistributable.
- Offline or minimally patched Windows 7 systems may not have the UCRT.
- App-local UCRT deployment has restrictions for plugins on systems before
  Windows 8.
- Removing the UCRT names alone does not prove compatibility. The final PE
  imports must also be checked for individual operating-system functions that
  were introduced after the intended minimum Windows version.

Microsoft describes these deployment requirements and restrictions in its
[Universal CRT deployment documentation](https://learn.microsoft.com/en-us/cpp/windows/universal-crt-deployment?view=msvc-170).

## Tested Zig behavior

The following behavior was verified with the project's pinned Zig 0.15.2.

### Explicit Windows 7 GNU target

Changing a test build from `x86_64-windows-gnu` to
`x86_64-windows.win7-gnu` removed the
`api-ms-win-core-synch-l1-2-0.dll` import. The UCRT API-set dependencies
remained.

Using an explicit Windows version is therefore worthwhile, but it does not
make the module self-contained:

```text
x86-windows.win7-gnu
x86_64-windows.win7-gnu
```

### Generic static option

Adding `-static` to a Zig C++ shared-library invocation does not produce a DLL
with a statically linked CRT. In this mode Zig changes the requested library
artifact into a static archive. It is not a solution for an Omni-bot module.

### MSVC target without an external SDK

Zig cannot provide the Microsoft CRT for a `windows-msvc` target by itself.
It requires external MSVC CRT and Windows SDK headers and libraries. Zig's
libc configuration format has fields for these external directories.

For a normal DLL link, Zig 0.15.2 also selects its dynamic MSVC CRT path based
on the DLL's dynamic link mode. Its linker implementation knows the correct
static libraries, but the Omni-bot build must select them explicitly rather
than relying on the default DLL link.

The relevant selection is visible in the
[Zig 0.15.2 COFF linker source](https://github.com/ziglang/zig/blob/0.15.2/src/link/Lld.zig#L674-L694).

## Available approaches

### 1. Zig compilation with the static Microsoft CRT

This is the recommended approach.

Compile the Windows objects for an explicitly versioned MSVC target:

```text
x86-windows.win7-msvc
x86_64-windows.win7-msvc
```

Provide pinned MSVC CRT and Windows SDK installations for both architectures,
then perform the final DLL link through Zig's bundled `lld-link`. The release
link should suppress dynamic default CRT selection and explicitly include the
static libraries, including:

```text
libcmt.lib
libvcruntime.lib
libucrt.lib
legacy_stdio_definitions.lib
```

The link must also include the required Windows SDK import libraries, such as
`kernel32.lib`, `user32.lib`, and `advapi32.lib`.

Advantages:

- Keeps Zig as the cross-compiler and keeps LLVM's linker.
- Restores the static-runtime model used by the reference release.
- Avoids requiring UCRT API-set DLLs on the destination system.
- Uses Microsoft's supported static UCRT implementation.

Costs:

- Requires pinned Microsoft CRT and Windows SDK inputs in every supported
  build environment.
- Requires a deliberate CMake link rule instead of Zig's default DLL link.
- Must account for Microsoft SDK licensing and redistribution terms.
- Changes the Windows C++ ABI from GNU to MSVC, so the complete module must be
  built consistently with the same ABI.

The Omni-bot module exposes a C entry-point interface, so the internal C++ ABI
change should not affect the game interface, but this must be confirmed during
implementation and testing.

### 2. Retain MinGW and use legacy `msvcrt.dll`

It is possible in principle to bypass Zig's automatic MinGW runtime link,
rebuild the MinGW startup/runtime objects for the legacy Microsoft CRT, and
link against `msvcrt.dll`.

This would remove the UCRT API-set dependencies and provide broad older
Windows availability, but it would not reproduce the fully static reference
build. The module would have a dynamic `msvcrt.dll` dependency. It would also
require maintaining custom CRT construction and linker behavior outside Zig's
supported MinGW path.

This approach is not recommended unless the MSVC static libraries cannot be
made available to the build.

### 3. Build a custom static GNU CRT

A custom CRT could theoretically combine Zig's GNU C++ runtime with a static C
runtime implementation. In practice this requires ownership of startup code,
CRT initialization, exception handling, thread support, header import
annotations, and linker behavior. It would be a substantial runtime port, not
a normal build-system adjustment.

This approach is not recommended.

### 4. Deploy the UCRT dynamically

The UCRT can be installed centrally through Windows Update or the Visual C++
Redistributable. It can also be deployed locally under some conditions.

This retains the current Zig/MinGW build but does not meet the goal of
self-contained plugin DLLs. The documented pre-Windows-8 plugin restriction
also makes local deployment unsuitable as the primary compatibility strategy.

## Recommended implementation plan

1. Define the actual minimum Windows release. Windows 7 SP1 is a practical
   initial target. Windows XP requires an older XP-capable toolset and a
   separate compatibility analysis.
2. Change the Windows compilation targets to the explicitly versioned MSVC ABI
   targets.
3. Add pinned MSVC CRT and Windows SDK inputs for x86 and x86-64 builds.
4. Keep Zig as the compiler frontend and use Zig's bundled `lld-link` for the
   final link.
5. Add a CMake Windows link rule that suppresses dynamic CRT defaults and
   explicitly selects the static CRT libraries.
6. Restore the strict reference dependency expectations in
   `Tools/check-dist.py` instead of accepting the UCRT API-set imports.
7. Rebuild both Windows architectures and inspect their normal and delay-load
   import tables.
8. Test loading and exercising each module on clean Windows 7 SP1 x86 and x64
   virtual machines without the Visual C++ Redistributable installed.
9. If Windows XP is required, repeat the build with an XP-capable toolset and
   test it independently. Dependency names alone are insufficient proof of XP
   compatibility.

## Acceptance criteria

The Windows compatibility work is complete when:

- both Windows modules are valid DLLs rather than static archives;
- neither module imports an `api-ms-win-crt-*` library;
- neither module imports `api-ms-win-core-synch-l1-2-0.dll`;
- the dependency checker enforces the intended minimal import set;
- the modules load successfully in the oldest supported clean Windows
  environments; and
- all existing Linux and macOS cross-build and distribution checks continue to
  pass.
