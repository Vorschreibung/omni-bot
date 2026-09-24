#include <windows.h>

/* Preserve the Advapi32 dependency carried by the established Windows modules. */
__declspec(dllexport) LONG omnibot_windows_dependency_anchor(void)
{
    return RegCloseKey(NULL);
}
