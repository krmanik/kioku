"""Programs add-ons start with subprocess (ffmpeg, ffprobe, lame, ...),
bundled with the app (shared/tools/build_programs.sh).

A folder of the programs' names goes first on PATH, so shutil.which() finds
them and plain names work. subprocess.Popen also takes an add-on's own copy
(Migaku's ffmpeg.exe, Japanese Support's mecab) for the bundled one.

  Android: one executable, packaged as libkiokuprog.so so that the app may
      run it; the folder holds symlinks to it, which it tells apart by name.
  iOS: apps can't start processes, so a program runs inside the app on a
      thread of its own (the _kioku_programs module), with the add-on's pipes
      as its standard streams. Popen's wait(), poll(), communicate() and
      send_signal() work on that run.

Programs written in Python (PYTHON_PROGRAMS) run the same way on both."""

from __future__ import annotations

import errno
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
from typing import Callable

# name -> function(argv, stdin, stdout, stderr) -> exit code, run on a thread;
# the streams are binary file objects
PYTHON_PROGRAMS: dict[str, Callable] = {}

_bin_dir = ""
_native: set[str] = set()
_android_exe = ""
_cwd_lock = threading.Lock()


def _chmod(argv, stdin, stdout, stderr) -> int:
    """chmod [-R] MODE FILE...: add-ons make their bundled binaries
    executable (AnkiOCR on macOS paths); iOS has no chmod to start."""
    import stat

    args = argv[1:]
    recursive = bool(args) and args[0] == "-R"
    if recursive:
        args = args[1:]
    if len(args) < 2:
        stderr.write(b"usage: chmod [-R] mode file...\n")
        return 1
    mode, paths = args[0], args[1:]

    def new_mode(old: int) -> int:
        if mode.isdigit():
            return int(mode, 8)
        bits = {"r": 0o444, "w": 0o222, "x": 0o111}
        result = old
        for clause in mode.split(","):
            who = clause.rstrip("rwx+-=").rstrip("+-=") or "a"
            op = next((c for c in clause if c in "+-="), "+")
            perms = clause.split(op, 1)[-1]
            mask = sum(m for c, m in (("u", 0o700), ("g", 0o070), ("o", 0o007)) if c in who or "a" in who)
            value = sum(bits.get(c, 0) for c in perms) & mask
            if op == "+":
                result |= value
            elif op == "-":
                result &= ~value
            else:
                result = (result & ~mask) | value
        return result

    code = 0
    for path in paths:
        targets = [path]
        if recursive and os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                targets += [os.path.join(root, n) for n in dirs + files]
        for target in targets:
            try:
                os.chmod(target, new_mode(stat.S_IMODE(os.stat(target).st_mode)))
            except OSError as e:
                stderr.write(f"chmod: {target}: {e.strerror}\n".encode())
                code = 1
    return code


if sys.platform == "ios":
    PYTHON_PROGRAMS["chmod"] = _chmod


# what add-ons append to their copies: mecab.lin, cwebp.mac, ffmpeg.exe,
# Migaku's mecab-linux / mecab-windows.exe, ...-x86_64
_PLATFORM_SUFFIX = re.compile(
    r"([-_.](lin|linux|mac|macos|osx|darwin|win|win32|win64|windows|x64|x86_64|amd64|arm64|aarch64))+$"
)


def program_name(path: str) -> str:
    name = os.path.basename(path).lower()
    if name.endswith(".exe"):
        name = name[:-4]
    return _PLATFORM_SUFFIX.sub("", name)


def bundled(name: str) -> bool:
    return name in _native or name in PYTHON_PROGRAMS


