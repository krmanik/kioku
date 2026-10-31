/* kioku_<name>_main for a program with nothing of its own to set up
 * (kioku_prog.c): -DKIOKU_NAME=<name>, and -DKIOKU_FAMILY=<family> for one
 * whose globals are put back before each run inside the app (state_<family>.h,
 * C programs only: C++ globals own memory). */
#define STR(x) #x
#define XSTR(x) STR(x)
#define CAT(a, b) a##b
#define XCAT(a, b) CAT(a, b)
#define TOOL XCAT(XCAT(kioku_, KIOKU_NAME), _tool_main)
#define ENTRY XCAT(XCAT(kioku_, KIOKU_NAME), _main)

int TOOL(int argc, char **argv);
int ENTRY(int argc, char **argv);

#ifdef KIOKU_FAMILY
int kioku_in_app(void);
void kioku_state_reset(char *data, char *data_end, char *bss, char *bss_end, char **saved);
#ifdef __APPLE__
extern char data_start[] __asm("section$start$__DATA$__kd_" XSTR(KIOKU_FAMILY));
extern char data_end[] __asm("section$end$__DATA$__kd_" XSTR(KIOKU_FAMILY));
extern char bss_start[] __asm("section$start$__DATA$__kb_" XSTR(KIOKU_FAMILY));
extern char bss_end[] __asm("section$end$__DATA$__kb_" XSTR(KIOKU_FAMILY));
#else
/* weak: ELF has no such symbols for a section a program doesn't have */
extern char data_start[] __asm("__start_kd_" XSTR(KIOKU_FAMILY)) __attribute__((weak));
extern char data_end[] __asm("__stop_kd_" XSTR(KIOKU_FAMILY)) __attribute__((weak));
extern char bss_start[] __asm("__start_kb_" XSTR(KIOKU_FAMILY)) __attribute__((weak));
extern char bss_end[] __asm("__stop_kb_" XSTR(KIOKU_FAMILY)) __attribute__((weak));
#endif
static char *saved_state;
#endif

int ENTRY(int argc, char **argv) {
#ifdef KIOKU_FAMILY
    if (kioku_in_app()) kioku_state_reset(data_start, data_end, bss_start, bss_end, &saved_state);
#endif
    return TOOL(argc, argv);
}
