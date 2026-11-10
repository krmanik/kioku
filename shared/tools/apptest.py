#!/usr/bin/env python3
"""Run Kioku's in-app tests (shared/tests/app/suite.py) and the crash sweep
(ios/tools/smoke.py) in the app on a device, and report pass/fail.

    python3 -I shared/tools/apptest.py android            # emulator or phone (adb)
    python3 -I shared/tools/apptest.py ios-sim             # iOS Simulator
    python3 -I shared/tools/apptest.py ios                 # iPhone (devicectl)

The app must be a development build (the run scripts make one:
android/tools/run_device.sh, ios/tools/run_sim.sh, ios/tools/run_device.sh);
this script relaunches it in development mode, waits for its command channel,
runs the tests and writes build/test-reports/<target>-<time>.{md,xml}
(JUnit). The exit status is 1 when a test fails, 2 when the app can't be
reached. The tests create the deck "Kioku Test" in the open profile and
remove it again; nothing else in the profile changes.

Options:
    --only a,b       run only these tests (names: --list)
    --no-network     skip the tests that need the internet
    --no-smoke       skip the crash sweep
    --no-launch      use the running app as it is
    --device ID      adb serial, simulator name/UDID or iPhone UDID
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SUITE = os.path.join(ROOT, "shared", "tests", "app", "suite.py")
SMOKE = os.path.join(ROOT, "ios", "tools", "smoke.py")
APP_ID = "io.ankidesk.kioku"
REPORTS = os.path.join(ROOT, "build", "test-reports")


def versions() -> dict[str, str]:
    out = {}
    with open(os.path.join(ROOT, "shared", "versions.env"), encoding="utf8") as f:
        for line in f:
            if m := re.match(r"^([A-Z0-9_]+)=(.*)$", line.strip()):
                out[m[1]] = m[2].strip('"')
    return out


def run(args: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, **kw)


# --- transports: put a file into / read a file from the app's Documents -----


class Target:
    name = ""

    def launch(self) -> None: ...
    def put(self, local: str, rel: str) -> bool: ...
    def read(self, rel: str) -> str | None: ...
    def remove(self, rel: str) -> None: ...
    def alive(self) -> bool:
        return True


class Android(Target):
    name = "android"

    def __init__(self, serial: str | None) -> None:
        sdk = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME") \
            or os.path.expanduser("~/Library/Android/sdk")
        adb = os.path.join(sdk, "platform-tools", "adb")
        self.adb = [adb if os.path.exists(adb) else "adb"]
        if serial:
            self.adb += ["-s", serial]
        self.docs = f"/sdcard/Android/data/{APP_ID}/files"

    def sh(self, *cmd: str) -> subprocess.CompletedProcess:
        return run(self.adb + ["shell", *cmd])

    def launch(self) -> None:
        # the sync server test shows a notification: a permission prompt
        # would sit over the app with nobody to answer it
        self.sh("pm", "grant", APP_ID, "android.permission.POST_NOTIFICATIONS")
        self.sh("am", "force-stop", APP_ID)
        self.sh(f"mkdir -p {self.docs} && touch {self.docs}/.kioku-dev")
        self.sh("am", "start", "-n", f"{APP_ID}/.KiokuActivity", "--ez", "dev", "true")

    def put(self, local: str, rel: str) -> bool:
        return run(self.adb + ["push", local, f"{self.docs}/{rel}"]).returncode == 0

    def read(self, rel: str) -> str | None:
        p = self.sh("cat", f"{self.docs}/{rel}")
        return p.stdout if p.returncode == 0 else None

    def remove(self, rel: str) -> None:
        self.sh("rm", "-f", f"{self.docs}/{rel}")

    def alive(self) -> bool:
        return bool(self.sh("pidof", APP_ID).stdout.strip())


class IosSim(Target):
    name = "ios-sim"

    def __init__(self, device: str | None) -> None:
        if not device:
            booted = run(["xcrun", "simctl", "list", "devices", "booted"]).stdout
            ids = re.findall(r"\(([0-9A-F-]{36})\) \(Booted\)", booted)
            device = ids[0] if ids else None
        if not device:
            sys.exit("no booted simulator: start one (ios/tools/run_sim.sh) or pass --device")
        self.dev = device

    def documents(self) -> str:
        p = run(["xcrun", "simctl", "get_app_container", self.dev, APP_ID, "data"])
        if p.returncode != 0:
            sys.exit(f"Kioku isn't installed on simulator {self.dev}: run ios/tools/run_sim.sh")
        return os.path.join(p.stdout.strip(), "Documents")

    def launch(self) -> None:
        env = dict(os.environ, SIMCTL_CHILD_KIOKU_DEV="1", SIMCTL_CHILD_USER="mobile")
        run(["xcrun", "simctl", "launch", "--terminate-running-process", self.dev, APP_ID], env=env)

    def put(self, local: str, rel: str) -> bool:
        shutil.copy(local, os.path.join(self.documents(), rel))
        return True

    def read(self, rel: str) -> str | None:
        try:
            with open(os.path.join(self.documents(), rel), encoding="utf8") as f:
                return f.read()
        except OSError:
            return None

    def remove(self, rel: str) -> None:
        try:
            os.remove(os.path.join(self.documents(), rel))
        except OSError:
            pass

    def alive(self) -> bool:
        p = run(["xcrun", "simctl", "spawn", self.dev, "launchctl", "list"])
        return APP_ID in p.stdout


class Iphone(Target):
    name = "ios"

    def __init__(self, device: str | None) -> None:
        if not device:
            out = run(["xcrun", "devicectl", "list", "devices"]).stdout
            ids = [re.search(r"[0-9A-F]{8}-[0-9A-F]{16}", line) for line in out.splitlines()
                   if "physical" in line or "connected" in line]
            ids = [m[0] for m in ids if m]
            device = ids[0] if ids else None
        if not device:
            sys.exit("no iPhone connected: plug one in or pass --device")
        self.dev = device
        self.tmp = tempfile.mkdtemp(prefix="kioku-apptest-")

    def copy(self, direction: str, src: str, dst: str) -> bool:
        p = run(["xcrun", "devicectl", "device", "copy", direction, "--device", self.dev,
                 "--domain-type", "appDataContainer", "--domain-identifier", APP_ID,
                 "--source", src, "--destination", dst])
        return p.returncode == 0

    def launch(self) -> None:
        run(["xcrun", "devicectl", "device", "process", "launch", "--device", self.dev,
             "--terminate-existing", "--environment-variables", '{"KIOKU_DEV": "1"}', APP_ID])

    def put(self, local: str, rel: str) -> bool:
        # devicectl reports a failure when the app picked the file up first
        self.copy("to", local, f"Documents/{rel}")
        return True

    def read(self, rel: str) -> str | None:
        dst = os.path.join(self.tmp, "read")
        if os.path.exists(dst):
            os.remove(dst)
        if not self.copy("from", f"Documents/{rel}", dst):
            return None
        with open(dst, encoding="utf8") as f:
            return f.read()

    def remove(self, rel: str) -> None:
        empty = os.path.join(self.tmp, "empty")
        open(empty, "w").close()
        self.copy("to", empty, f"Documents/{rel}")


# --- the command channel ------------------------------------------------------


def command(target: Target, code: str, timeout: float = 30) -> str | None:
    """Run code in the app (devtools.py) and return its output."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
    target.remove(".kioku-cmd.out")
    target.put(f.name, ".kioku-cmd.py")
    os.remove(f.name)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(1)
        out = target.read(".kioku-cmd.out")
        if out:
            return out
    return None


