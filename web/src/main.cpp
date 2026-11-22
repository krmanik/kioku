// Feasibility probe: CPython with PyQt6 and Anki's Rust core linked in
// statically, like Kioku's iOS app (ios/src/main.mm), running a Python script
// from the preloaded file system.
#include <Python.h>

#include <emscripten.h>
#include <emscripten/threading.h>
#include <emscripten/val.h>

#include <poll.h>
#include <unistd.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>

extern "C" {
PyObject *PyInit_sip(void);
PyObject *PyInit_QtCore(void);
PyObject *PyInit_QtGui(void);
PyObject *PyInit_QtWidgets(void);
PyObject *PyInit_QtNetwork(void);
PyObject *PyInit_QtSvg(void);
PyObject *PyInit__rsbridge(void);
PyObject *PyInit_rpds(void);
PyObject *PyInit_orjson(void);
PyObject *PyInit__speedups(void);
}

// Emscripten's poll() ignores its timeout and returns at once, so a socket
// wait with a timeout (CPython's sockets: ssl handshakes, requests) gave up
// before the relay's data arrived. Linked with --wrap=poll: poll again
// every 2 ms until something is ready or the timeout passes. Worker threads
// sleep; the main thread yields to the browser with emscripten_sleep()
// (Asyncify, as Qt's nested event loops do), since the WebSocket events
// that bring the data only run then: add-ons call the network from the
// GUI thread (AMBOSS logs in from a pycmd handler).
extern "C" int __real_poll(struct pollfd *fds, nfds_t nfds, int timeout);
extern "C" int __wrap_poll(struct pollfd *fds, nfds_t nfds, int timeout) {
    int ready = __real_poll(fds, nfds, 0);
    if (ready != 0 || timeout == 0) return ready;
    bool main = emscripten_is_main_runtime_thread();
    double end = emscripten_get_now() + timeout;
    while (ready == 0 && (timeout < 0 || emscripten_get_now() < end)) {
        if (main)
            emscripten_sleep(2);
        else
            usleep(2000);
        ready = __real_poll(fds, nfds, 0);
    }
    return ready;
}

// _kioku_web: what kioku_platform needs from the page (shell/kioku-web.js)

// Run JavaScript on the page and return the result as a string. Main thread
// only: the page's DOM isn't reachable from the workers behind threads.
static PyObject *web_run_script(PyObject *, PyObject *args) {
    const char *code;
    if (!PyArg_ParseTuple(args, "s", &code)) return nullptr;
    if (!emscripten_is_main_runtime_thread()) {
        PyErr_SetString(PyExc_RuntimeError, "run_script() needs the main thread");
        return nullptr;
    }
    const char *result = emscripten_run_script_string(code);
    return PyUnicode_FromString(result ? result : "");
}

// A WId for QWindow.fromWinId(): Qt for WebAssembly takes a pointer to an
// emscripten::val holding the HTML element of a foreign window
static PyObject *web_element_handle(PyObject *, PyObject *args) {
    int id;
    if (!PyArg_ParseTuple(args, "i", &id)) return nullptr;
    emscripten::val frame = emscripten::val::global("__kiokuWeb").call<emscripten::val>("frame", id);
    if (frame.isUndefined() || frame.isNull()) Py_RETURN_NONE;
    return PyLong_FromVoidPtr(new emscripten::val(frame));
}

// Answer a request relayed by the service worker; called from the worker
// threads that run Anki's web server code
static PyObject *web_respond(PyObject *, PyObject *args) {
    int id, status;
    Py_buffer headers, body;
    if (!PyArg_ParseTuple(args, "iiy*y*", &id, &status, &headers, &body)) return nullptr;
    Py_BEGIN_ALLOW_THREADS
    MAIN_THREAD_EM_ASM({
        var dec = new TextDecoder();
        globalThis.__kiokuWeb.respond($0, $1, dec.decode(HEAPU8.slice($2, $2 + $3)),
                                      HEAPU8.slice($4, $4 + $5));
    }, id, status, headers.buf, (int)headers.len, body.buf, (int)body.len);
    Py_END_ALLOW_THREADS
    PyBuffer_Release(&headers);
    PyBuffer_Release(&body);
    Py_RETURN_NONE;
}

// Wait without blocking the page: the main thread yields to the browser with
// emscripten_sleep() (Asyncify), workers sleep. A thread started beyond the
// worker pool runs only once Emscripten's new worker has loaded, which
// needs the main thread to yield (kioku_platform._start_threads_yielding).
static PyObject *web_sleep(PyObject *, PyObject *args) {
    int ms;
    if (!PyArg_ParseTuple(args, "i", &ms)) return nullptr;
    bool main = emscripten_is_main_runtime_thread();
    Py_BEGIN_ALLOW_THREADS
    if (main)
        emscripten_sleep(ms);
    else
        usleep(ms * 1000);
    Py_END_ALLOW_THREADS
    Py_RETURN_NONE;
}

