"""Statically scan unpacked add-ons for what they need outside Kioku's bundle.

    python3 -I scan.py <addons dir> <names.json> <scan.json>

One folder per add-on (named by AnkiWeb id). Parses each add-on's own .py
files (vendored folders skipped) for imports, subprocess calls naming a known
program and runtime pip installs, and lists shipped native binaries. Nothing
is imported or run. names.json comes from names.py.
"""

import ast, json, os, re, sys
from collections import Counter

root, names_path, out = sys.argv[1:4]
names = json.load(open(names_path))
STD = set(sys.stdlib_module_names) | {"__future__", "_thread"}
PY2 = {"StringIO", "cStringIO", "urlparse", "urllib2", "Queue", "httplib", "cPickle", "htmlentitydefs", "HTMLParser", "ConfigParser", "UserDict", "UserList", "cookielib", "Cookie", "thread", "dummy_thread", "dummy_threading", "SocketServer", "BaseHTTPServer", "SimpleHTTPServer", "markupbase", "Tkinter", "sets", "commands", "__builtin__", "urllib", "exceptions", "copy_reg", "PyQt4", "sip"}
HOST = PY2 | {"aqt", "anki", "PyQt6", "PyQt5", "sip", "PyQt6.sip", "_aqt", "pkg_resources", "setuptools", "pip", "distutils"}
BUNDLED = {"bs4", "markdown", "orjson", "google", "requests", "decorator", "typing_extensions", "flask",
           "jsonschema", "packaging", "send2trash", "truststore", "waitress", "markupsafe", "jinja2",
           "werkzeug", "urllib3", "certifi", "idna", "charset_normalizer", "chardet", "soupsieve", "socks",
           "attrs", "click", "itsdangerous", "blinker", "fitz", "pymupdf", "referencing", "rpds", "asgiref",
           "sockshandler"}
NATIVE_EXT = (".so", ".pyd", ".dylib", ".dll", ".exe")
TOOLS = ["ffmpeg", "ffprobe", "mpv", "mplayer", "tesseract", "mecab", "kakasi", "lame", "sox", "espeak",
         "pdftoppm", "pdftotext", "java", "node", "git", "latex", "dvipng", "dvisvgm", "magick", "convert",
         "gs", "yt-dlp", "youtube-dl", "pandoc", "wkhtmltopdf", "osascript", "say", "xdg-open", "powershell",
         "curl", "wget", "aws", "gcloud", "edge-tts", "anki-sync-server"]
SPAWN = re.compile(r"\b(subprocess\.|Popen\(|os\.system\(|os\.popen\(|QProcess|check_output\(|run_process|call\(\[)")
PIP = re.compile(r"""(pip\.main|pip\._internal|['"]-m['"]\s*,\s*['"]pip['"]|['"]pip['"]\s*,\s*['"]install['"]|-m pip install)""")
TOOL_RE = re.compile(r"""['"/\\](%s)(\.exe)?['"\s]""" % "|".join(map(re.escape, TOOLS)))

# Repos (fetch_github.sh) also hold tests and build scripts, not add-on code.
DEV = {"tests", "test", "scripts", "tools", "docs", "build", "dist", ".github", "examples", "benchmarks"}
DEVFILE = re.compile(r"^(build\w*|setup|conftest|noxfile|tasks|make\w*|package\w*|release\w*|test_\w+|\w+_test)\.py$")

rows = []
missing_all = Counter()
for aid in sorted(os.listdir(root)):
    d = os.path.join(root, aid)
    if not os.path.isdir(d):
        continue
    local, natives, pyfiles = set(), [], []
    for dp, dns, fns in os.walk(d):
        for n in dns:
            local.add(n)
        for f in fns:
            if f.endswith(".py"):
                local.add(f[:-3]); pyfiles.append(os.path.join(dp, f))
            elif f.lower().endswith(NATIVE_EXT) or ".cpython-" in f or ".abi3." in f:
                natives.append(os.path.relpath(os.path.join(dp, f), d))
    VEND = {"lib", "libs", "vendor", "_vendor", "vendored", "third_party", "thirdparty", "site-packages", "dist-packages", "extern", "external", "deps", "packages", "modules"}
    perfile = {}
    spawn = pip = False
    tools = set()
    for p in pyfiles:
        try:
            src = open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        flags = (bool(SPAWN.search(src)), bool(PIP.search(src)), {m.group(1) for m in TOOL_RE.finditer(src)})
        try:
            tree = ast.parse(src)
        except Exception:
            perfile[p] = ({m.group(1) for m in re.finditer(r"^\s*(?:from|import)\s+([A-Za-z_]\w*)", src, re.M)}, set(), flags)
            continue
        imports, optional = set(), set()
        tried = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                for b in node.body:
                    for sub in ast.walk(b):
                        tried.add(id(sub))
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module.split(".")[0]]
            for m in mods:
                (optional if id(node) in tried else imports).add(m)
        perfile[p] = (imports, optional, flags)
    allimp = set().union(*(a for a, *_ in perfile.values())) if perfile else set()
    vend = (allimp & local) | VEND
    imports, optional = set(), set()
    for p, (a, o, f) in perfile.items():
        parts = os.path.relpath(p, d).split(os.sep)[:-1]
        name = os.path.basename(p)
        if any(x in vend or x in DEV or x.endswith(("-info", ".egg")) for x in parts) or DEVFILE.match(name):
            continue
        imports |= a; optional |= o
        spawn |= f[0]; pip |= f[1]; tools |= f[2]
    ext = lambda s: {m for m in s if m not in STD and m not in HOST and m not in BUNDLED and m not in local
                     and not m.isdigit() and not m.startswith("_")}
    req, opt = sorted(ext(imports)), sorted(ext(optional) - ext(imports))
    missing_all.update(req + opt)
    meta = names.get(aid, {})
    rows.append(dict(id=aid, title=meta.get("t", "?"), likes=meta.get("likes", 0), pv=meta.get("pv"),
                     natives=natives, req=req, opt=opt, spawn=spawn, pip=pip, tools=sorted(tools)))
json.dump(dict(rows=rows, missing=missing_all.most_common()), open(out, "w"))
print(len(rows), "addons")
print(missing_all.most_common(120))
