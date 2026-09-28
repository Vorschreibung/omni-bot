# Configure CMake to drive Zig's Clang frontend for a caller-selected target.
foreach(variable OMNIBOT_ZIG_SYSTEM_NAME OMNIBOT_ZIG_PROCESSOR OMNIBOT_ZIG_TARGET)
    if (NOT DEFINED ${variable})
        message(FATAL_ERROR "${variable} must be set before loading the Zig toolchain")
    endif ()
endforeach()

# Conda-forge exposes Zig under a target-prefixed name on Windows and records
# its full path in ZIG, while Unix installations also commonly provide `zig`.
if (NOT OMNIBOT_ZIG_EXECUTABLE)
    if (DEFINED ENV{ZIG} AND EXISTS "$ENV{ZIG}")
        set(OMNIBOT_ZIG_EXECUTABLE "$ENV{ZIG}")
    else ()
        find_program(OMNIBOT_ZIG_EXECUTABLE NAMES zig REQUIRED)
    endif ()
endif ()

# Compiler ABI probes create nested CMake projects that reload this toolchain.
list(
    APPEND
    CMAKE_TRY_COMPILE_PLATFORM_VARIABLES
    OMNIBOT_MACOS_SYSROOT
    OMNIBOT_ZIG_LIBSYSTEM
    OMNIBOT_ZIG_EXECUTABLE
    OMNIBOT_ZIG_SYSTEM_NAME
    OMNIBOT_ZIG_PROCESSOR
    OMNIBOT_ZIG_TARGET
)

set(CMAKE_SYSTEM_NAME "${OMNIBOT_ZIG_SYSTEM_NAME}")
set(CMAKE_SYSTEM_PROCESSOR "${OMNIBOT_ZIG_PROCESSOR}")

if (CMAKE_SYSTEM_NAME STREQUAL "Darwin")
    set(OMNIBOT_MACOS_SDK "${CMAKE_CURRENT_LIST_DIR}/macos-sdk")
    if (NOT EXISTS "${OMNIBOT_MACOS_SDK}/usr/lib/libomnibot-libcxx.tbd")
        message(FATAL_ERROR "The reduced macOS SDK is missing its libc++ stub")
    endif ()

    if (OMNIBOT_ZIG_LIBSYSTEM AND NOT EXISTS "${OMNIBOT_ZIG_LIBSYSTEM}")
        unset(OMNIBOT_ZIG_LIBSYSTEM CACHE)
    endif ()
    if (NOT OMNIBOT_ZIG_LIBSYSTEM)
        set(OMNIBOT_ZIG_LIBRARY_PATHS "")
        if (DEFINED ENV{ZIG_LIB_DIR} AND NOT "$ENV{ZIG_LIB_DIR}" STREQUAL "")
            list(APPEND OMNIBOT_ZIG_LIBRARY_PATHS "$ENV{ZIG_LIB_DIR}/libc/darwin")
        endif ()
        if (DEFINED ENV{CONDA_PREFIX} AND NOT "$ENV{CONDA_PREFIX}" STREQUAL "")
            list(
                APPEND
                OMNIBOT_ZIG_LIBRARY_PATHS
                "$ENV{CONDA_PREFIX}/lib/zig/libc/darwin"
                "$ENV{CONDA_PREFIX}/Library/lib/zig/libc/darwin"
            )
        endif ()
        find_file(
            OMNIBOT_ZIG_LIBSYSTEM
            NAMES libSystem.tbd
            PATHS ${OMNIBOT_ZIG_LIBRARY_PATHS}
            NO_DEFAULT_PATH
            REQUIRED
        )
    endif ()

    if (NOT OMNIBOT_MACOS_SYSROOT)
        set(
            OMNIBOT_MACOS_SYSROOT
            "${CMAKE_BINARY_DIR}/macos-sdk"
            CACHE PATH
            "Build-local macOS SDK overlay"
        )
    endif ()

    # Zig's Darwin linker needs a real sysroot so absolute text-stub reexports
    # never resolve against libraries from the host operating system.
    file(COPY "${OMNIBOT_MACOS_SDK}/" DESTINATION "${OMNIBOT_MACOS_SYSROOT}")
    file(MAKE_DIRECTORY "${OMNIBOT_MACOS_SYSROOT}/usr/lib")
    file(
        COPY_FILE
        "${OMNIBOT_ZIG_LIBSYSTEM}"
        "${OMNIBOT_MACOS_SYSROOT}/usr/lib/libSystem.tbd"
        ONLY_IF_DIFFERENT
    )
    set(CMAKE_OSX_SYSROOT "${OMNIBOT_MACOS_SYSROOT}" CACHE PATH "" FORCE)
endif ()

set(CMAKE_C_COMPILER "${OMNIBOT_ZIG_EXECUTABLE}")
set(CMAKE_C_COMPILER_ARG1 cc)
set(CMAKE_C_COMPILER_TARGET "${OMNIBOT_ZIG_TARGET}")

set(CMAKE_CXX_COMPILER "${OMNIBOT_ZIG_EXECUTABLE}")
set(CMAKE_CXX_COMPILER_ARG1 c++)
set(CMAKE_CXX_COMPILER_TARGET "${OMNIBOT_ZIG_TARGET}")
# Zig selects its bundled libc++ automatically for MinGW targets.
if (NOT CMAKE_SYSTEM_NAME STREQUAL "Windows")
    set(CMAKE_CXX_FLAGS_INIT "-stdlib=libc++")
endif ()

if (CMAKE_SYSTEM_NAME STREQUAL "Darwin")
    # The source compatibility switch selects PhysicsFS's portable Unix backend.
    add_compile_definitions(PHYSFS_FORCE_UNIX)
endif ()

# Call Zig's archive subcommands from CMake's command templates so the same
# toolchain works on hosts that cannot execute the POSIX wrapper scripts.
set(CMAKE_AR "${OMNIBOT_ZIG_EXECUTABLE}")
set(CMAKE_RANLIB "${OMNIBOT_ZIG_EXECUTABLE}")

# Windows-GNU replaces archive commands while initializing each language, so
# apply the Zig-specific forms through CMake's post-platform override hook.
set(CMAKE_USER_MAKE_RULES_OVERRIDE "${CMAKE_CURRENT_LIST_DIR}/zig-toolchain-rules.cmake")

# Cross-compiled configure probes can be compiled but not run on the host.
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)
