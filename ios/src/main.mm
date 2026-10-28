// Kioku for iOS: starts an embedded CPython that runs the unmodified Anki
// desktop app (aqt). PyQt6, sip and the Rust extension modules are linked
// statically into this binary and registered as built-in modules; the
// standard library comes from the BeeWare Python.framework.

#import <Foundation/Foundation.h>
#import <JavaScriptCore/JavaScriptCore.h>
#include <Python.h>
#include <pthread.h>
#include <sys/resource.h>

extern "C" {
PyObject *PyInit_sip(void);
PyObject *PyInit_QtCore(void);
PyObject *PyInit_QtGui(void);
PyObject *PyInit_QtWidgets(void);
PyObject *PyInit_QtNetwork(void);
PyObject *PyInit_QtSvg(void);
PyObject *PyInit__rsbridge(void);
PyObject *PyInit_orjson(void);
PyObject *PyInit_rpds(void);
}

static void fail(const char *what, PyStatus status) {
    NSLog(@"Kioku: %s failed: %s", what, status.err_msg ? status.err_msg : "?");
    exit(1);
}

static void append_path(PyConfig *config, NSString *path) {
    wchar_t *w = Py_DecodeLocale(path.UTF8String, NULL);
    PyStatus status = PyWideStringList_Append(&config->module_search_paths, w);
    PyMem_RawFree(w);
    if (PyStatus_Exception(status)) fail("module path", status);
}

// Qt runs main() on a 512 KB stack reserved inside the main thread's stack
// and lowers RLIMIT_STACK to that size meanwhile; QApplication::exec() then
// jumps back to UIApplicationMain's frames, below that block. WebKit takes
// the main thread's stack bounds from RLIMIT_STACK once, when it first sees
// the thread (our first WKWebView, inside main()), so later it found the
// stack pointer outside them and stopped the app (JSC::sanitizeStackForVM)
// on iOS 18 (iOS 27 refuses Qt's lower limit). Raising the limit again
// doesn't help there, so let WebKit see the thread before Qt starts, while
// the limit still covers the whole stack.
static rlim_t stack_limit_at_start;

__attribute__((constructor)) static void set_webkit_stack_bounds(void) {
    struct rlimit limit;
    if (getrlimit(RLIMIT_STACK, &limit) == 0)
        stack_limit_at_start = limit.rlim_cur;
    @autoreleasepool {
        [[[JSVirtualMachine alloc] init] release];
    }
}

int main(int argc, char *argv[]) {
    @autoreleasepool {
        struct rlimit limit;
        if (getrlimit(RLIMIT_STACK, &limit) == 0 && limit.rlim_cur != stack_limit_at_start)
            NSLog(@"Kioku: RLIMIT_STACK %llu at start, %llu in main()",
                  (unsigned long long)stack_limit_at_start, (unsigned long long)limit.rlim_cur);

        NSString *res = [[NSBundle mainBundle] resourcePath];

        PyImport_AppendInittab("PyQt6.sip", PyInit_sip);
        PyImport_AppendInittab("PyQt6.QtCore", PyInit_QtCore);
        PyImport_AppendInittab("PyQt6.QtGui", PyInit_QtGui);
        PyImport_AppendInittab("PyQt6.QtWidgets", PyInit_QtWidgets);
        PyImport_AppendInittab("PyQt6.QtNetwork", PyInit_QtNetwork);
        PyImport_AppendInittab("PyQt6.QtSvg", PyInit_QtSvg);
        PyImport_AppendInittab("anki._rsbridge", PyInit__rsbridge);
        PyImport_AppendInittab("orjson.orjson", PyInit_orjson);
        PyImport_AppendInittab("rpds", PyInit_rpds);

        PyPreConfig preconfig;
        PyPreConfig_InitIsolatedConfig(&preconfig);
        preconfig.utf8_mode = 1;
        PyStatus status = Py_PreInitialize(&preconfig);
        if (PyStatus_Exception(status)) fail("pre-init", status);

        PyConfig config;
        PyConfig_InitIsolatedConfig(&config);
        config.use_system_logger = 1;
        config.buffered_stdio = 0;
        config.write_bytecode = 0;
        config.install_signal_handlers = 1;

        NSString *home = [res stringByAppendingPathComponent:@"python"];
        wchar_t *whome = Py_DecodeLocale(home.UTF8String, NULL);
        status = PyConfig_SetString(&config, &config.home, whome);
        PyMem_RawFree(whome);
        if (PyStatus_Exception(status)) fail("home", status);

        NSString *stdlib = [home stringByAppendingPathComponent:@"lib/python3.14"];
        config.module_search_paths_set = 1;
        append_path(&config, [res stringByAppendingPathComponent:@"app"]);
        append_path(&config, [res stringByAppendingPathComponent:@"app_packages"]);
        append_path(&config, stdlib);
        append_path(&config, [stdlib stringByAppendingPathComponent:@"lib-dynload"]);

        status = PyConfig_SetBytesArgv(&config, argc, argv);
        if (PyStatus_Exception(status)) fail("argv", status);
        status = PyConfig_SetString(&config, &config.run_module, L"kioku");
        if (PyStatus_Exception(status)) fail("run_module", status);

        status = Py_InitializeFromConfig(&config);
        PyConfig_Clear(&config);
        if (PyStatus_Exception(status)) fail("init", status);

        // Python takes the main thread's stack bounds from pthread here, inside
        // Qt's 512 KB block, and then runs below it in exec(). Seeing the stack
        // pointer under its limit, it took every object freed on the main thread
        // for deep recursion and parked it in its trashcan for good: nothing was
        // freed, and add-ons' sqlite3 statements stayed active. Give it the
        // whole stack, as WebKit has above.
        char *stack_top = (char *)pthread_get_stackaddr_np(pthread_self());
        rlim_t stack_size = stack_limit_at_start && stack_limit_at_start != RLIM_INFINITY
            ? stack_limit_at_start : 8 * 1024 * 1024;
        if (PyUnstable_ThreadState_SetStackProtection(PyThreadState_Get(),
                                                      stack_top - stack_size, stack_size) < 0)
            PyErr_Print();
    }
    return Py_RunMain();
}
