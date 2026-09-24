cmake_minimum_required(VERSION 3.24)
cmake_policy(SET CMP0091 NEW)

project(Omnibot VERSION 0.93 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

macro(add_cxx_flag flag)
    message(STATUS "Configure with flag '${flag}'")
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} ${flag}")
endmacro()

set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# MSVC static runtime linkage
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

option(OMNIBOT_ET "Build the Enemy Territory bots module" ON)
option(OMNIBOT_RTCW "Build the Return to Castle Wolfenstein bots module" ON)

string(TOLOWER "${CMAKE_SYSTEM_PROCESSOR}" SYSTEM_PROCESSOR_LOWER)
if (APPLE)
    string(APPEND MODULE_SUFFIX "_mac")
elseif (SYSTEM_PROCESSOR_LOWER MATCHES "(x86)|(amd64)")
    if(CMAKE_SIZEOF_VOID_P EQUAL 8)
        if (WIN32)
            string(APPEND MODULE_SUFFIX "_x64")
        else ()
            string(APPEND MODULE_SUFFIX ".x86_64")
        endif ()
    endif ()
elseif (SYSTEM_PROCESSOR_LOWER STREQUAL "aarch64")
    string(APPEND MODULE_SUFFIX ".aarch64")
endif ()

set(DEPENDENCIES_PATH "${CMAKE_SOURCE_DIR}/dependencies")

add_library(omni-shared INTERFACE)

# Fetch one reproducible Boost source tree and build only the libraries used by
# Omni-bot. Header-only dependencies are discovered by Boost's CMake project.
include(FetchContent)
set(BUILD_SHARED_LIBS OFF)
set(BOOST_INCLUDE_LIBRARIES filesystem regex date_time system)
set(BOOST_RUNTIME_LINK static)
set(BOOST_SKIP_INSTALL_RULES ON)
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
        Boost::filesystem
        Boost::regex
        Boost::date_time
        Boost::system
)
target_compile_definitions(omni-shared INTERFACE BOOST_ALL_NO_LIB)

target_include_directories(omni-shared INTERFACE "${DEPENDENCIES_PATH}/WildMagic5/SDK/include")

if (NOT WIN32)
    add_compile_options(-Wall -Wno-deprecated -fno-strict-aliasing)
endif ()
add_compile_options("$<$<CONFIG:DEBUG>:-D_DEBUG>")

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
