// node test: CPython + Anki's Rust core in one wasm
#include <Python.h>
PyObject *PyInit__rsbridge(void);
int main(int argc, char **argv) {
    PyImport_AppendInittab("anki._rsbridge", PyInit__rsbridge);
    PyConfig c; PyConfig_InitIsolatedConfig(&c);
    PyConfig_SetString(&c, &c.home, L"/python");
    c.module_search_paths_set = 1;
    PyWideStringList_Append(&c.module_search_paths, L"/app");
    PyWideStringList_Append(&c.module_search_paths, L"/site");
    PyWideStringList_Append(&c.module_search_paths, L"/python/lib/python" KIOKU_PYTHON_VERSION);  // link_core.sh
    PyConfig_SetBytesArgv(&c, argc, argv);
    c.parse_argv = 1;
    PyStatus s = Py_InitializeFromConfig(&c);
    if (PyStatus_Exception(s)) Py_ExitStatusException(s);
    return Py_RunMain();
}
