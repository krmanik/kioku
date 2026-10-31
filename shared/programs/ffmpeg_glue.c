/* ffmpeg and ffprobe entry points (kioku_prog.c). Inside the app each run
 * starts with the tools' globals as they were before the first, FFmpeg's log
 * goes to the running tool's stderr and ffmpeg doesn't read keys from
 * standard input (-nostdin), which isn't the add-on's pipe. */
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>

#include "libavutil/log.h"

int kioku_ffmpeg_tool_main(int argc, char **argv);
int kioku_ffprobe_tool_main(int argc, char **argv);
void kioku_log_write(const char *line);
int kioku_in_app(void);
void kioku_state_reset(char *data, char *data_end, char *bss, char *bss_end, char **saved);

/* the tools' globals (state_ff.h) */
#ifdef __APPLE__
extern char data_start[] __asm("section$start$__DATA$__kd_ff");
extern char data_end[] __asm("section$end$__DATA$__kd_ff");
extern char bss_start[] __asm("section$start$__DATA$__kb_ff");
extern char bss_end[] __asm("section$end$__DATA$__kb_ff");
#else
extern char data_start[] __asm("__start_kd_ff");
extern char data_end[] __asm("__stop_kd_ff");
extern char bss_start[] __asm("__start_kb_ff");
extern char bss_end[] __asm("__stop_kb_ff");
#endif
static char *saved_state;

static void log_callback(void *avcl, int level, const char *fmt, va_list vl) {
    static int print_prefix = 1;
    char line[4096];
    if (level > av_log_get_level()) return;
    av_log_format_line2(avcl, level, fmt, vl, line, sizeof(line), &print_prefix);
    kioku_log_write(line);
}

static int run(int (*tool)(int, char **), int argc, char **argv, int nostdin) {
    if (!kioku_in_app()) return tool(argc, argv);
    kioku_state_reset(data_start, data_end, bss_start, bss_end, &saved_state);
    av_log_set_callback(log_callback);
    av_log_set_level(AV_LOG_INFO);
    av_log_set_flags(0);
    char **args = calloc(argc + 2, sizeof(char *));
    int n = 0;
    args[n++] = argv[0];
    if (nostdin) args[n++] = "-nostdin";
    for (int i = 1; i < argc; i++) args[n++] = argv[i];
    int code = tool(n, args);
    free(args);
    return code;
}

int kioku_ffmpeg_main(int argc, char **argv) { return run(kioku_ffmpeg_tool_main, argc, argv, 1); }
int kioku_ffprobe_main(int argc, char **argv) { return run(kioku_ffprobe_tool_main, argc, argv, 0); }