def install(base_dir: str) -> None:
    global _bin_dir, _android_exe
    if sys.platform == "android":
        _android_exe = _android_executable()
        if _android_exe:
            _native.update(_ANDROID_PROGRAMS)
    elif sys.platform == "ios":
        try:
            import _kioku_programs
        except ImportError:
            pass
        else:
            _native.update(_kioku_programs.names())
        # Popen refuses at once on iOS; _execute_child below decides
        subprocess._can_fork_exec = True

    # not in the cache folder: Android empties that while the app runs when
    # storage is low, and every program would fail until the next start
    _bin_dir = os.path.join(base_dir, "kioku-bin")
    os.makedirs(_bin_dir, exist_ok=True)
    for name in sorted(_native | set(PYTHON_PROGRAMS)):
        path = os.path.join(_bin_dir, name)
        if _android_exe and name in _native:
            if os.path.islink(path) and os.readlink(path) == _android_exe:
                continue
            if os.path.lexists(path):
                os.remove(path)
            os.symlink(_android_exe, path)
        elif not os.path.isfile(path) or os.path.islink(path):
            # a placeholder for shutil.which(); Popen runs the program itself
            if os.path.lexists(path):
                os.remove(path)
            with open(path, "w") as f:
                f.write("#!/bin/sh\n# bundled with Kioku\n")
            os.chmod(path, 0o755)
    data = _data_dir()
    if data:
        os.environ.setdefault("TESSDATA_PREFIX", os.path.join(data, "tessdata"))
        os.environ.setdefault("ESPEAK_DATA_PATH", data)
    os.environ["PATH"] = os.pathsep.join(
        [_bin_dir] + [p for p in os.environ.get("PATH", "").split(os.pathsep) if p and p != _bin_dir]
    )
    subprocess.Popen = Popen


# the programs in libkiokuprog.so (shared/programs/kioku_prog.c)
_ANDROID_PROGRAMS = {"ffmpeg", "ffprobe", "lame", "tesseract", "espeak-ng", "espeak", "kakasi", "mecab",
                     "cwebp", "dwebp"}


def _program_started(name: str) -> None:
    """Some programs' data is downloaded (kioku.packs): offer it."""
    try:
        from kioku import packs

        packs.program_started(name)
    except Exception:
        pass


def _data_dir() -> str:
    """The programs' data files (build/programs/data), in site-packages."""
    for path in sys.path:
        candidate = os.path.join(path, "kioku_programs_data")
        if os.path.isdir(candidate):
            return candidate
    return ""


def _android_executable() -> str:
    """libkiokuprog.so in the app's native library folder (extracted on
    install: useLegacyPackaging), found next to libpython."""
    try:
        with open("/proc/self/maps") as f:
            for line in f:
                if "libpython" in line and line.rstrip().endswith(".so"):
                    path = os.path.join(os.path.dirname(line.split()[-1]), "libkiokuprog.so")
                    return path if os.access(path, os.X_OK) else ""
    except OSError:
        pass
    return ""


def _command(args, shell: bool) -> list[str] | None:
    """The argument list if it starts a bundled program, else None."""
    if isinstance(args, (str, bytes, os.PathLike)):
        args = [args]
    args = [os.fsdecode(a) for a in args]
    if shell:
        # "ffmpeg -i a.mp3 b.ogg": fine without a shell if there's nothing
        # for the shell to do
        if len(args) != 1 or any(c in args[0] for c in "|&;<>()$`*?\n"):
            return None
        try:
            args = shlex.split(args[0])
        except ValueError:
            return None
    if not args or not bundled(program_name(args[0])):
        return None
    return args


