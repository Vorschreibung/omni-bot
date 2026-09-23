#include "common.h"

#include <cstdio>
#include <cstdlib>

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
}

int main()
{
	if(!Require(Utils::RegexMatch("Engineer", "engineer"), "literal matching must ignore case"))
		return EXIT_FAILURE;
	if(!Require(Utils::RegexMatch("bot_.*", "BOT_engineer"), "wildcard matching must ignore case"))
		return EXIT_FAILURE;
	if(!Require(!Utils::RegexMatch("bot_.*", "prefix_bot_engineer"), "matching must cover the full value"))
		return EXIT_FAILURE;
	if(!Require(Utils::RegexMatch("slot_[0-9]\\{2\\}", "SLOT_42"), "basic-regex repetition must remain supported"))
		return EXIT_FAILURE;
	if(!Require(!Utils::RegexMatch("slot_[0-9]\\{2\\}", "SLOT_7"), "basic-regex repetition must reject short values"))
		return EXIT_FAILURE;
	return EXIT_SUCCESS;
}
