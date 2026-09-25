cmake_minimum_required(VERSION 3.24)
cmake_policy(SET CMP0091 NEW)

project(Omnibot VERSION 0.93 LANGUAGES C CXX)

# Zig 0.16 can corrupt its shared runtime cache when Windows starts multiple
# cross-link processes concurrently. Keep compilation parallel but serialize
# link commands that use this toolchain on Windows hosts.
if (CMAKE_HOST_WIN32 AND OMNIBOT_ZIG_TARGET)
    set_property(GLOBAL PROPERTY JOB_POOLS omnibot_zig_link=1)
    set(CMAKE_JOB_POOL_LINK omnibot_zig_link)
endif ()

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

macro(add_cxx_flag flag)
    message(STATUS "Configure with flag '${flag}'")
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} ${flag}")
endmacro()

set(CMAKE_POSITION_INDEPENDENT_CODE ON)

if (OMNIBOT_ZIG_TARGET)
    # Zig's bundled libc++ emits nullability completeness diagnostics on
    # Windows and macOS that do not identify issues in Omni-bot itself.
    add_compile_options("$<$<COMPILE_LANGUAGE:CXX>:-Wno-nullability-completeness>")
endif ()

if (WIN32)
    # The legacy sources test WIN32 and require lean Windows headers to avoid
    # collisions such as the PlaySound macro with bot API function names.
    add_compile_definitions(WIN32 WIN32_LEAN_AND_MEAN NOMINMAX)
endif ()

# MSVC static runtime linkage
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

option(OMNIBOT_ET "Build the Enemy Territory bots module" ON)
option(OMNIBOT_RTCW "Build the Return to Castle Wolfenstein bots module" ON)

string(TOLOWER "${CMAKE_SYSTEM_PROCESSOR}" SYSTEM_PROCESSOR_LOWER)
set(OMNIBOT_TARGET_ARCH "")
if (SYSTEM_PROCESSOR_LOWER MATCHES "^(amd64|x86_64)$")
    set(OMNIBOT_TARGET_ARCH "x86_64")
elseif (SYSTEM_PROCESSOR_LOWER MATCHES "^(x86|i[3-6]86)$")
    set(OMNIBOT_TARGET_ARCH "x86")
elseif (SYSTEM_PROCESSOR_LOWER MATCHES "^(aarch64|arm64)$")
    set(OMNIBOT_TARGET_ARCH "aarch64")
endif ()

set(MODULE_SUFFIX "")
if (APPLE)
    string(APPEND MODULE_SUFFIX "_mac")
elseif (WIN32)
    if (OMNIBOT_TARGET_ARCH STREQUAL "x86_64" OR CMAKE_SIZEOF_VOID_P EQUAL 8)
        string(APPEND MODULE_SUFFIX "_x64")
    endif ()
elseif (UNIX)
    if (OMNIBOT_TARGET_ARCH STREQUAL "x86_64")
        string(APPEND MODULE_SUFFIX ".x86_64")
    elseif (OMNIBOT_TARGET_ARCH STREQUAL "aarch64")
        string(APPEND MODULE_SUFFIX ".aarch64")
    endif ()
endif ()

set(DEPENDENCIES_PATH "${CMAKE_SOURCE_DIR}/dependencies")

add_library(omni-shared INTERFACE)

# Fetch one reproducible Boost source tree and build only the libraries used by
# Omni-bot. Header-only dependencies are discovered by Boost's CMake project.
include(FetchContent)
set(BUILD_SHARED_LIBS OFF)
set(
    BOOST_INCLUDE_LIBRARIES
    algorithm
    array
    bind
    date_time
    dynamic_bitset
    filesystem
    interprocess
    lexical_cast
    multi_array
    pool
    regex
    smart_ptr
    static_assert
    system
)
set(BOOST_RUNTIME_LINK static)
set(BOOST_SKIP_INSTALL_RULES ON)
if (CMAKE_SYSTEM_NAME STREQUAL "Linux")
    # Both release glibc baselines predate the getrandom wrapper.
    set(BOOST_FILESYSTEM_DISABLE_GETRANDOM ON CACHE BOOL "" FORCE)
endif ()
FetchContent_Declare(
    Boost
    URL https://github.com/boostorg/boost/releases/download/boost-1.92.0/boost-1.92.0-cmake.tar.gz
    URL_HASH SHA256=f51707c27359a0df0cac1beada86de31bb5eed5e8285592dadec384df99c2984
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)
FetchContent_MakeAvailable(Boost)
target_link_libraries(
    omni-shared
    INTERFACE
        Boost::headers
        Boost::algorithm
        Boost::array
        Boost::bind
        Boost::filesystem
        Boost::dynamic_bitset
        Boost::interprocess
        Boost::lexical_cast
        Boost::multi_array
        Boost::pool
        Boost::regex
        Boost::smart_ptr
        Boost::static_assert
        Boost::date_time
        Boost::system
)
target_compile_definitions(omni-shared INTERFACE BOOST_ALL_NO_LIB)

target_include_directories(omni-shared INTERFACE "${DEPENDENCIES_PATH}/WildMagic5/SDK/include")

if (NOT WIN32)
    add_compile_options(-Wall -Wno-deprecated -fno-strict-aliasing)
endif ()
# Omni-bot intentionally embeds its build timestamp in IGame::GetVersion().
add_compile_options("$<$<COMPILE_LANGUAGE:CXX>:-Wno-date-time>")
add_compile_options("$<$<CONFIG:DEBUG>:-D_DEBUG>")
if (CMAKE_SYSTEM_NAME STREQUAL "Linux")
    # Keep compiler and Zig runtime debug data out of release modules.
    add_compile_options("$<$<CONFIG:Release>:-g0>")
    add_link_options("$<$<CONFIG:Release>:-Wl,--strip-debug>")
endif ()

add_subdirectory(Common)

if (OMNIBOT_ET)
    add_subdirectory(ET)
    # Set ET as the startup project in Visual Studio
    set_property(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR} PROPERTY VS_STARTUP_PROJECT omnibot-et)
endif ()

if (OMNIBOT_RTCW)
    add_subdirectory(RTCW)
    if (NOT OMNIBOT_ET)
        set_property(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR} PROPERTY VS_STARTUP_PROJECT omnibot-rtcw)
    endif ()
endif ()
