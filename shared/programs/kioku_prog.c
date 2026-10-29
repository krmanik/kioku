/* Runs the bundled programs (ffmpeg, mecab, tesseract, ...).
 *
 * Each program is compiled with kioku_prog.h forced in and its main renamed
 * to kioku_<name>_main. Programs that aren't built leave their (weak) entry
 * NULL.
 *
 *   KIOKU_EXECUTABLE (Android): main() picks the program from the name it was
 *       started as (a symlink named ffmpeg, mecab, ...: see
 *       shared/python/kioku/programs.py). Nothing is redirected.
 *   KIOKU_PYTHON (iOS): the _kioku_programs module runs a program on a thread
 *       of its own, with the given file descriptors as its standard streams.
 *       One run of a program at a time (programs keep global state); a run
 *       of ffmpeg also holds ffprobe's lock, since they share FFmpeg's
 *       libraries, whose log goes to the running tool's stderr. */
#include <getopt.h>
#include <libgen.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

typedef int (*kioku_main_t)(int, char **);
typedef void (*kioku_sighandler_t)(int);

#define PROGRAM(name) extern int kioku_##name##_main(int, char **) __attribute__((weak));
PROGRAM(ffmpeg)
PROGRAM(ffprobe)
PROGRAM(lame)
PROGRAM(tesseract)
PROGRAM(espeak)
PROGRAM(kakasi)
PROGRAM(mecab)
PROGRAM(cwebp)
PROGRAM(dwebp)
#undef PROGRAM

struct program {
    const char *name;
    kioku_main_t main;
    int family; /* index of the program whose lock it shares; -1: runs at once
                   (mecab: add-ons keep one running) */
};

static struct program programs[] = {
    {"ffmpeg", kioku_ffmpeg_main, 0},
    {"ffprobe", kioku_ffprobe_main, 0},
    {"lame", kioku_lame_main, 2},
    {"tesseract", kioku_tesseract_main, 3},
    {"espeak-ng", kioku_espeak_main, 4},
    {"espeak", kioku_espeak_main, 4},
    {"kakasi", kioku_kakasi_main, 6},
    {"mecab", kioku_mecab_main, -1},
    {"cwebp", kioku_cwebp_main, 8},
    {"dwebp", kioku_dwebp_main, 9},
};
#define NPROGRAMS (int)(sizeof(programs) / sizeof(programs[0]))

static struct program *find_program(const char *name) {
    for (int i = 0; i < NPROGRAMS; i++)
        if (programs[i].main && strcmp(programs[i].name, name) == 0) return &programs[i];
    return NULL;
}

/* A run inside the app ------------------------------------------------------- */

struct session {
    struct program *program;
    int argc;
    char **argv;
    FILE *in, *out, *err;
    int in_fd;
    int code;
    kioku_sighandler_t handlers[NSIG];
    /* the program's globals (kioku_state_reset), and this run's copy of them
     * while it waits for input */
    char *data, *data_end, *bss, *bss_end;
    char *own_data, *own_bss;
};

static __thread struct session *current;
/* the session of each family, for the threads a program starts itself */
static struct session *family_session[NPROGRAMS];
static pthread_mutex_t family_lock[NPROGRAMS] = {
    PTHREAD_MUTEX_INITIALIZER, PTHREAD_MUTEX_INITIALIZER, PTHREAD_MUTEX_INITIALIZER,
    PTHREAD_MUTEX_INITIALIZER, PTHREAD_MUTEX_INITIALIZER, PTHREAD_MUTEX_INITIALIZER,
    PTHREAD_MUTEX_INITIALIZER, PTHREAD_MUTEX_INITIALIZER, PTHREAD_MUTEX_INITIALIZER,
    PTHREAD_MUTEX_INITIALIZER,
};

/* the calling program's session; FFmpeg's own threads use ffmpeg's/ffprobe's */
static struct session *active(void) { return current ? current : family_session[0]; }

int kioku_in_app(void) { return current != NULL; }

FILE *kioku_stdin(void) { return current ? current->in : stdin; }
int kioku_stdin_fd(void) { return current ? current->in_fd : 0; }
FILE *kioku_stdout(void) { return current ? current->out : stdout; }
FILE *kioku_stderr(void) { return current ? current->err : stderr; }

