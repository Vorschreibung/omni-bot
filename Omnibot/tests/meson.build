filesystem_test = executable(
    'filesystem_test',
    'filesystem_test.cpp',
    '../Common/FileSearch.cpp',
    include_directories: omnibot_includes,
    dependencies: boost_headers_dependency,
)

regex_test = executable(
    'regex_test',
    'regex_test.cpp',
    '../Common/RegexMatch.cpp',
    include_directories: omnibot_includes,
    dependencies: [boost_headers_dependency, boost_regex_dependency],
)

test('filesystem behavior', filesystem_test)
test('regex behavior', regex_test)
