/* tesseract's entry point (kioku_prog.c). libtesseract (not compiled with
 * kioku_prog.h) writes "stdout" output and leptonica reads "stdin" input
 * with the process's streams, so inside the app those go through temporary
 * files: the input is copied from the run's stdin, the output files
 * (<base>.txt, .tsv, .hocr, ...) are copied to its stdout. */
#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int kioku_tesseract_tool_main(int argc, char **argv);
int kioku_tesseract_main(int argc, char **argv);
int kioku_in_app(void);
FILE *kioku_stdin(void);
FILE *kioku_stdout(void);

static int is_std(const char *a) { return strcmp(a, "-") == 0 || strcmp(a, "stdin") == 0 || strcmp(a, "stdout") == 0; }

static void copy(FILE *from, FILE *to) {
    char buf[65536];
    size_t n;
    while ((n = fread(buf, 1, sizeof(buf), from)) > 0) fwrite(buf, 1, n, to);
}

int kioku_tesseract_main(int argc, char **argv) {
    /* tesseract <image> <outputbase> [options...]; anything else (--version,
     * --list-langs) as it is */
    if (!kioku_in_app() || argc < 3 || argv[1][0] == '-' && argv[1][1] != 0 ||
        (!is_std(argv[1]) && !is_std(argv[2])))
        return kioku_tesseract_tool_main(argc, argv);

    const char *tmp = getenv("TMPDIR");
    char template[1024];
    snprintf(template, sizeof(template), "%s/kioku-tesseract-XXXXXX", tmp ? tmp : "/tmp");
    char *d = mkdtemp(template);
    if (!d) return 1;

    char input[1100], base[1100];
    char **args = calloc(argc + 1, sizeof(char *));
    memcpy(args, argv, argc * sizeof(char *));
    if (is_std(argv[1])) {
        snprintf(input, sizeof(input), "%s/input", d);
        FILE *f = fopen(input, "wb");
        if (f) {
            copy(kioku_stdin(), f);
            fclose(f);
        }
        args[1] = input;
    }
    int to_stdout = is_std(argv[2]);
    if (to_stdout) {
        snprintf(base, sizeof(base), "%s/out", d);
        args[2] = base;
    }
    int code = kioku_tesseract_tool_main(argc, args);
    free(args);

    DIR *dp = opendir(d);
    struct dirent *e;
    while (dp && (e = readdir(dp))) {
        if (e->d_name[0] == '.') continue;
        char path[1400];
        snprintf(path, sizeof(path), "%s/%s", d, e->d_name);
        if (to_stdout && strncmp(e->d_name, "out.", 4) == 0) {
            FILE *f = fopen(path, "rb");
            if (f) {
                copy(f, kioku_stdout());
                fclose(f);
            }
        }
        unlink(path);
    }
    if (dp) closedir(dp);
    rmdir(d);
    return code;
}