void kioku_exit(int code) {
    if (!current) exit(code);
    current->code = code;
    fflush(current->out);
    fflush(current->err);
    pthread_exit(NULL);
}

kioku_sighandler_t kioku_signal(int sig, kioku_sighandler_t handler) {
    if (!current) return signal(sig, handler);
    if (sig <= 0 || sig >= NSIG) return SIG_ERR;
    kioku_sighandler_t old = current->handlers[sig];
    current->handlers[sig] = handler;
    return old ? old : SIG_DFL;
}

/* FFmpeg's pipe: protocol (libavformat/file.c is patched to call this): the
 * session's streams for pipe:0, pipe:1 and pipe:2 */
int kioku_fd(int fd) {
    struct session *s = active();
    if (!s || fd < 0 || fd > 2) return fd;
    return fd == 0 ? s->in_fd : fileno(fd == 1 ? s->out : s->err);
}

/* FFmpeg's log (libavutil isn't compiled with kioku_prog.h): set by
 * build_programs.sh's ffmpeg wrapper through kioku_ffmpeg_log() */
void kioku_log_write(const char *line) {
    struct session *s = active();
    fputs(line, s ? s->err : stderr);
}

/* A program's globals (state_<family>.h): copied before its first run, put
 * back before every later one. Called by the program's entry point, under its
 * family's lock. */
void kioku_state_reset(char *data, char *data_end, char *bss, char *bss_end, char **saved) {
    /* a section the program doesn't have: NULL (weak symbols on Android) */
    size_t data_size = data ? (size_t)(data_end - data) : 0;
    size_t bss_size = bss ? (size_t)(bss_end - bss) : 0;
    if (current) {
        current->data = data;
        current->data_end = data + data_size;
        current->bss = bss;
        current->bss_end = bss + bss_size;
    }
    if (!*saved) {
        *saved = malloc(data_size + 1);
        if (data_size) memcpy(*saved, data, data_size);
    } else {
        if (data_size) memcpy(data, *saved, data_size);
        if (bss_size) memset(bss, 0, bss_size);
    }
}

/* The run's standard input. A program with its globals in sections (state_
 * <family>.h) gives up its family's lock while it waits for input, with its
 * globals saved, and gets them back after: add-ons keep kakasi open for the
 * whole session (Japanese Support), so a second one would wait forever. */
static int session_read(void *cookie, char *buf, int n) {
    struct session *s = cookie;
    int family = s->program->family;
    size_t data_size = (size_t)(s->data_end - s->data), bss_size = (size_t)(s->bss_end - s->bss);
    int swap = family >= 0 && (data_size || bss_size);
    fflush(s->out);
    if (swap) {
        if (!s->own_data) s->own_data = malloc(data_size + 1);
        if (!s->own_bss) s->own_bss = malloc(bss_size + 1);
        if (data_size) memcpy(s->own_data, s->data, data_size);
        if (bss_size) memcpy(s->own_bss, s->bss, bss_size);
        family_session[family] = NULL;
        pthread_mutex_unlock(&family_lock[family]);
    }
    ssize_t r = read(s->in_fd, buf, (size_t)n);
    if (swap) {
        pthread_mutex_lock(&family_lock[family]);
        family_session[family] = s;
        if (data_size) memcpy(s->data, s->own_data, data_size);
        if (bss_size) memcpy(s->bss, s->own_bss, bss_size);
    }
    return (int)r;
}

static int session_close(void *cookie) {
    struct session *s = cookie;
    return close(s->in_fd);
}

static void *run_thread(void *arg) {
    struct session *s = arg;
    current = s;
    /* libc's getopt state (espeak-ng parses its options with it) */
    optind = 1;
#ifdef __APPLE__
    optreset = 1;
#endif
    s->code = s->program->main(s->argc, s->argv);
    fflush(s->out);
    fflush(s->err);
    return NULL;
}

/* Runs a program to the end; the descriptors are the program's (closed here).
 * Returns its exit code, or -1 if it isn't bundled. */
