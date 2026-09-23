#include "common.h"

#include <cstdio>
#include <cstdlib>
#include <fstream>

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
			: m_Path(fs::temp_directory_path() / fs::unique_path("omnibot-%%%%-%%%%"))
		{
			fs::create_directories(m_Path / "nested");
		}

		~TemporaryDirectory()
		{
			// Cleanup must not hide a test result if the filesystem refuses removal.
			boost::system::error_code ignoredError;
			fs::remove_all(m_Path, ignoredError);
		}

		const fs::path &Path() const
		{
			return m_Path;
		}

	private:
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
