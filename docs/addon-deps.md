# Add-on dependency sweep (2026-10-29)

Static scan of 2101 AnkiWeb add-ons: 1749 from the add-on dump and 352
fetched from their GitHub repos (add-ons missing from the dump that support
Anki 2.1.50+; a repo can differ from the AnkiWeb build, and a repo holding
several add-ons counts for each). Nothing was run: each add-on's own `.py` files were
parsed for imports, `subprocess`/`QProcess` calls with a known program name,
and runtime `pip install`; shipped `.so`/`.pyd`/`.dll`/`.dylib`/`.exe` files
were listed. Code in vendored folders (`lib/`, `vendor/`, packages the add-on
imports by name), tests and build scripts were skipped, as were Python 2 fallback imports. "Not
bundled" means outside Kioku's Python bundle (Anki's own dependencies plus
PyMuPDF). Imports inside `try` count, so some hits are optional features;
desktop APIs are usually behind a platform check.

What each need means here: pure-Python libraries can be bundled or vendored
on every variant. Native libraries need a cross-built wheel on iOS/Android
(like PyMuPDF); Termux can install many from its repositories. External
programs can't run on iOS at all, need a bundled binary on native Android,
and are a `pkg install` away on Termux. Modules removed from Python 3.13+
break on desktop Anki too.

## What the native apps bundle now

Added after this sweep, in both native apps (iOS and Android). Add-ons use
them as on the desktop: programs through `subprocess` by name or by the
add-on's own copy (`support/mecab.lin`, `cwebp.mac`, ...), which Kioku swaps
for its own; packages by `import`.

