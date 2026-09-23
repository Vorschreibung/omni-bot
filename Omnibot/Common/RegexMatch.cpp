#include "common.h"

namespace Utils
{
	// Keep the inexpensive literal prefix check before invoking the regex engine.
	bool RegexMatch(const char *_expression, const char *_value)
	{
		const char *expression = _expression;
		const char *value = _value;
		for(;; expression++, value++)
		{
			char expressionCharacter = *expression;
			char valueCharacter = *value;
			if(!expressionCharacter)
				return !valueCharacter;
			if(expressionCharacter == valueCharacter)
				continue;
			if(expressionCharacter >= 'A' && expressionCharacter <= 'Z')
			{
				if(expressionCharacter + ('a' - 'A') == valueCharacter)
					continue;
			}
			else if(expressionCharacter >= 'a' && expressionCharacter <= 'z')
			{
				if(expressionCharacter - ('a' - 'A') == valueCharacter)
					continue;
			}
			else if(expressionCharacter != '_' &&
				!(expressionCharacter >= '0' && expressionCharacter <= '9'))
			{
				if(expressionCharacter == '*' ||
					(expressionCharacter == '\\' && expression[1] == '{'))
				{
					expression--;
					value--;
				}
				break;
			}

			char nextCharacter = expression[1];
			if(nextCharacter != '*' && nextCharacter != '\\')
				return false;
			break;
		}

		if(expression[0] == '.' && expression[1] == '*' && expression[2] == '\0')
			return true;

		try
		{
			boost::regex compiledExpression(expression, REGEX_OPTIONS);
			return boost::regex_match(value, compiledExpression);
		}
		catch(const std::exception &exception)
		{
			_UNUSED(exception);
			OBASSERT(0, exception.what());
		}
		return false;
	}
}
