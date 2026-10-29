"""Kioku entry point (iOS and native Android): prepare the environment, patch
the few places where Anki assumes a desktop OS, then run the unmodified Anki
desktop app."""

import io
import logging
import os
import sys
import traceback

import kioku_platform as platform

HOME = os.path.expanduser("~")
DOCUMENTS = platform.documents_dir()
LOG_PATH = os.path.join(DOCUMENTS, "kioku.log")


class _Tee(io.TextIOBase):
    """Send output to both the system log and Documents/kioku.log."""

    def __init__(self, stream, log):
        self._stream = stream
        self._log = log

    def write(self, text):
        try:
            self._stream.write(text)
        except Exception:
            pass
        try:
            self._log.write(text)
            self._log.flush()
        except Exception:
            pass
        return len(text)

    def flush(self):
        try:
            self._stream.flush()
        except Exception:
            pass

    @property
    def encoding(self):
        return "utf-8"

    def isatty(self):
        return False


def _setup_logging() -> None:
    os.makedirs(DOCUMENTS, exist_ok=True)
    log = open(LOG_PATH, "w", encoding="utf-8", buffering=1)
    sys.stdout = _Tee(sys.stdout, log)
    sys.stderr = _Tee(sys.stderr, log)
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )


def _setup_environment() -> None:
    # Anki keeps its data in $XDG_DATA_HOME/Anki2
    os.environ.setdefault("XDG_DATA_HOME", DOCUMENTS)
    os.environ.setdefault("XDG_CONFIG_HOME", platform.config_dir())
    os.environ.setdefault("XDG_CACHE_HOME", platform.cache_dir())
    os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
    os.environ.setdefault("LANG", "en_US.UTF-8")


def main() -> None:
    _setup_logging()
    _setup_environment()
    print(f"Kioku: Python {sys.version} on {sys.platform}")
    try:
        platform.prepare()
        from kioku import patches, programs

        try:
            programs.install(platform.cache_dir())
        except Exception:
            traceback.print_exc()

        patches.apply()
        import aqt

        aqt.run()
    except SystemExit as exit:
        _exit(exit.code if isinstance(exit.code, int) else 0)
    except BaseException:
        traceback.print_exc()
        raise
    _exit(0)


def _exit(code: int) -> None:
    """Leave without the interpreter's shutdown: sip's atexit clean-up then
    visits Qt objects Qt has already deleted and sometimes crashed
    (cleanup_qobject, after Quit in the profile window). Anki has closed
    the collection and saved the profile by the time aqt.run() returns."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass
    logging.shutdown()
    os._exit(code)


main()
