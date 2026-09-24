project(
    'omnibot',
    ['c', 'cpp'],
    version: '0.93',
    meson_version: '>=1.1',
    default_options: [
        'b_staticpic=true',
        'c_std=gnu99',
        'cpp_std=c++17',
        'warning_level=0',
    ],
)

# Standalone mode makes the vendored Boost.Regex implementation header-only.
boost_regex_dependency = declare_dependency(
    include_directories: include_directories('dependencies/boost-regex/include'),
    compile_args: [
        '-DBOOST_REGEX_STANDALONE',
        # dev.py exposes only the host Boost tree, not incompatible host libc headers.
        '-isystem',
        meson.project_build_root() / 'host-include',
    ],
)

common_arguments = ['-fno-strict-aliasing']
if host_machine.system() == 'linux'
    common_arguments += '-D__linux__'
elif host_machine.system() == 'windows'
    # The legacy sources use WIN32 in addition to the compiler-provided _WIN32.
    common_arguments += '-DWIN32'
endif
add_project_arguments(common_arguments, language: ['c', 'cpp'])
# Omni-bot intentionally embeds its build timestamp in IGame::GetVersion().
add_project_arguments('-Wno-date-time', language: 'cpp')
# Vendored GameMonkey sources still use the register keyword removed in C++17.
add_project_arguments('-Wno-register', language: 'cpp')
if get_option('buildtype') == 'release'
    # Keep debug data out of Zig's compiler and runtime objects in release builds.
    add_project_arguments('-g0', language: ['c', 'cpp'])
    add_project_link_arguments('-Wl,--strip-debug', language: ['c', 'cpp'])
endif

physfs_c_arguments = []
if host_machine.system() == 'linux'
    # This vendored PhysicsFS version uses alloca without including its Linux declaration.
    physfs_c_arguments += ['-include', 'alloca.h']
endif

gm_platform_include = 'dependencies/gmscriptex/gmsrc_ex/src/platform/win32gcc'
gm_platform_timer = 'dependencies/gmscriptex/gmsrc_ex/src/platform/win32gcc/gmPlatformTimer.cpp'
if host_machine.system() == 'windows'
    gm_platform_include = 'dependencies/gmscriptex/gmsrc_ex/src/platform/win32msvc'
    gm_platform_timer = 'dependencies/gmscriptex/gmsrc_ex/src/platform/win32msvc/gmPlatformTimer.cpp'
elif host_machine.system() == 'darwin'
    gm_platform_include = 'dependencies/gmscriptex/gmsrc_ex/src/platform/osx'
endif

omnibot_includes = include_directories(
    '.',
    'Common',
    'dependencies/iprof',
    'dependencies/wildmagic',
    'dependencies/gmscriptex/gmsrc_ex/src/3rdParty',
    'dependencies/gmscriptex/gmsrc_ex/src/gm',
    'dependencies/gmscriptex/gmsrc_ex/src/binds',
    'dependencies/gmscriptex/gmsrc_ex/src/3rdParty/gmbinder2',
    gm_platform_include,
    'dependencies/physfs',
    'dependencies/physfs/lzma/C',
    'dependencies/physfs/lzma/C/Archive/7z',
    'dependencies/physfs/lzma/C/Compress/Lzma',
    'dependencies/physfs/lzma/C/Compress/Branch',
    'dependencies/physfs/zlib123',
)

if host_machine.system() == 'darwin'
    macos_stubs = meson.project_source_root() / 'meson' / 'macos-sdk'
    # Zig ships macOS libc stubs but not the legacy frameworks used by release modules.
    add_project_link_arguments(
        '-F' + macos_stubs,
        '-L' + (macos_stubs / 'usr' / 'lib'),
        '-Wl,-needed_framework,ApplicationServices',
        '-Wl,-needed_framework,Carbon',
        '-Wl,-needed_framework,CoreFoundation',
        '-Wl,-needed_framework,CoreServices',
        '-Wl,-needed_framework,IOKit',
        '-Wl,-needed_library,omnibot-libcxx',
        language: ['c', 'cpp'],
    )