| | What | How |
| --- | --- | --- |
| Programs | ffmpeg, ffprobe (FFmpeg 9.0.2: lame, vorbis, opus, webp, x264, vpx, aom), lame, mecab, kakasi, tesseract (eng, jpn, jpn_vert, chi_sim, chi_tra, kor), espeak-ng / espeak, cwebp, dwebp | [shared/tools/build_programs.sh](../shared/tools/build_programs.sh), [shared/programs](../shared/programs), [kioku/programs.py](../shared/python/kioku/programs.py). Android: one executable; iOS: run inside the app on a thread of their own (iOS apps can't start processes) |
| Native packages | numpy, Pillow (JPEG, PNG, WebP, FreeType), cryptography with cffi and pyOpenSSL | [shared/tools/build_wheels.sh](../shared/tools/build_wheels.sh): iOS from BeeWare's and PyPI's iOS wheels, Android built with cibuildwheel |
| Pure Python | pygments, qtpy, tqdm, jieba | `shared/requirements.in`, `build_wheels.sh` (jieba) |
| Compatibility | `platform.system()` answers "Linux" (Android) / "Darwin" (iOS) to add-ons, as before Python 3.13; `pkgutil.find_loader()` is back (removed in 3.14, which the apps run; desktop Anki runs 3.13); `chmod` on iOS | [kioku/patches.py](../shared/python/kioku/patches.py), `programs.py` |

Not bundled, and why:

| Need | Add-ons | Why not |
| --- | --- | --- |
| mpv, mplayer | 27 | they open their own window or are driven over a socket; Anki's own playback already goes to the system player |
| osascript, node | 14 | macOS-only; Node.js is mostly build tooling in add-on repos |
| pdftotext | 4 | the add-ons that use it fall back to PyMuPDF or their own code, or call it with `shell=True` and a list (broken outside Windows) |
| sox | 4 | only in bundled copies of old Anki 2.0 code |
| scipy | 4 | needs a Fortran compiler for iOS/Android; Pomodium (66 likes), the main user, needs only `scipy.io.wavfile` |
| lxml, psutil | 4, 5 | optional in every add-on that imports them; neither builds for these platforms as it is |
| ntlm, importlib_metadata | 4, 3 | only imported by libraries add-ons bundle (urllib3, setuptools), or as fallbacks for Python < 3.8 |
| sentence_transformers, langchain | 3 | PyTorch / Rust-heavy, far too large |
| Windows/macOS/Linux desktop APIs | 31 | not on phones; usually behind a platform check |
| pip at runtime | 25 | the apps can't install native code at runtime |

Size: the APK grew from 70 to 142 MB, mostly the programs (43 MB:
three video encoders), jieba (37 MB of dictionaries), espeak-ng's and
Tesseract's data (19 + 18 MB) and numpy (18 MB).

Since then jieba, Tesseract's languages and eSpeak NG's data are downloaded
when an add-on needs them ("extra files": `shared/python/kioku/packs.json`,
`kioku/packs.py`; built and published by `shared/tools/packs.py` to the
repository's `packs` branch). To move more files out of the apps: add an
entry to packs.json (its `site` paths leave the bundles), run
`shared/tools/packs.py build` and `publish`. Only files: iOS loads no native
code from outside the app.

Tested through add-ons' own code in the apps (`shared/programs/test_addons.py`):
Japanese Support (mecab, kakasi), AJT Media Converter (cwebp, ffmpeg),
AnkiOCR's OCR (tesseract through pytesseract; its GUI imports PyQt5, which
fails on Qt 6 Anki anywhere). Results: [testing.md](testing.md).

## The sweep

Scripts: [shared/tools/addon_sweep](../shared/tools/addon_sweep) (`names.py`,
`fetch_github.sh`, `scan.py`, `classify.py`, `table.py`; usage at the top of
each).

Add-ons scanned: 2101. Nothing outside Kioku's bundle: 1863. Flagged: 238.

| Need | Add-ons |
|---|---|
| External program (subprocess) | 102 |
| Native library or shipped binaries | 54 |
| Pure-Python library not bundled | 79 |
| Windows/macOS/Linux desktop API | 31 |
| Module removed from Python 3.13+ | 14 |
| Another add-on | 21 |
| Runs pip at runtime | 25 |

Most wanted programs: ffmpeg 35, mpv 20, mecab 17, tesseract 9, osascript 8, mplayer 7, ffprobe 7, node 6, espeak 6, pdftotext 4, kakasi 4, lame 3.

Most wanted libraries: numpy 9, qtpy 9, PIL 8, cryptography 6, psutil 5, OpenSSL 5, lxml 4, ntlm 4, scipy 4, importlib_metadata 3, pygments 3, tqdm 3, sentence_transformers 2, BeautifulSoup 2, jieba 2.

<details>
<summary>Flagged add-ons (238, most liked first)</summary>

| Add-on | ID | Likes | Programs | Native libs | Pure libs | Desktop API | Removed stdlib | Other add-on | pip |
|---|---|---|---|---|---|---|---|---|---|
| Ankimon (by Unlucky-life and h0tp) | 1908235722 | 2264 |  |  |  | AppKit, Foundation, gi |  |  |  |
| 🧠 Synapse – The Ultimate Anki Workspace | 236979321 | 1045 | node | psutil |  |  |  |  |  |
| AnkiBrain (AnkiChatGPT) - GPT-5.6 with auto-cards  | 1915225457 | 545 | osascript | langchain |  |  |  |  |  |
| 🏆Anki Leaderboard - Compete with friends to boost  | 175794613 | 374 |  |  | googletrans |  |  |  |  |
| AnkiHub | 1322529746 | 315 |  | Crypto |  |  |  |  |  |
| Zzz AwesomeTTS (Google Cloud Text-to-Speech & Micr | 814349176 | 260 | espeak, lame, mplayer |  |  | pythoncom, win32com | cgi |  |  |
| Contanki - Controller Support for Anki (beta) | 1898790263 | 229 | osascript |  |  |  |  |  |  |
| 🤖Anki Terminator V2 - ChatGPT DeepSeek Sidebar for | 1468920185 | 223 |  |  |  |  | imghdr |  |  |
| Japanese Support | 3918629684 | 222 | kakasi, mecab |  |  |  |  |  |  |
| 🌐 AnkiCollab - A Free Collaboration Platform | 1957538407 | 220 |  |  | pygtrie |  |  |  |  |
| Migaku Japanese | 278530045 | 212 | kakasi, mecab |  | qtpy | AppKit, Foundation, gtk |  |  |  |
| Migaku Dictionary | 1655992655 | 183 | ffmpeg, java |  | qtpy | gi, gtk |  |  |  |
| Pop-up Dictionary (beta) | 153625306 | 181 |  |  |  |  |  | jsbooster |  |
| Multiple Choice for Anki | 1566095810 | 167 |  |  | pyparsing |  |  |  |  |
| Watch Foreign Language Movies with Anki | 939347702 | 149 | ffmpeg, ffprobe, mpv |  |  |  |  |  |  |
| Batch Download Pictures From Google Images | 561924305 | 134 | mpv | PIL |  |  |  |  |  |
| Progress Bar | 2091361802 | 130 |  |  |  |  |  | Night_Mode |  |
| 🎖️Anki Killstreaks - Reward Medals for Correct Ans | 1562475180 | 124 |  |  |  |  |  |  | yes |
| ⌛️Progress Bar for Anki - Visualize the Reviewed C | 1708250053 | 120 |  |  |  |  |  | Night_Mode |  |
| 🇯🇵 JapaneseFurigana | 678316993 | 118 | mecab |  |  |  |  |  |  |
| Migaku Editor | 1051095155 | 87 |  |  | qtpy | AppKit, Foundation, gtk |  |  |  |
| not maintained, don't use | 427598962 | 84 | espeak, lame, mplayer |  |  | pythoncom, win32com | cgi |  |  |
| Anki Habitica for 2.1 | 1758045507 | 77 |  |  |  | win32evtlog, win32evtlogutil |  |  |  |
| Anki Killstreaks | 579111794 | 76 |  |  |  |  |  |  | yes |
| Auto Ease Factor | 1672712021 | 72 |  |  |  | PySide2, PySimpleGUIQt |  |  |  |
| AJT Japanese - Furigana, Pitch Accent, Native pron | 1344485230 | 68 | mecab |  |  |  |  |  |  |
| Pomodium 🍅- The best pomodoro add-on for Anki | 678094152 | 66 |  | matplotlib, numpy, scipy |  |  |  |  |  |
| Chinese Support 3 | 1752008591 | 65 |  |  | yaspin |  |  |  |  |
| AJT Media Converter - WebP, AVIF, Opus 📹 | 1151815987 | 59 | ffmpeg |  |  |  |  |  |  |
| Migaku Anki Add-on | 1846879528 | 58 | ffmpeg, ffprobe |  |  |  |  |  |  |
| Create subs2srs cards with mpv video player | 1213145732 | 52 | ffmpeg, mpv |  |  |  |  |  |  |
| Cloze Overlapper for Anki 2.1 | 109531687 | 51 |  |  | BeautifulSoup |  |  |  |  |
| AnkiMorphs | 472573498 | 49 | mecab | spacy |  |  |  |  |  |
| Korean Support | 1336389630 | 45 |  |  | simplejson |  |  |  |  |
| 七牛云图床 - 学习骇客 | 928912796 | 45 |  |  |  |  |  |  | yes |
| AnkiOCR | 450181164 | 42 | tesseract |  | tqdm |  |  |  |  |
| VOICEVOX Japanese Text To Speech Audio Generator | 366960193 | 41 | ffmpeg |  |  |  |  |  |  |
| Syntax Highlighting (NG) | 566351439 | 41 |  |  | pygments |  |  |  |  |
| Migaku Kanji GOD | 1872210448 | 37 | mecab |  |  |  |  |  |  |
| AnkiFlash Flashcards Importer (Vietnamese, English | 1129289384 | 35 |  |  |  |  | cgi |  |  |
| Memory Forest: a forest that grows with your revie | 1255432496 | 34 | ffmpeg, node | PIL |  |  |  |  |  |
| Open linked pdf, docx, epub, audio/video, etc. in  | 879473266 | 34 | osascript |  |  |  |  |  |  |
| Progress Bar (original) | 1685464019 | 33 |  |  |  |  |  | Night_Mode |  |
| AnkiCraft | 368161874 | 32 |  |  |  |  |  |  | yes |
| 🤖PiperTTS for Anki - Fast local AI neural text to  | 428593773 | 31 | ffmpeg |  |  |  |  |  |  |
| Migaku Chinese | 498302176 | 30 |  |  | qtpy | AppKit, Foundation, gtk |  |  |  |
| Migaku Vacation | 605638174 | 30 |  |  | qtpy | AppKit, Foundation, gtk |  |  |  |
| 🔂AnkiRestart - Quick Anki Rebooter, for Customize  | 237169833 | 29 | ffmpeg | psutil |  |  |  |  |  |
| multiple choice with 12 options | 1573325751 | 27 |  |  | pyparsing |  |  |  |  |
| SimpleFurigana | 1444055400 | 24 | kakasi, mecab |  |  |  |  |  |  |
| OpenInExternalEditor,Rename,Duplicate for Image,Au | 1560623518 | 24 | osascript |  |  |  |  |  |  |
| Searching, PDF Reading & Note-Taking in Add Dialog | 572933442 | 23 |  | siacrs |  |  |  |  |  |
| Cambridge Dictionary | 1875288089 | 21 | ffmpeg |  |  |  |  |  |  |
| maobi - Chinese Hanzi Writing Quizzes in Anki v0 6 | 931477147 | 20 |  |  | maobi |  |  |  |  |
| 😄 KanjiEater's Smart Japanese Kindle Highlights | 1353504091 | 19 | mecab |  |  |  |  | japanese |  |
| Export deck to audio (Anki 2.1) | 2095022381 | 18 | ffmpeg, ffprobe | pyaudio, scipy, simpleaudio |  |  | audioop |  |  |
| 🌐Local Anki Server - Use self-hosted server with W | 49665391 | 17 | ffmpeg |  |  |  |  |  |  |
| 📸Anki OCR - Generate OCR text from images (Fixed b | 546383173 | 17 | tesseract |  | tqdm |  |  |  |  |
| Kanji Table | 1828617820 | 16 | ffmpeg |  |  |  |  |  |  |
| Export deck to HTML | 1897277426 | 16 | wkhtmltopdf |  |  |  |  |  |  |
| pasteOCR | 1746010116 | 15 | tesseract | numpy, pandas |  |  |  |  |  |
| Cloze Overlapper for 23.x+ | 1784155610 | 15 |  |  | BeautifulSoup |  |  |  |  |
| 🖼️Quick Images Downloader - Bulk download images G | 8280891 | 14 |  |  |  |  | imghdr |  |  |
| Preview Slideshow | 90397199 | 14 | mplayer | psutil |  | win32evtlog, win32evtlogutil |  |  |  |
| MeCab UniDic Japanese Dictionary | 13462835 | 13 | mecab |  |  |  |  |  |  |
| Grade Echo - XXHK | 16493485 | 13 |  |  |  |  |  | revlog |  |
| Accurate progress bar (mizmu addons) | 1935872040 | 12 |  |  |  |  |  | Night_Mode |  |
| Zzz (legacy) No Sound Fix (libmpv) | 1586469444 | 11 |  | PIL |  |  |  |  |  |
| Yomisama (Japanese/Chinese) | 907186589 | 11 | ffmpeg, mecab, mplayer |  | pattern |  | cgi |  |  |
| Send Audio Clips From Audacity To Addcards/Ankidac | 1326170847 | 10 | ffmpeg |  |  |  |  |  |  |
| AI Language Explainer | 375742312 | 10 |  |  |  |  |  |  | yes |
| Youtube to Anki | 964531817 | 10 | ffmpeg |  |  |  |  |  |  |
| 📖 - Incremento (anki incremental reading/learning  | 1013949798 | 9 | ffmpeg, pdftotext, tesseract |  |  |  |  |  |  |
| 🟨 Sticky Notes for Anki - Create Beautiful Stickie | 2073533957 | 9 | latex |  | latex2mathml, pygments, test_markdown2, wavedrom |  |  |  |  |
| Anki Live: GAME CHANGER add-on | 438250708 | 9 | mpv |  |  | pywintypes, win32file, win32pipe, winerror |  |  |  |
| Anki Word Frequency | 110659003 | 8 |  | MeCab | ipadic, jieba, mecab_ko_dic |  |  |  |  |
| Export Card to Audio | 1117983796 | 8 | ffmpeg |  |  |  |  |  |  |
| KanjiVocab - smart automatic vocab for RTK | 1600796261 | 8 | mecab |  |  |  |  | japanese |  |
| 😄KanjiEater's GoldenDict Japanese Toolbelt | 247820692 | 8 |  |  |  | win32api, win32con |  |  |  |
| Anki-Coder | 1543399508 | 7 |  | ships 12 binaries |  |  |  |  |  |
| Anki PDF Connector, Links and Note (Editor and Rev | 16097657 | 7 |  |  |  |  |  |  | yes |
| ⏩Preview Slideshow (Fixed by Shigeඞ) | 1621302762 | 7 | mplayer | psutil |  | win32evtlog, win32evtlogutil |  |  |  |
| AnkiFuzzy - Identifying Identical, Similar and Rep | 1665515487 | 7 |  | Levenshtein |  |  |  |  |  |
| Study.io - See your most-missed tags, works great  | 720874373 | 7 |  |  | module |  |  |  |  |
| FrequencyMan - 🔺 Sort your new cards i+1 🔻 | 909420026 | 7 | mecab |  |  |  |  |  |  |
| ZIM Reader - Look up words in Wiktionary | 951350249 | 7 |  |  | libzim |  |  |  |  |
| WaniKani Sync | 391275087 | 6 |  | brotli, brotlicffi |  |  |  |  |  |
| pomodoro番茄钟/deepseek/Gemini智能分析学习情况/每日计划/每日打卡/倒计时/ | 547148424 | 6 |  |  |  |  |  |  | yes |
| Power - Check your battery from your Anki menu (by | 643961895 | 6 |  | ships 19 binaries |  |  |  |  |  |
| Hanzi2Pinyin | 77106192 | 6 |  |  | tomli |  |  |  |  |
| Batch Download Pictures From Baidu Images | 1024335436 | 5 | mpv | PIL |  |  |  |  |  |
| EPUB READER PLUS AI | 1098514784 | 5 |  | lxml | aiofiles |  |  |  |  |
| PDF to notes | 1250587448 | 5 | pdftoppm, pdftotext |  |  |  |  |  |  |
| Auto Image Occlusion | 1414192727 | 5 | tesseract |  |  |  |  |  |  |
| 📸PasteOCR - Paste image as text (Fixed by Shigeඞ) | 1808435406 | 5 | tesseract | numpy, pandas |  |  |  |  |  |
| Reveal in File Manager | 545706530 | 5 | osascript |  |  |  |  |  |  |
| Inline media | 683715045 | 5 | ffmpeg |  |  |  |  |  |  |
| Notes2Flash - AI tool to organize GoogleDocs Notio | 868678030 | 5 |  |  |  |  |  |  | yes |
| Mindmap - Visual Learning & Card Linking | 905917130 | 5 | node |  |  |  |  |  |  |
| OGG To MP3 Converter - Updated Version | 1603562177 | 4 | ffmpeg |  |  |  |  |  |  |
| Internal References | 323026909 | 4 |  |  | advanced_previewer |  |  | jsbooster |  |
| Anki Dojo | 433778282 | 4 | mecab |  | flask_cors |  |  |  |  |
| Migaku German | 768963681 | 4 |  | OpenSSL, cryptography | ntlm, qtpy | AppKit, Foundation, gtk |  |  |  |
| PDF Occlusion | 783821131 | 4 | osascript |  | pypdfium2 |  |  |  |  |
| Context Helper (语境学习法) | 823803971 | 4 | ffmpeg | numpy |  |  |  |  |  |
| Example Sentences - Japanese | 1290983049 | 3 | mecab |  |  |  |  |  |  |
| AnkivnTTS - FreeTTS by Vietnamese | 1388060198 | 3 |  | ships 142 binaries |  |  |  |  |  |
| Batch Edit Tools | 1609139780 | 3 |  | cElementTree, lxml | defusedxml |  |  |  |  |
| Show HTML fields of a note | 1778098423 | 3 |  |  |  |  | cgi |  |  |
| Anki Semantic Search | 751846187 | 3 |  | numpy | anthropic, colorama, sentence_transformers, spellchecker, torch |  |  |  | yes |
| Hanzi Table | 768679940 | 3 | ffmpeg |  |  |  |  |  |  |
| Minimalistic Pomodoro Timer | 928234906 | 3 |  | ships 14 binaries |  |  |  |  |  |
| OGG To MP3 media converter | 984498916 | 3 | ffmpeg |  |  |  |  |  |  |
| Pangolin Anki TTS / ✨Free✨ - Text-To-Speech - Narr | 1216029285 | 2 |  |  |  | pythoncom, win32com |  |  |  |
| Speech to text Windows | 1239768349 | 2 |  |  |  | win32com |  |  |  |
| 📥PDF to notes (Fixed by Shigeඞ) | 1660513597 | 2 | pdftoppm, pdftotext |  |  |  |  |  |  |
| 📊Auto Ease Factor (Fixed by Shigeඞ) | 179120908 | 2 |  |  |  | PySide2, PySimpleGUIQt |  |  |  |
| AI 学习助手 - 国内可用的 AI 学习助手 | 1968029185 | 2 | pdftotext |  |  |  |  |  |  |
| Sub FFmpeg Cards Cutter (Divisor de Midia Avançado | 1983257427 | 2 | ffmpeg, ffprobe |  | six |  |  |  |  |
| Ultimate Add-on for template (Multiple-Choice, Tex | 1988684072 | 2 |  |  | anki_ultimate |  |  |  |  |
| History Recorder | 2039239436 | 2 | mpv |  |  |  |  |  |  |
| Audio File Speed Control | 225211451 | 2 | ffmpeg |  |  |  |  |  |  |
| Sync Learned to TickTick | 240836168 | 2 |  |  | dotenv |  |  |  |  |
| Learn2Rot | 317517318 | 2 | osascript |  | pymunk, pystray, rumps, winrt |  |  |  | yes |
| Hands-Free Voice Review | 361564241 | 2 |  |  | sounddevice, vosk |  |  |  |  |
| 💾History Recorder - word cloud and statistics  (Fi | 510715849 | 2 | mpv |  |  |  |  |  |  |
| Custom Toolbar Buttons v2 | 583648253 | 2 |  | ships 2 binaries |  |  |  |  |  |
| AnkiExam | 654715453 | 2 |  | cryptography | pypdf |  |  |  |  |
| AirPods: fix audio dropouts (macOS) | 676963607 | 2 | mpv |  |  |  |  |  |  |
| 🍣KanjiVocab - smart automatic vocab for RTK (Fixed | 887572166 | 2 | mecab |  |  |  |  | japanese |  |
| Adjust Review Times (Timezone) | 928551535 | 2 |  |  | backports, pytz |  |  |  |  |
| AttendingAI | 1014280579 | 1 | tesseract | PIL, numpy, ships 10 binaries | cairosvg, reportlab, sentence_transformers, svglib |  |  |  |  |
| Youtube's Video to SRS Deck | 1023383878 | 1 | ffmpeg |  |  |  |  |  |  |
| Anki Ai Automation | 1186735228 | 1 |  |  | openai |  |  |  |  |
| Adaptive Retention Scheduler for FSRS (Deprecated) | 1202210378 | 1 |  |  | knowledge_ema |  |  |  |  |
| Migaku Spanish | 1233908746 | 1 |  | OpenSSL, cryptography | ntlm, qtpy | AppKit, Foundation, gtk |  |  |  |
| LilyPond Integration (Sheet Music Typesetter) for  | 123418104 | 1 |  |  |  |  | cgi |  |  |
| All your due cards in one deck | 1393821859 | 1 | mpv |  |  |  |  |  |  |
| Anki Card Viewer | 1454059008 | 1 |  |  |  |  |  |  | yes |
| Auto-Recolor | 147600983 | 1 |  |  |  |  |  |  | yes |
| Pykaudio Background Audio Player | 1546179770 | 1 |  |  |  | AppKit, Foundation, gi |  |  |  |
| Audio Converter - Convert audio in your Anki cards | 1555675372 | 1 | ffmpeg |  |  |  |  |  |  |
| Language Keyboard Auto-switch | 1606509029 | 1 |  |  |  | win32api, win32gui |  |  |  |
| MathMemo - Learn Proofs and theorems with Anki, im | 1675265203 | 1 | latex |  |  |  |  |  |  |
| Binge-Studying (Watch anything and get used to "no | 1716968608 | 1 | espeak, ffprobe, mpv |  |  |  |  |  |  |
| Transcribe Own Voice | 1719356135 | 1 |  |  |  |  |  | asr |  |
| Migaku Portuguese | 1786818696 | 1 |  | OpenSSL, cryptography | ntlm, qtpy | AppKit, Foundation, gtk |  |  |  |
| Randomized Image Occlusion | 1836497069 | 1 | node |  |  |  |  |  |  |
| ankimorphs-japanese-mecab | 1974309724 | 1 | kakasi, mecab |  |  |  |  |  |  |
| AnkiVec | 2028823832 | 1 |  |  | chromadb, ollama, onnxruntime |  |  |  |  |
| Paste Wikipedia and MathJax math formulae into Ank | 30765645 | 1 |  | lxml |  |  |  |  |  |
| TRMNL Anki | 415381283 | 1 |  | ships 1 binaries | pytz |  |  |  |  |
| Lier les Cartes (Anki EDN) | 445658251 | 1 |  |  | Anki_EDN_Lier_les_cartes |  |  |  |  |
| AINotePro: AI Text and Audio for Anki | 468889502 | 1 |  | ships 10 binaries |  |  |  |  |  |
| Obsidianki 4: Move Your Obsidian Vault into Anki | 620260832 | 1 |  |  | pygments, test_markdown2 |  |  |  |  |
| Zzz (legacy) Video Fix 2 | 100620900 | 0 | mpv |  |  |  |  |  |  |
| Zzz (legacy) Video Fix 1 | 1006287781 | 0 | mpv |  |  |  |  |  |  |
| update | 1031727192 | 0 |  |  |  |  |  | utd_anki_addon |  |
| Export Anki cards as picture | 1047004318 | 0 | magick |  |  |  |  |  |  |
| Generate Audio | 1056834290 | 0 | ffmpeg |  |  |  |  |  |  |
| anki uptodate | 1058181944 | 0 |  |  |  |  |  | utd_anki_addon |  |
| Swedish-English Card Filler | 1069915013 | 0 |  |  | defusedexpat |  |  |  |  |
| LilyPond (sheet music typesetting) integration | 1080109152 | 0 |  |  |  |  | cgi |  |  |
| Balanced Audio Controller – Speed, Volume & Loudne | 1090755758 | 0 | ffmpeg |  |  |  |  |  |  |
| ? | 1097423555 | 0 |  |  |  |  |  | Night_Mode |  |
| AnKing Images | 110824396 | 0 |  | ships 15 binaries |  |  |  |  |  |
| Karo Magic Again Sorter - Auto-organize cards by f | 1122269011 | 0 |  | ships 1 binaries |  |  |  |  |  |
| ? | 1146841074 | 0 |  | xcffib |  |  |  |  |  |
| Anki MPV Shortcuts✅ | 1181799219 | 0 | mpv |  |  |  |  |  |  |
| Sentence Translator – Translate and Create Cards | 1182420013 | 0 |  | ships 125 binaries |  |  |  |  |  |
| Preview Slideshow (Shigeyuki) - mod kaiu 2026 | 1188253433 | 0 | mplayer | psutil | PyQ5 | win32evtlog, win32evtlogutil |  |  |  |
| mp4-2-gif | 122137380 | 0 | ffmpeg, ffprobe, graphviz |  |  |  |  |  |  |
| rudict - Russian dictionary popup for Anki | 1227408997 | 0 |  |  | pymorphy3 |  |  |  | yes |
| ? | 1320954270 | 0 |  |  |  |  | audioop |  |  |
| Memo Flashcards | 1347191746 | 0 |  |  | dotenv |  |  |  |  |
| Idly-media-pause | 1466024936 | 0 | mpv |  |  |  |  |  |  |
| Chat with Card | 1466614056 | 0 |  |  |  |  |  |  | yes |
| kind2anki (New) - import words from Kindle Vocabul | 1476714888 | 0 |  |  |  |  |  |  | yes |
| LangU | 149544380 | 0 |  |  |  |  |  | langu |  |
| Animated Graphs | 1501397084 | 0 |  | matplotlib |  |  |  |  | yes |
| TesseractOCR | 1509163599 | 0 | tesseract | PIL |  | pyautogui |  |  |  |
| WhipFlash - AI Flashcard Generator & Study Tracker | 1549373528 | 0 |  |  | PyPDF2, playwright |  |  |  | yes |
| Thai Reading Add-on | 1603467171 | 0 |  |  | thaiphon, thaiphon_data_volubilis |  |  |  |  |
| MDX批量查词与导出 | 1616953407 | 0 |  |  | tkFileDialog |  |  |  |  |
| 🎬️FFmpeg Downloader for Anki (Create by Shigeඞ) | 1652323034 | 0 | ffmpeg |  |  |  |  |  |  |
| up to date | 1658165800 | 0 |  |  |  |  |  | utd_anki_addon |  |
| UpToDate | 1662702269 | 0 |  |  |  |  |  | utd_anki_addon |  |
| Anki EDN Stats | 1674438508 | 0 |  |  | Anki_EDN_Spotlight_Background |  |  |  |  |
| Card Stats in Editor | 1690626281 | 0 |  |  | qtawesome |  |  |  |  |
| ? | 1693442640 | 0 |  | cv2, easyocr |  |  |  |  | yes |
| ? | 1695607349 | 0 |  |  |  |  |  | Night_Mode |  |
| CardCast: MP3 Audio Generator for Commuting | 1697388828 | 0 | ffmpeg | ships 1 binaries |  |  |  |  |  |
| Anki TTS - Auto Text-to-Speech for Reviews | 170636394 | 0 | edge-tts, espeak, mpv |  | edge_tts |  |  |  |  |
| ankis up to date | 1718266469 | 0 |  |  |  |  |  | utd_anki_addon |  |
| Export deck to both audio and html | 1735239174 | 0 | ffmpeg, ffprobe, wkhtmltopdf | pyaudio, scipy, simpleaudio |  |  | audioop |  |  |
| Video Import As A Deck | 1779953895 | 0 |  |  | importlib_metadata |  |  |  |  |
| Movie Import with Subtitles to Learning | 1840722307 | 0 |  |  | importlib_metadata |  |  |  |  |
| Auto Translator (Google Translate) | 1855534469 | 0 |  |  | google_trans |  |  |  |  |
| clipboard_field_copy_need_to_work | 1856231912 | 0 |  |  |  | win32clipboard |  |  |  |
| ? | 1919894971 | 0 |  | lxml, numpy, scipy, sklearn |  |  |  |  |  |
| utd | 1926077229 | 0 |  |  |  |  |  | utd_anki_addon |  |
| Memozu - Autogenerate your Chinese Cards | 1969684823 | 0 | java, node | OpenSSL, brotli, brotlicffi, cryptography, cx_Oracle, mysql, numpy, paddle, psycopg2 | Dialog, FileDialog, ScrolledText, SimpleDialog, Tix, Tkconstants, Tkdnd, future, h2, hanzidentifier, jieba, libfuturize, libpasteurize, mock, past, pinyin, pinyin_jyutping, pysqlcipher, pysqlcipher3, pysqlite2, simplejson, sqla_plugin_base, sqlalchemy, tkColorChooser, tkCommonDialog, tkFileDialog, tkFont, tkMessageBox, treelib, ttk, whoosh, xdist, xmlrpclib, zhon, zstandard | com | imghdr, imp, lib2to3, sndhdr, uu | chin_dict | yes |
| Anki All Stars Auto Updater | 2013989921 | 0 |  |  | dulwich |  |  |  |  |
| Anki-Con - Control Anki With Joy-Cons 🎮 | 2094090771 | 0 |  |  | hid |  |  |  |  |
| Dragon Mapper | 237254603 | 0 |  |  | dragonmapper |  |  |  |  |
| Migaku French | 262508408 | 0 |  | OpenSSL, cryptography | ntlm, qtpy | AppKit, Foundation, gtk |  |  |  |
| Anki Language Sentence Miner | 267473329 | 0 |  |  |  |  |  |  | yes |
| ogg2mp3 - convert ogg audio to mp3 on sync (iOS-sa | 282618623 | 0 | ffmpeg |  |  |  |  |  |  |
| Anki Remote Driver | 306050281 | 0 |  |  | hid |  |  |  |  |
| Ankisstant | 351752439 | 0 |  |  | practice_questions |  |  |  |  |
| Relocate Existing Cards on Import | 413327949 | 0 |  | ships 8 binaries |  |  |  |  |  |
| MyVoiceCards | 437468286 | 0 |  |  |  |  |  |  | yes |
| Enhanced Typebox - Improved Multi-line Input for C | 441175204 | 0 |  |  | cssutils, tinycss |  |  |  |  |
| Importar PDF para Anki - Beta | 494997960 | 0 | osascript, tesseract | PIL, cv2, numpy | gtts, pdfplumber |  |  |  | yes |
| Voice Review: Hands-free reviewing graded by AI | 499865194 | 0 |  |  | vosk | pythoncom, win32com |  |  |  |
| Media Import and View with external Window | 51127796 | 0 |  |  | System, importlib_metadata, md5 |  |  |  |  |
| Google Image Batch Downloader for Anki | 511921711 | 0 | mpv | PIL |  |  |  |  |  |
| Anki² Autofill fields with images, audio, and AI s | 517882364 | 0 |  |  | ankisquared |  |  |  |  |
| pyop | 525125636 | 0 |  |  | pyop |  |  |  |  |
| Notatki text notes importer addon for Anki | 541850746 | 0 |  |  | markdownify, mistune |  |  |  |  |
| Awesome2.1-Masoud | 544358717 | 0 | espeak, lame, mplayer |  |  | pythoncom, win32com |  |  |  |
| Speak button in Review (Falar botão na Revisão) | 571257863 | 0 | mpv |  |  |  |  |  |  |
| TTS - Get text localStorage.getItem and read by sp | 599889568 | 0 |  |  |  | win32clipboard, win32com |  |  |  |
| add-on that enables you to create cards from engli | 657359787 | 0 |  | spacy |  |  |  |  |  |
| Yukogurafu (有向グラフ): directed graphs of knowledge f | 665790891 | 0 | graphviz |  |  |  |  |  |  |
| Tsunagi - Modern API access to Anki | 666370974 | 0 |  | ships 2 binaries |  |  |  |  |  |
| MangAnki - a helper for online manga vocabulary mi | 67466478 | 0 |  |  |  | AppKit, Foundation, gi |  |  |  |
| Linux TTS player for native {{tts}} tags | 704375187 | 0 | espeak, mpv |  |  |  |  |  |  |
| Taiwanese Taigi 台語 Helper - Auto fill Tâi-Lô roman | 706708885 | 0 | mpv |  | genanki, tqdm |  |  |  |  |
| 🗣️ Offline TTS powered by Chatterbox | 749820458 | 0 |  |  | chatterbox, torch, torchaudio |  |  |  |  |
| Greek flashcard generator | 754137745 | 0 |  |  | llama_cpp |  |  |  | yes |
| reacttest | 757521341 | 0 | node |  |  |  |  |  |  |
| Buscador no Editor (Searcher) | 81493138 | 0 |  |  | cloudscraper, curl_cffi |  |  |  | yes |
| Zettel Join | 822767335 | 0 |  |  | emojis, pymdownx |  |  |  | yes |
| ? | 828860704 | 0 |  |  |  |  | imp |  |  |
| Create subs2srs cards with mpv + interactive subs | 832294226 | 0 | ffmpeg, mpv |  |  |  |  |  |  |
| ? | 93614872 | 0 | mecab |  |  |  |  |  |  |
| wiktionaryCopy | 949530966 | 0 |  |  | wiktionarycopy |  |  |  |  |

</details>
