# CMake loads this file after its compiler and platform rules for each language.
foreach(language C CXX)
    # Replace mode creates a missing archive consistently across Zig host builds.
    set(CMAKE_${language}_ARCHIVE_CREATE "<CMAKE_AR> ar rcs <TARGET> <LINK_FLAGS> <OBJECTS>")
    set(CMAKE_${language}_ARCHIVE_APPEND "<CMAKE_AR> ar r <TARGET> <LINK_FLAGS> <OBJECTS>")
    set(CMAKE_${language}_ARCHIVE_FINISH "<CMAKE_RANLIB> ranlib <TARGET>")
endforeach()