endif

# Keep this list aligned with Common/Jamfile; BatchBuild.cpp supplies Omni-bot's unity sources.
common_sources = files(
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmByteCode.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmByteCodeGen.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmCodeGen.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmCodeTree.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmCrc.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmDebug.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmDebugger.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmFunctionObject.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmIncGC.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmLibHooks.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmLog.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmMachine.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmMachineLib.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmMemChain.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmMemFixedSet.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmOperators.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmParser.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmScanner.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmStreamBuffer.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmStringObject.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmTableObject.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmThread.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmUserObject.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmUtil.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/gm/gmVariable.cpp',
    gm_platform_timer,
    'dependencies/gmscriptex/gmsrc_ex/src/binds/gmArrayLib.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/binds/gmCall.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/binds/gmEntity.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/binds/gmGCRoot.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/binds/gmGCRootUtil.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/binds/gmHelpers.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/binds/gmMathLib.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/binds/gmSchemaLib.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/binds/gmStringLib.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/binds/gmVec3Stack.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/binds/gmVector3Lib.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/3rdParty/mathlib/matrix.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/3rdParty/mathlib/quat.cpp',
    'dependencies/gmscriptex/gmsrc_ex/src/3rdParty/mathlib/vector.cpp',
    'dependencies/wildmagic/Wm3ContBox3.cpp',
    'dependencies/wildmagic/Wm3DistSegment3Segment3.cpp',
    'dependencies/wildmagic/Wm3DistVector3Ray3.cpp',
    'dependencies/wildmagic/Wm3DistVector3Segment3.cpp',
    'dependencies/wildmagic/Wm3Distance.cpp',
    'dependencies/wildmagic/Wm3Intersector.cpp',
    'dependencies/wildmagic/Wm3IntrBox3Box3.cpp',
    'dependencies/wildmagic/Wm3IntrLine3Box3.cpp',
    'dependencies/wildmagic/Wm3IntrLine3Plane3.cpp',
    'dependencies/wildmagic/Wm3IntrSegment3Box3.cpp',
    'dependencies/wildmagic/Wm3IntrSegment3Plane3.cpp',
    'dependencies/wildmagic/Wm3Math.cpp',
    'dependencies/wildmagic/Wm3Matrix3.cpp',
    'dependencies/wildmagic/Wm3Quaternion.cpp',
    'dependencies/wildmagic/Wm3Vector2.cpp',
    'dependencies/wildmagic/Wm3Vector3.cpp',
    'dependencies/physfs/physfs.c',
    'dependencies/physfs/physfs_byteorder.c',
    'dependencies/physfs/physfs_unicode.c',
    'dependencies/physfs/archivers/dir.c',
    'dependencies/physfs/archivers/grp.c',
    'dependencies/physfs/archivers/hog.c',
    'dependencies/physfs/archivers/lzma.c',
    'dependencies/physfs/archivers/mvl.c',
    'dependencies/physfs/archivers/qpak.c',
    'dependencies/physfs/archivers/wad.c',
    'dependencies/physfs/archivers/zip.c',
    'dependencies/physfs/lzma/C/7zCrc.c',
    'dependencies/physfs/lzma/C/7zCrcT8.c',
    'dependencies/physfs/lzma/C/Alloc.c',
    'dependencies/physfs/lzma/C/Sort.c',
    'dependencies/physfs/lzma/C/Threads.c',
    'dependencies/physfs/lzma/C/Archive/7z/7zAlloc.c',
    'dependencies/physfs/lzma/C/Archive/7z/7zBuffer.c',
    'dependencies/physfs/lzma/C/Archive/7z/7zDecode.c',
    'dependencies/physfs/lzma/C/Archive/7z/7zExtract.c',
    'dependencies/physfs/lzma/C/Archive/7z/7zHeader.c',
    'dependencies/physfs/lzma/C/Archive/7z/7zIn.c',
    'dependencies/physfs/lzma/C/Archive/7z/7zItem.c',
    'dependencies/physfs/lzma/C/Archive/7z/7zMain.c',
    'dependencies/physfs/lzma/C/Archive/7z/7zMethodID.c',
    'dependencies/physfs/lzma/C/Compress/Lzma/LzmaDecode.c',
    'dependencies/physfs/lzma/C/Compress/Lzma/LzmaStateDecode.c',
    'dependencies/physfs/lzma/C/Compress/Lzma/LzmaStateTest.c',
    'dependencies/physfs/lzma/C/Compress/Lzma/LzmaTest.c',
    'dependencies/physfs/lzma/C/Compress/Branch/BranchARM.c',
    'dependencies/physfs/lzma/C/Compress/Branch/BranchARMThumb.c',
    'dependencies/physfs/lzma/C/Compress/Branch/BranchIA64.c',
    'dependencies/physfs/lzma/C/Compress/Branch/BranchPPC.c',
    'dependencies/physfs/lzma/C/Compress/Branch/BranchSPARC.c',
    'dependencies/physfs/lzma/C/Compress/Branch/BranchX86.c',
    'dependencies/physfs/lzma/C/Compress/Branch/BranchX86_2.c',
    'dependencies/physfs/zlib123/adler32.c',
    'dependencies/physfs/zlib123/compress.c',
    'dependencies/physfs/zlib123/crc32.c',
    'dependencies/physfs/zlib123/deflate.c',
    'dependencies/physfs/zlib123/gzio.c',
    'dependencies/physfs/zlib123/infback.c',
    'dependencies/physfs/zlib123/inffast.c',
    'dependencies/physfs/zlib123/inflate.c',
    'dependencies/physfs/zlib123/inftrees.c',
    'dependencies/physfs/zlib123/trees.c',
    'dependencies/physfs/zlib123/uncompr.c',
    'dependencies/physfs/zlib123/zutil.c',
    'dependencies/physfs/platform/macosx.c',
    'dependencies/physfs/platform/os2.c',
    'dependencies/physfs/platform/pocketpc.c',
    'dependencies/physfs/platform/posix.c',
    'dependencies/physfs/platform/unix.c',
    'dependencies/physfs/platform/windows.c',
    'Common/FileSearch.cpp',
    'Common/RegexMatch.cpp',
    'Common/BatchBuild.cpp',
)