int kioku_run(const char *name, int argc, char **argv, int in, int out, int err) {
    struct program *p = find_program(name);
    if (!p) return -1;
    struct session s = {.program = p, .argc = argc, .argv = argv, .in_fd = in};
#ifdef __APPLE__
    s.in = funopen(&s, session_read, NULL, NULL, session_close);
#else
    s.in = fdopen(in, "r");
#endif
    s.out = fdopen(out, "w");
    s.err = fdopen(err, "w");
    setvbuf(s.err, NULL, _IONBF, 0);

    int family = p->family;
    if (family >= 0) {
        pthread_mutex_lock(&family_lock[family]);
        family_session[family] = &s;
    }
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setstacksize(&attr, 16 << 20);
    pthread_t thread;
    if (pthread_create(&thread, &attr, run_thread, &s) == 0) {
        pthread_join(thread, NULL);
    } else {
        s.code = 127;
    }
    pthread_attr_destroy(&attr);
    if (family >= 0) {
        family_session[family] = NULL;
        pthread_mutex_unlock(&family_lock[family]);
    }

    fclose(s.in);
    fclose(s.out);
    fclose(s.err);
    free(s.own_data);
    free(s.own_bss);
    return s.code;
}

/* Calls the handler the running program installed for sig (ffmpeg stops
 * cleanly on SIGINT/SIGTERM). Returns 0 if one was called. */
int kioku_signal_program(const char *name, int sig) {
    struct program *p = find_program(name);
    if (!p || p->family < 0 || sig <= 0 || sig >= NSIG) return -1;
    struct session *s = family_session[p->family];
    if (!s || s->program != p) return -1;
    kioku_sighandler_t h = s->handlers[sig];
    if (!h || h == SIG_DFL || h == SIG_IGN || h == SIG_ERR) return -1;
    h(sig);
    return 0;
}

#ifdef KIOKU_EXECUTABLE
int main(int argc, char **argv) {
    char *name = basename(argv[0]);
    struct program *p = find_program(name);
    if (!p) {
        fprintf(stderr, "kioku: no bundled program %s\n", name);
        return 127;
    }
    return p->main(argc, argv);
}
#endif

#ifdef KIOKU_PYTHON
#define PY_SSIZE_T_CLEAN
#include <Python.h>

static PyObject *py_run(PyObject *self, PyObject *args) {
    const char *name;
    PyObject *argv_list;
    int in, out, err;
    if (!PyArg_ParseTuple(args, "sO!iii", &name, &PyList_Type, &argv_list, &in, &out, &err))
        return NULL;
    Py_ssize_t argc = PyList_GET_SIZE(argv_list);
    char **argv = calloc(argc + 1, sizeof(char *));
    for (Py_ssize_t i = 0; i < argc; i++) {
        const char *a = PyUnicode_AsUTF8(PyList_GET_ITEM(argv_list, i));
        if (!a) {
            for (Py_ssize_t j = 0; j < i; j++) free(argv[j]);
            free(argv);
            return NULL;
        }
        argv[i] = strdup(a);
    }
    int code;
    Py_BEGIN_ALLOW_THREADS
    code = kioku_run(name, (int)argc, argv, in, out, err);
    Py_END_ALLOW_THREADS
    /* programs may keep pointers into argv (getopt): freed only after the run */
    for (Py_ssize_t i = 0; i < argc; i++) free(argv[i]);
    free(argv);
    return PyLong_FromLong(code);
}

static PyObject *py_signal(PyObject *self, PyObject *args) {
    const char *name;
    int sig;
    if (!PyArg_ParseTuple(args, "si", &name, &sig)) return NULL;
    return PyBool_FromLong(kioku_signal_program(name, sig) == 0);
}

static PyObject *py_names(PyObject *self, PyObject *unused) {
    PyObject *names = PyList_New(0);
    for (int i = 0; i < NPROGRAMS; i++) {
        if (!programs[i].main) continue;
        PyObject *n = PyUnicode_FromString(programs[i].name);
        PyList_Append(names, n);
        Py_DECREF(n);
    }
    return names;
}

static PyMethodDef methods[] = {
    {"run", py_run, METH_VARARGS,
     "run(name, argv, stdin_fd, stdout_fd, stderr_fd) -> exit code; closes the fds"},
    {"signal", py_signal, METH_VARARGS, "signal(name, sig) -> handled"},
    {"names", py_names, METH_NOARGS, "names() -> the bundled programs"},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "_kioku_programs", NULL, -1, methods};

PyMODINIT_FUNC PyInit__kioku_programs(void) { return PyModule_Create(&module); }
#endif