class Popen(subprocess.Popen):
    _kioku_thread: threading.Thread | None = None
    _kioku_name = ""
    _kioku_code = 0

    def _execute_child(self, args, executable, preexec_fn, close_fds, pass_fds, cwd, env,
                       startupinfo, creationflags, shell, p2cread, p2cwrite, c2pread,
                       c2pwrite, errread, errwrite, *rest):
        command = _command(args, shell)
        if command is None:
            if sys.platform == "ios":
                raise OSError(errno.ENOTSUP, f"{sys.platform} does not support processes.")
            return super()._execute_child(args, executable, preexec_fn, close_fds, pass_fds,
                                          cwd, env, startupinfo, creationflags, shell,
                                          p2cread, p2cwrite, c2pread, c2pwrite, errread,
                                          errwrite, *rest)
        name = program_name(command[0])
        _program_started(name)
        if _android_exe and name in _native:
            command[0] = os.path.join(_bin_dir, name)
            return super()._execute_child(command, None, preexec_fn, close_fds, pass_fds,
                                          cwd, env, startupinfo, creationflags, False,
                                          p2cread, p2cwrite, c2pread, c2pwrite, errread,
                                          errwrite, *rest)
        self._kioku_start(name, command, cwd, env, p2cread, p2cwrite, c2pread, c2pwrite,
                          errread, errwrite)

    # A run inside the app ------------------------------------------------------

    def _kioku_start(self, name, command, cwd, env, p2cread, p2cwrite, c2pread, c2pwrite,
                     errread, errwrite):
        # the run gets its own copies of the child's ends, closed when it
        # ends (EOF for the reader)
        def own(fd, default):
            if fd == -1:
                return os.open(os.devnull, os.O_RDONLY) if default == 0 else os.dup(default)
            return os.dup(fd)

        fds = (own(p2cread, 0), own(c2pwrite, 1), own(errwrite, 2))
        # and, as Popen's own _execute_child does, the parent closes its copies
        devnull = getattr(self, "_devnull", None)
        if p2cread != -1 and p2cwrite != -1 and p2cread != devnull:
            os.close(p2cread)
        if c2pwrite != -1 and c2pread != -1 and c2pwrite != devnull:
            os.close(c2pwrite)
        if errwrite != -1 and errread != -1 and errwrite != devnull:
            os.close(errwrite)
        if devnull is not None:
            os.close(devnull)
        command[0] = name
        self._kioku_name = name
        self.pid = -1
        self._child_created = True
        self._kioku_thread = threading.Thread(
            target=self._kioku_run, args=(name, command, fds, cwd, env),
            name=f"kioku-{name}", daemon=True)
        self._kioku_thread.start()

    def _kioku_run(self, name, command, fds, cwd, env):
        code = 1
        try:
            with _environment(cwd, env):
                if name in PYTHON_PROGRAMS:
                    with os.fdopen(fds[0], "rb") as i, os.fdopen(fds[1], "wb") as o, \
                            os.fdopen(fds[2], "wb", buffering=0) as e:
                        try:
                            code = PYTHON_PROGRAMS[name](command, i, o, e)
                        except SystemExit as exit:
                            code = exit.code if isinstance(exit.code, int) else 1
                        except Exception as exc:
                            e.write(f"{name}: {exc}\n".encode())
                            code = 1
                else:
                    import _kioku_programs

                    code = _kioku_programs.run(name, command, *fds)
        finally:
            self._kioku_code = code if code is not None else 0

    def _internal_poll(self, *args, **kwargs):
        if self._kioku_thread is None:
            return super()._internal_poll(*args, **kwargs)
        if self.returncode is None and not self._kioku_thread.is_alive():
            self.returncode = self._kioku_code
        return self.returncode

    def _wait(self, timeout):
        if self._kioku_thread is None:
            return super()._wait(timeout)
        self._kioku_thread.join(timeout)
        if self._kioku_thread.is_alive():
            raise subprocess.TimeoutExpired(self.args, timeout)
        self.returncode = self._kioku_code
        return self.returncode

    def send_signal(self, sig):
        if self._kioku_thread is None:
            return super().send_signal(sig)
        if self.poll() is not None or self._kioku_name in PYTHON_PROGRAMS:
            return
        import _kioku_programs

        # ffmpeg stops on SIGINT/SIGTERM; SIGKILL can't end a thread, so it
        # asks the same
        if sig == signal.SIGKILL:
            sig = signal.SIGTERM
        _kioku_programs.signal(self._kioku_name, sig)


class _environment:
    """A run's cwd and env, while it lasts: the process has one of each."""

    def __init__(self, cwd, env):
        self.cwd = os.fsdecode(cwd) if cwd is not None else None
        self.env = env

    def __enter__(self):
        self.saved_env = None
        if self.env is not None:
            self.saved_env = {}
            for key, value in self.env.items():
                key, value = os.fsdecode(key), os.fsdecode(value)
                if os.environ.get(key) != value:
                    self.saved_env[key] = os.environ.get(key)
                    os.environ[key] = value
        self.saved_cwd = None
        if self.cwd is not None:
            _cwd_lock.acquire()
            self.saved_cwd = os.getcwd()
            os.chdir(self.cwd)

    def __exit__(self, *exc):
        if self.saved_cwd is not None:
            try:
                os.chdir(self.saved_cwd)
            finally:
                _cwd_lock.release()
        for key, value in (self.saved_env or {}).items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def which(name: str) -> str | None:
    """The bundled program's path, for code that wants one."""
    return shutil.which(name, path=_bin_dir) if _bin_dir else None