static PyMethodDef web_methods[] = {
    {"run_script", web_run_script, METH_VARARGS, nullptr},
    {"sleep", web_sleep, METH_VARARGS, nullptr},
    {"element_handle", web_element_handle, METH_VARARGS, nullptr},
    {"respond", web_respond, METH_VARARGS, nullptr},
    {nullptr, nullptr, 0, nullptr},
};

static PyModuleDef web_module = {PyModuleDef_HEAD_INIT, "_kioku_web", nullptr, -1, web_methods};

static PyObject *PyInit__kioku_web(void) {
    return PyModule_Create(&web_module);
}

// Events from the page (kioku-web.js post()) for kioku_platform.web._post()
extern "C" EMSCRIPTEN_KEEPALIVE void kioku_post(const char *json) {
    if (!Py_IsInitialized()) return;
    PyGILState_STATE gil = PyGILState_Ensure();
    PyObject *module = PyImport_ImportModule("kioku_platform.web");
    PyObject *result = module ? PyObject_CallMethod(module, "_post", "s", json) : nullptr;
    if (!result) PyErr_Print();
    Py_XDECREF(result);
    Py_XDECREF(module);
    PyGILState_Release(gil);
}

EM_JS_DEPS(kioku_web, "$stringToUTF8,$lengthBytesUTF8,$FS,malloc,free");
EM_JS(void, kioku_install_js, (), {
    globalThis.__kiokuFS = FS;
    globalThis.__kiokuWasmPost = function(text) {
        var size = lengthBytesUTF8(text) + 1;
        var ptr = _malloc(size);
        stringToUTF8(text, ptr, size);
        try {
            _kioku_post(ptr);
        } finally {
            _free(ptr);
        }
    };
});

// shell/storage.js keeps /home/web_user in IndexedDB
EM_JS_DEPS(kioku_storage, "$IDBFS,$MEMFS");

static void fail(const char *what, PyStatus status) {
    fprintf(stderr, "Kioku: %s failed: %s\n", what, status.err_msg ? status.err_msg : "?");
    Py_ExitStatusException(status);
}

static void append_path(PyConfig *config, const wchar_t *path) {
    PyStatus status = PyWideStringList_Append(&config->module_search_paths, path);
    if (PyStatus_Exception(status)) fail("module path", status);
}

int main(int argc, char *argv[]) {
    PyImport_AppendInittab("PyQt6.sip", PyInit_sip);
    PyImport_AppendInittab("PyQt6.QtCore", PyInit_QtCore);
    PyImport_AppendInittab("PyQt6.QtGui", PyInit_QtGui);
    PyImport_AppendInittab("PyQt6.QtWidgets", PyInit_QtWidgets);
    PyImport_AppendInittab("PyQt6.QtNetwork", PyInit_QtNetwork);
    PyImport_AppendInittab("PyQt6.QtSvg", PyInit_QtSvg);
    PyImport_AppendInittab("anki._rsbridge", PyInit__rsbridge);
    PyImport_AppendInittab("rpds", PyInit_rpds);
    PyImport_AppendInittab("orjson.orjson", PyInit_orjson);
    PyImport_AppendInittab("markupsafe._speedups", PyInit__speedups);
    PyImport_AppendInittab("_kioku_web", PyInit__kioku_web);
    kioku_install_js();

    PyPreConfig preconfig;
    PyPreConfig_InitIsolatedConfig(&preconfig);
    preconfig.utf8_mode = 1;
    PyStatus status = Py_PreInitialize(&preconfig);
    if (PyStatus_Exception(status)) fail("pre-init", status);

    PyConfig config;
    PyConfig_InitIsolatedConfig(&config);
    config.buffered_stdio = 0;
    config.write_bytecode = 0;
    status = PyConfig_SetString(&config, &config.home, L"/python");
    if (PyStatus_Exception(status)) fail("home", status);
    config.module_search_paths_set = 1;
    append_path(&config, L"/app");
    append_path(&config, L"/site");
    append_path(&config, L"/python/lib/python" KIOKU_PYTHON_VERSION);  // from CMake

    // --kioku only picks the entry point; Anki would take it for a file to import
    status = PyConfig_SetBytesArgv(&config, argc > 1 && strcmp(argv[1], "--kioku") == 0 ? 1 : argc, argv);
    if (PyStatus_Exception(status)) fail("argv", status);
    // the probe page runs /app/probe.py; app.html passes --kioku for the app
    bool kioku = argc > 1 && strcmp(argv[1], "--kioku") == 0;
    if (kioku)
        status = PyConfig_SetString(&config, &config.run_module, L"kioku");
    else
        status = PyConfig_SetString(&config, &config.run_filename, L"/app/probe.py");
    if (PyStatus_Exception(status)) fail("entry", status);

    status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    if (PyStatus_Exception(status)) fail("init", status);
    return Py_RunMain();
}