common_library = static_library(
    'omnibot-common',
    common_sources,
    include_directories: omnibot_includes,
    dependencies: boost_regex_dependency,
    c_args: [
        '-DPHYSFS_SUPPORTS_ZIP=1',
        '-DPHYSFS_SUPPORTS_7Z=1',
        '-DPHYSFS_NO_CDROM_SUPPORT=1',
    ] + physfs_c_arguments,
    cpp_args: [
        '-DPHYSFS_SUPPORTS_ZIP=1',
        '-DPHYSFS_SUPPORTS_7Z=1',
        '-DPHYSFS_NO_CDROM_SUPPORT=1',
    ],
    pic: true,
)

common_dependency = declare_dependency(
    include_directories: omnibot_includes,
    link_with: common_library,
    dependencies: boost_regex_dependency,
)

# The empty prefix and default platform suffix reproduce b2's module names on 32-bit Linux.
et_sources = files('ET/ET_BatchBuild.cpp')
if host_machine.system() == 'windows'
    # Keep advapi32 in the module's import table, matching existing releases.
    et_sources += files('meson/windows_dependency_anchor.c')
endif

shared_module(
    'omnibot_et',
    et_sources,
    name_prefix: '',
    dependencies: common_dependency,
    install: false,
)

shared_module(
    'omnibot_rtcw',
    'RTCW/RTCW_BatchBuild.cpp',
    name_prefix: '',
    dependencies: common_dependency,
    install: false,
)

if get_option('tests')
    subdir('tests')
endif