# A fresh install first asks for the language (before the main window
# exists) and to confirm it, and may show the profile list: answer like a
# user who takes the defaults. Modal dialogs are answered from a timer, so the
# command returns first (devtools.py).
FIRST_RUN = """
from aqt.qt import QApplication, QDialog, QMessageBox, QTimer
mw = aqt.mw
def _answer():
    for w in QApplication.topLevelWidgets():
        if not w.isVisible() or w is mw:
            continue
        if isinstance(w, QMessageBox):
            b = w.button(QMessageBox.StandardButton.Yes) or w.button(QMessageBox.StandardButton.Ok)
            b.click() if b else w.accept()
        elif mw is not None and w is getattr(mw, "profileDiag", None):
            mw.profileForm.profiles.setCurrentRow(0)
            mw.onOpenProfile()
        elif isinstance(w, QDialog):
            w.accept()
QTimer.singleShot(0, _answer)
print('READY', mw is not None and mw.col is not None)
"""


def wait_ready(target: Target, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        out = command(target, FIRST_RUN, 10)
        if out and "READY True" in out:
            return True
        time.sleep(2)
    return False


def run_suite(target: Target, expected: str, only: list[str], network: bool,
              timeout: float) -> tuple[list[dict], str]:
    header = (f"EXPECTED_VERSION = {expected!r}\nONLY = {only!r}\nNETWORK = {network!r}\n")
    with open(SUITE, encoding="utf8") as f:
        code = header + f.read()
    out = command(target, code, 30)
    if not out or "apptest started" not in out:
        return [], f"the suite didn't start: {out!r}"
    results: list[dict] = []
    deadline = time.monotonic() + timeout
    shown = 0
    while time.monotonic() < deadline:
        time.sleep(2)
        text = target.read(".kioku-test/results.jsonl") or ""
        results = [json.loads(line) for line in text.splitlines() if line.strip()]
        for r in results[shown:]:
            if "test" in r:
                print(f"  {r['status'].upper():4}  {r['test']:16} {r['detail']}", flush=True)
        shown = len(results)
        if results and results[-1].get("done"):
            return results[:-1], ""
        if not target.alive():
            return results, "the app quit or crashed"
    return results, f"no result after {timeout:.0f} s"


def run_smoke(target: Target, timeout: float) -> tuple[list[dict], str]:
    """The crash sweep: opens every window; its lines go to kioku.log."""
    with open(SMOKE, encoding="utf8") as f:
        code = f.read()
    out = command(target, code, 30)
    if not out or "sweep started" not in out:
        return [], f"the sweep didn't start: {out!r}"
    deadline = time.monotonic() + timeout
    log = ""
    while time.monotonic() < deadline:
        time.sleep(3)
        log = target.read("kioku.log") or ""
        if "SWEEP done" in log:
            break
        if not target.alive():
            break
    lines = [line for line in log.splitlines() if line.startswith("SWEEP ")]
    # the log may hold an earlier sweep: keep the last one
    starts = [i for i, line in enumerate(lines) if re.match(r"SWEEP 0 \w", line) and line.endswith("start")]
    if starts:
        lines = lines[starts[-1]:]
    steps: dict[str, dict] = {}
    for line in lines:
        if m := re.match(r"SWEEP (\d+) (\S+): (.*)$", line):
            n, name, rest = m.groups()
            if rest == "start":
                steps[name] = {"test": f"sweep {n} {name}", "status": "fail",
                               "detail": "never finished (crash or hang)", "seconds": 0}
            elif rest.startswith("ok"):
                steps[name] = {"test": f"sweep {n} {name}", "status": "pass",
                               "detail": rest[2:].strip(" ()"), "seconds": 0}
            elif rest == "EXCEPTION":
                steps[name] = {"test": f"sweep {n} {name}", "status": "fail",
                               "detail": "exception (see kioku.log)", "seconds": 0}
    error = "" if "SWEEP done" in log else "no \"SWEEP done\": the app crashed, quit or hangs"
    return list(steps.values()), error


# --- reports --------------------------------------------------------------------


def write_reports(target: str, sections: dict[str, tuple[list[dict], str]], info: str) -> str:
    os.makedirs(REPORTS, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = os.path.join(REPORTS, f"{target}-{stamp}")
    icon = {"pass": "✅", "fail": "❌", "skip": "➖"}
    md = [f"# Kioku app tests: {target}", "", f"{datetime.datetime.now():%Y-%m-%d %H:%M}, {info}", ""]
    suites = ET.Element("testsuites")
    for section, (results, error) in sections.items():
        md += [f"## {section}", "", "| Test | Result | Detail |", "| --- | --- | --- |"]
        for r in results:
            md.append(f"| {r['test']} | {icon.get(r['status'], r['status'])} | "
                      f"{str(r.get('detail', '')).replace('|', '/')} |")
        if error:
            md.append(f"| (run) | ❌ | {error} |")
        md.append("")
        suite = ET.SubElement(suites, "testsuite", name=f"{target}.{section}",
                              tests=str(len(results) + bool(error)),
                              failures=str(sum(r["status"] == "fail" for r in results) + bool(error)),
                              skipped=str(sum(r["status"] == "skip" for r in results)))
        for r in results:
            case = ET.SubElement(suite, "testcase", classname=f"{target}.{section}", name=r["test"],
                                 time=str(r.get("seconds", 0)))
            if r["status"] == "fail":
                ET.SubElement(case, "failure", message=str(r.get("detail", ""))).text = r.get("traceback", "")
            elif r["status"] == "skip":
                ET.SubElement(case, "skipped", message=str(r.get("detail", "")))
        if error:
            case = ET.SubElement(suite, "testcase", classname=f"{target}.{section}", name="(run)")
            ET.SubElement(case, "failure", message=error)
    with open(base + ".md", "w", encoding="utf8") as f:
        f.write("\n".join(md))
    ET.ElementTree(suites).write(base + ".xml", encoding="utf-8", xml_declaration=True)
    return base


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target", choices=["android", "ios-sim", "ios"], nargs="?")
    ap.add_argument("--device")
    ap.add_argument("--only", default="")
    ap.add_argument("--no-network", action="store_true")
    ap.add_argument("--no-smoke", action="store_true")
    ap.add_argument("--no-launch", action="store_true")
    ap.add_argument("--timeout", type=float, default=900, help="seconds for the whole suite")
    ap.add_argument("--list", action="store_true", help="list the test names")
    args = ap.parse_args()
    if args.list:
        with open(SUITE, encoding="utf8") as f:
            print("\n".join(re.findall(r'^    \("([\w-]+)", t_', f.read(), re.M)))
        return 0
    if not args.target:
        ap.error("target required")
    target: Target = {"android": Android, "ios-sim": IosSim, "ios": Iphone}[args.target](args.device)
    expected = versions().get("ANKI_TAG", "")

    print(f"== {args.target}: {'relaunching Kioku' if not args.no_launch else 'using the running app'}")
    if not args.no_launch:
        target.launch()
    if not wait_ready(target, 180):
        print("!! Kioku's command channel doesn't answer: is a development build installed "
              "and the profile open?")
        return 2

    sections: dict[str, tuple[list[dict], str]] = {}
    print(f"== in-app tests (Anki {expected} expected)")
    only = [t for t in args.only.split(",") if t]
    sections["flows"] = run_suite(target, expected, only, not args.no_network, args.timeout)
    if sections["flows"][1]:
        print(f"!! {sections['flows'][1]}")
    if not args.no_smoke and target.alive():
        print("== crash sweep (every window)")
        sections["sweep"] = run_smoke(target, 300)
        for r in sections["sweep"][0]:
            if r["status"] != "pass":
                print(f"  FAIL  {r['test']}: {r['detail']}")
        ok = sum(r["status"] == "pass" for r in sections["sweep"][0])
        print(f"  {ok}/{len(sections['sweep'][0])} steps ok" + (f"; {sections['sweep'][1]}" if sections['sweep'][1] else ""))

    flows = sections["flows"][0]
    info = next((r["detail"] for r in flows if r["test"] == "version"), "")
    base = write_reports(args.target, sections, info)
    failed = [r for res, _ in sections.values() for r in res if r["status"] == "fail"]
    errors = [e for _, e in sections.values() if e]
    passed = sum(r["status"] == "pass" for res, _ in sections.values() for r in res)
    skipped = sum(r["status"] == "skip" for res, _ in sections.values() for r in res)
    print(f"== {passed} passed, {len(failed)} failed, {skipped} skipped"
          + (f", {len(errors)} run errors" if errors else ""))
    print(f"   report: {base}.md (JUnit: {base}.xml)")
    return 1 if failed or errors else 0


if __name__ == "__main__":
    sys.exit(main())
