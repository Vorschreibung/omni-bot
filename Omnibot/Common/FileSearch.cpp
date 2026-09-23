#include "common.h"

namespace Utils
{
	fs::path FindFileInSearchPath(const fs::path &_file, const fs::path &_searchPath)
	{
		// Preserve FindFile's historical preference for a bare filename in each PATH entry.
		fs::path checkPath = _searchPath / _file.filename();
		if(fs::exists(checkPath) && !fs::is_directory(checkPath))
			return checkPath;

		if(_file.string() != _file.filename())
		{
			checkPath = _searchPath / _file;
			if(fs::exists(checkPath) && !fs::is_directory(checkPath))
				return checkPath;
		}

		return fs::path();
	}
}
