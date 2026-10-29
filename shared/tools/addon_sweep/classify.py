"""Sort scan.py's findings into needs (program, native, pure, desktop API, ...).

    python3 -I classify.py <scan.json> <classified.json>
"""

import json, sys
from collections import Counter
d = json.load(open(sys.argv[1]))
NATIVE = set("numpy OpenSSL cryptography PIL lxml scipy psutil matplotlib pandas pyaudio simpleaudio brotli brotlicffi spacy MeCab Levenshtein cv2 easyocr sklearn paddle psycopg2 pyjson5 Crypto siacrs magic langchain cElementTree xcffib mysql cx_Oracle".split())
TOOLMOD = {"pydub": "ffmpeg", "imageio_ffmpeg": "ffmpeg", "pytesseract": "tesseract", "graphviz": "graphviz", "easyocr": None}
OSONLY = set("AppKit Foundation gtk gi win32com pythoncom win32evtlog win32evtlogutil win32api win32clipboard win32gui win32con win32file win32pipe winerror pywintypes pyautogui pyperclip PySide2 PySimpleGUIQt com".split())
REMOVED = set("cgi audioop imghdr imp sndhdr uu lib2to3 asynchat asyncore smtpd telnetlib nntplib crypt pipes msilib".split())
ADDON = set("utd_anki_addon Night_Mode japanese crowd_anki multiple_choice jsbooster revlog chin_dict langu asr".split())
IGNORE = set("pytest test unittest2 java js pyodide attr nose".split()) | set("Sybase adodbapi anydbm cdecimal dumbdbm gdbm whichdb repr robotparser UserString mx pgdb postgresql CGIHTTPServer future_builtins elementtree".split())
REAL_TOOLS = {"ffmpeg", "ffprobe", "mpv", "mplayer", "tesseract", "mecab", "kakasi", "lame", "sox", "espeak", "pdftoppm", "pdftotext", "latex", "dvipng", "dvisvgm", "magick", "yt-dlp", "youtube-dl", "pandoc", "wkhtmltopdf", "osascript", "edge-tts", "java", "node"}
out = []
for r in d["rows"]:
    mods = set(r["req"]) | set(r["opt"])
    c = {}
    nat = sorted(m for m in mods if m in NATIVE)
    if r["natives"]: nat.append("ships %d binaries" % len(r["natives"]))
    tools = sorted({t for t in r["tools"] if t in REAL_TOOLS} if r["spawn"] else set()) + sorted({TOOLMOD[m] for m in mods if TOOLMOD.get(m)})
    pure = sorted(mods - NATIVE - OSONLY - REMOVED - ADDON - IGNORE - set(TOOLMOD))
    for k, v in (("native", nat), ("tool", sorted(set(tools))), ("pure", pure), ("os", sorted(mods & OSONLY)),
                 ("removed", sorted(mods & REMOVED)), ("addon", sorted(mods & ADDON))):
        if v: c[k] = v
    if r["pip"]: c["pip"] = True
    out.append(dict(r, c=c))
cnt = Counter(k for r in out for k in r["c"])
print("total", len(out), "clean", sum(not r["c"] for r in out), dict(cnt))
json.dump(out, open(sys.argv[2], "w"))
for r in sorted(out, key=lambda r: -r["likes"]):
    if r["c"]: print(r["id"], r["likes"], r["title"][:45], json.dumps(r["c"]))
