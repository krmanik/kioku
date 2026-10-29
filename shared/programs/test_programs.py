"""Test the bundled programs the way add-ons use them, through
subprocess and shared/python/kioku/programs.py.

    python3.14 shared/programs/test_programs.py build/programs/macos/lib

On the build machine (build_programs.sh macos) every program runs inside
this process, as on iOS. On a device, kioku.programs is installed already:
run test(tmp_dir) from devcmd."""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def check(name, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + name + (f": {detail}" if detail and not condition else ""))
    return bool(condition)


def run(*args, **kwargs):
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("timeout", 120)
    return subprocess.run(list(args), **kwargs)


def test(tmp):
    results = []
    ok = lambda *a: results.append(check(*a))

    p = run("ffmpeg", "-hide_banner", "-version")
    ok("ffmpeg -version", p.returncode == 0 and b"ffmpeg version" in p.stdout, p.stderr[-300:])
    ok("which ffmpeg", shutil.which("ffmpeg") is not None)

    mp3 = os.path.join(tmp, "tone.mp3")
    p = run("ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:a", "libmp3lame", mp3)
    ok("encode mp3 (libmp3lame)", p.returncode == 0 and os.path.getsize(mp3) > 1000, p.stderr[-300:])

    p = run("ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", mp3)
    try:
        duration = float(json.loads(p.stdout)["format"]["duration"])
    except Exception:
        duration = 0
    ok("ffprobe json to stdout", 1.9 < duration < 2.2, p.stdout[-300:])

    # pydub: decode to WAV on stdout, read with communicate()
    p = subprocess.Popen(["ffmpeg", "-i", mp3, "-f", "wav", "-"], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    out, err = p.communicate(timeout=60)
    ok("wav to stdout (pipe:1)", p.returncode == 0 and out[:4] == b"RIFF" and len(out) > 100000,
       err[-300:])

    # and from stdin
    with open(mp3, "rb") as f:
        data = f.read()
    p = run("ffmpeg", "-i", "pipe:0", "-f", "ogg", "-c:a", "libvorbis", "-", input=data)
    ok("stdin to stdout, libvorbis", p.returncode == 0 and p.stdout[:4] == b"OggS", p.stderr[-300:])

    encoders = [
        ("libopus", ["-f", "lavfi", "-i", "sine=duration=1", "-c:a", "libopus"], "a.opus"),
        ("aac", ["-f", "lavfi", "-i", "sine=duration=1", "-c:a", "aac"], "a.m4a"),
        ("flac", ["-f", "lavfi", "-i", "sine=duration=1", "-c:a", "flac"], "a.flac"),
        ("libwebp", ["-f", "lavfi", "-i", "testsrc=size=320x240", "-frames:v", "1", "-c:v", "libwebp"], "a.webp"),
        ("mjpeg", ["-f", "lavfi", "-i", "testsrc=size=320x240", "-frames:v", "1"], "a.jpg"),
        ("png", ["-f", "lavfi", "-i", "testsrc=size=320x240", "-frames:v", "1"], "a.png"),
        ("gif", ["-f", "lavfi", "-i", "testsrc=size=160x120:duration=1"], "a.gif"),
        ("libx264", ["-f", "lavfi", "-i", "testsrc=size=320x240:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p"], "a.mp4"),
        ("libvpx-vp9", ["-f", "lavfi", "-i", "testsrc=size=160x120:duration=0.5", "-c:v", "libvpx-vp9", "-deadline", "realtime"], "a.webm"),
        ("libaom-av1 (AVIF)", ["-f", "lavfi", "-i", "testsrc=size=160x120", "-frames:v", "1", "-c:v", "libaom-av1", "-still-picture", "1"], "a.avif"),
    ]
    for name, args, out_name in encoders:
        path = os.path.join(tmp, out_name)
        p = run("ffmpeg", "-y", "-hide_banner", *args, path)
        ok(f"encode {name}", p.returncode == 0 and os.path.exists(path) and os.path.getsize(path) > 0,
           p.stderr[-300:])

    # a cut, as subs2srs-style add-ons do
    clip = os.path.join(tmp, "clip.mp4")
    p = run("ffmpeg", "-y", "-ss", "0.2", "-i", os.path.join(tmp, "a.mp4"), "-t", "0.5", "-c", "copy", clip)
    ok("cut with -ss/-t", p.returncode == 0 and os.path.exists(clip), p.stderr[-300:])

    p = run("ffmpeg", "-i", os.path.join(tmp, "missing.mp3"), os.path.join(tmp, "x.wav"))
    ok("error: exit code and message", p.returncode != 0 and b"No such file" in p.stderr, p.stderr[-300:])

    p = run("ffmpeg", "-y", "-i", "tone.mp3", "tone.wav", cwd=tmp)
    ok("cwd=", p.returncode == 0 and os.path.exists(os.path.join(tmp, "tone.wav")), p.stderr[-300:])

    p = run("ffmpeg -y -i tone.mp3 tone2.ogg", shell=True, cwd=tmp)
    ok("shell=True, simple command", p.returncode == 0, p.stderr[-300:])

    codes = []
    threads = [threading.Thread(target=lambda: codes.append(
        run("ffprobe", "-v", "error", "-show_format", mp3).returncode)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ok("4 ffprobe runs at once", codes == [0, 0, 0, 0], codes)

    p = subprocess.Popen(["ffmpeg", "-re", "-f", "lavfi", "-i", "sine=duration=600", "-f", "null", "-"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    started = time.time()
    p.terminate()
    try:
        p.wait(timeout=20)
        stopped = True
    except subprocess.TimeoutExpired:
        stopped = False
    ok("terminate() stops a run", stopped and time.time() - started < 20)
    try:
        subprocess.run(["ffmpeg", "-re", "-f", "lavfi", "-i", "sine=duration=600", "-f", "null", "-"],
                       capture_output=True, timeout=1)
        timed_out = False
    except subprocess.TimeoutExpired:
        timed_out = True
    ok("run(timeout=) raises and stops", timed_out)

    p = run("ffmpeg", "-y", "-f", "lavfi", "-i", "sine=duration=1", os.path.join(tmp, "again.mp3"))
    ok("runs after a stopped one", p.returncode == 0, p.stderr[-300:])

    for name, extra in TESTS:
        results.append(extra(tmp, ok) is not False)
    failed = results.count(False)
    print(f"{len(results) - failed}/{len(results)} passed")
    return failed == 0


def test_lame(tmp, ok):
    wav = os.path.join(tmp, "tone.wav")
    mp3 = os.path.join(tmp, "lame.mp3")
    p = run("lame", "--quiet", "-b", "64", wav, mp3)
    ok("lame wav to mp3", p.returncode == 0 and os.path.getsize(mp3) > 1000, p.stderr[-300:])
    p = run("lame", "--quiet", "-", "-", input=open(wav, "rb").read())
    ok("lame stdin to stdout", p.returncode == 0 and len(p.stdout) > 1000, p.stderr[-300:])
    p = run("lame", "--quiet", os.path.join(tmp, "missing.wav"), mp3)
    ok("lame error", p.returncode != 0)


# Japanese Support's dictionaries (build/programs/testdata/japanese, or
# JAPANESE_SUPPORT)
JAPANESE = os.environ.get("JAPANESE_SUPPORT") or os.path.join(
    HERE, "..", "..", "build", "programs", "testdata", "japanese")


def test_mecab(tmp, ok):
    if not os.path.exists(os.path.join(JAPANESE, "sys.dic")):
        print("skip mecab: no dictionary in " + JAPANESE)
        return
    # as Japanese Support does: a mecab that stays open, a line at a time
    args = ["--node-format=%m[%f[7]] ", "--eos-format=\n", "--unk-format=%m[] ",
            "-d", JAPANESE, "-r", os.path.join(JAPANESE, "mecabrc")]
    procs = [subprocess.Popen([os.path.join(JAPANESE, "mecab.lin")] + args, bufsize=-1,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT) for _ in range(2)]
    answers = []
    for text in ("日本語を勉強します", "漢字", "東京へ行きました"):
        for p in procs:
            p.stdin.write(text.encode() + b"\n")
            p.stdin.flush()
            answers.append(p.stdout.readline().decode().strip())
    ok("mecab, two open at once, a line at a time",
       answers[0].startswith("日本語[ニホンゴ] を[ヲ] 勉強[ベンキョウ]") and answers[0] == answers[1]
       and answers[2] == answers[3] == "漢字[カンジ]" and "行き[イキ]" in answers[4], answers)
    for p in procs:
        p.stdin.close()
        p.wait(timeout=10)
    ok("mecab ends at end of input", all(p.returncode == 0 for p in procs),
       [p.returncode for p in procs])
    p = run("mecab", "-d", JAPANESE, "-r", os.path.join(JAPANESE, "mecabrc"), "-Owakati",
            input="すもももももももものうち\n".encode())
    ok("mecab -Owakati", p.returncode == 0 and p.stdout.decode().split() ==
       ["すもも", "も", "もも", "も", "もも", "の", "うち"], p.stdout[-200:])


def test_kakasi(tmp, ok):
    if not os.path.exists(os.path.join(JAPANESE, "kanwadict")):
        print("skip kakasi: no dictionary in " + JAPANESE)
        return
    os.environ["ITAIJIDICT"] = os.path.join(JAPANESE, "itaijidict")
    os.environ["KANWADICT"] = os.path.join(JAPANESE, "kanwadict")
    p = subprocess.Popen([os.path.join(JAPANESE, "kakasi"), "-isjis", "-osjis", "-u", "-JH", "-KH"],
                         bufsize=-1, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT)
    readings = []
    for text in ("漢字", "カタカナ"):
        p.stdin.write(text.encode("sjis") + b"\n")
        p.stdin.flush()
        readings.append(p.stdout.readline().rstrip(b"\r\n").decode("sjis"))
    ok("kakasi, Japanese Support's way", readings == ["かんじ", "かたかな"], readings)
    p.stdin.close()
    p.wait(timeout=10)
    p = run("kakasi", "-iutf8", "-outf8", "-JH", input="日本語\n".encode())
    ok("kakasi again (state reset)", p.stdout.decode().strip() == "にほんご", p.stdout)


# (name, function(tmp, ok)), after ffmpeg's: lame reads the WAV made above
TESTS = [("lame", test_lame), ("mecab", test_mecab), ("kakasi", test_kakasi)]


if __name__ == "__main__":
    lib = os.path.abspath(sys.argv[1])
    sys.path[:0] = [lib, os.path.join(HERE, "..", "python")]
    from kioku import programs

    import _kioku_programs

    # as on iOS: every bundled program runs inside this process
    programs._native.update(_kioku_programs.names())
    with tempfile.TemporaryDirectory() as tmp:
        programs._bin_dir = os.path.join(tmp, "bin")
        os.makedirs(programs._bin_dir)
        for name in programs._native:
            path = os.path.join(programs._bin_dir, name)
            open(path, "w").close()
            os.chmod(path, 0o755)
        os.environ["PATH"] = programs._bin_dir + os.pathsep + os.environ["PATH"]
        subprocess.Popen = programs.Popen
        work = os.path.join(tmp, "work")
        os.makedirs(work)
        sys.exit(0 if test(work) else 1)
