# Configure CMake to drive Zig's Clang frontend for a caller-selected target.
foreach(variable OMNIBOT_ZIG_SYSTEM_NAME OMNIBOT_ZIG_PROCESSOR OMNIBOT_ZIG_TARGET)
    if (NOT DEFINED ${variable})
        message(FATAL_ERROR "${variable} must be set before loading the Zig toolchain")
    endif ()
endforeach()

# Compiler ABI probes create nested CMake projects that reload this toolchain.
list(
    APPEND
    CMAKE_TRY_COMPILE_PLATFORM_VARIABLES
    OMNIBOT_ZIG_SYSTEM_NAME
    OMNIBOT_ZIG_PROCESSOR
    OMNIBOT_ZIG_TARGET
)

set(CMAKE_SYSTEM_NAME "${OMNIBOT_ZIG_SYSTEM_NAME}")
set(CMAKE_SYSTEM_PROCESSOR "${OMNIBOT_ZIG_PROCESSOR}")

set(CMAKE_C_COMPILER zig)
set(CMAKE_C_COMPILER_ARG1 cc)
set(CMAKE_C_COMPILER_TARGET "${OMNIBOT_ZIG_TARGET}")

set(CMAKE_CXX_COMPILER zig)
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
set(CMAKE_AR zig)
set(CMAKE_RANLIB zig)
foreach(language C CXX)
    set(CMAKE_${language}_ARCHIVE_CREATE "<CMAKE_AR> ar qc <TARGET> <LINK_FLAGS> <OBJECTS>")
    set(CMAKE_${language}_ARCHIVE_APPEND "<CMAKE_AR> ar q <TARGET> <LINK_FLAGS> <OBJECTS>")
    set(CMAKE_${language}_ARCHIVE_FINISH "<CMAKE_RANLIB> ranlib <TARGET>")
endforeach()

# Cross-compiled configure probes can be compiled but not run on the host.
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)
