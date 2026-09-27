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
    OMNIBOT_ZIG_EXECUTABLE
    OMNIBOT_ZIG_SYSTEM_NAME
    OMNIBOT_ZIG_PROCESSOR
    OMNIBOT_ZIG_TARGET
)

set(CMAKE_SYSTEM_NAME "${OMNIBOT_ZIG_SYSTEM_NAME}")
set(CMAKE_SYSTEM_PROCESSOR "${OMNIBOT_ZIG_PROCESSOR}")

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
