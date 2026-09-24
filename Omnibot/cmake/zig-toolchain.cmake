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

# CMake archive rules require a single executable, so small wrappers expose
# Zig's multicall archive tools using the conventional command-line shape.
set(CMAKE_AR "${CMAKE_CURRENT_LIST_DIR}/zig-ar")
set(CMAKE_RANLIB "${CMAKE_CURRENT_LIST_DIR}/zig-ranlib")
set(CMAKE_STRIP "${CMAKE_CURRENT_LIST_DIR}/zig-strip")

# Cross-compiled configure probes can be compiled but not run on the host.
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)
