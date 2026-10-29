/* Forced into every bundled program's sources (-include kioku_prog.h).
 *
 * stdin, stdout, stderr, exit() and signal() go through kioku_prog.c (and
 * kioku_cin(), kioku_cout(), kioku_cerr() in C++: kioku_iostream.cpp). In a
 * real process (the Android executable) they behave as usual; when a program
 * runs inside the app (iOS, which can't start processes) they use the
 * add-on's pipes, end only the program's thread and leave the app's signal
 * handlers alone. */
#ifndef KIOKU_PROG_H
#define KIOKU_PROG_H

#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef __cplusplus
extern "C" {
#define KIOKU_NORETURN [[noreturn]]
#else
#define KIOKU_NORETURN _Noreturn
#endif

typedef void (*kioku_sighandler_t)(int);

FILE *kioku_stdin(void);
FILE *kioku_stdout(void);
FILE *kioku_stderr(void);
KIOKU_NORETURN void kioku_exit(int code);
kioku_sighandler_t kioku_signal(int sig, kioku_sighandler_t handler);

/* -DKIOKU_MAIN=kioku_<name>_main on the file with the program's main */
#ifdef KIOKU_MAIN
int KIOKU_MAIN(int argc, char **argv);
#define main KIOKU_MAIN
#endif

#ifdef __cplusplus
}
#include <iosfwd>
std::istream &kioku_cin();
std::ostream &kioku_cout();
std::ostream &kioku_cerr();
#endif

#undef stdin
#undef stdout
#undef stderr
#define stdin kioku_stdin()
#define stdout kioku_stdout()
#define stderr kioku_stderr()
#define exit kioku_exit
#define signal kioku_signal

/* the functions that use the standard streams implicitly */
#define printf(...) fprintf(stdout, __VA_ARGS__)
#define vprintf(fmt, ap) vfprintf(stdout, fmt, ap)
#define puts(s) (fputs(s, stdout) < 0 ? EOF : fputc('\n', stdout))
#define putchar(c) fputc(c, stdout)
#define getchar() fgetc(stdin)
#define perror(s) fprintf(stderr, "%s%s%s\n", (s) ? (s) : "", (s) ? ": " : "", strerror(errno))

#endif
