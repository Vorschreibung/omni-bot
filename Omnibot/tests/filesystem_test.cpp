#include "common.h"

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <stdexcept>

namespace
{
	bool Require(bool _condition, const char *_message)
	{
		if(!_condition)
		{
			std::fprintf(stderr, "%s\n", _message);
			return false;
		}
		return true;
	}

	class TemporaryDirectory
	{
	public:
		TemporaryDirectory()
			: m_Path(CreatePath())
		{
			std::error_code error;
			if(!fs::create_directories(m_Path / "nested", error) || error)
				throw std::runtime_error("failed to create temporary test directory");
		}

		~TemporaryDirectory()
		{
			// Cleanup must not hide a test result if the filesystem refuses removal.
			std::error_code ignoredError;
			fs::remove_all(m_Path, ignoredError);
		}

		const fs::path &Path() const
		{
			return m_Path;
		}

	private:
		static fs::path CreatePath()
		{
			// The timestamp replaces Boost.Filesystem's non-standard unique_path helper.
			const long long timestamp = std::chrono::steady_clock::now()
				.time_since_epoch()
				.count();
			return fs::temp_directory_path() / ("omnibot-" + std::to_string(timestamp));
		}

		fs::path m_Path;
	};

	void WriteFile(const fs::path &_path, const char *_contents)
	{
		std::ofstream stream(_path.string().c_str());
		stream << _contents;
	}
}

int main()
{
	TemporaryDirectory temporaryDirectory;
	const fs::path searchPath = temporaryDirectory.Path();
	const fs::path requestedPath = fs::path("nested") / "target.txt";
	const fs::path bareCandidate = searchPath / "target.txt";
	const fs::path nestedCandidate = searchPath / requestedPath;

	WriteFile(bareCandidate, "bare");
	WriteFile(nestedCandidate, "nested");
	if(!Require(fs::file_size(bareCandidate) == 4, "failed to create filesystem test input"))
		return EXIT_FAILURE;
	if(!Require(
		Utils::FindFileInSearchPath(requestedPath, searchPath) == bareCandidate,
		"bare filename must take precedence over the supplied subpath"))
		return EXIT_FAILURE;

	fs::remove(bareCandidate);
	if(!Require(
		Utils::FindFileInSearchPath(requestedPath, searchPath) == nestedCandidate,
		"supplied subpath must be searched after the bare filename"))
		return EXIT_FAILURE;

	fs::remove(nestedCandidate);
	fs::create_directory(nestedCandidate);
	if(!Require(
		Utils::FindFileInSearchPath(requestedPath, searchPath).empty(),
		"directory candidates must not be returned as files"))
		return EXIT_FAILURE;
	if(!Require(
		Utils::FindFileInSearchPath("missing.txt", searchPath).empty(),
		"a missing file must produce an empty path"))
		return EXIT_FAILURE;
	return EXIT_SUCCESS;
}
