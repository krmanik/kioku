# Add-ons

> **Applies to:** iPhone/iPad, Android native, Android Termux

Kioku runs Anki desktop's add-ons. Install them as on a computer: **Tools ›
Add-ons › Get Add-ons…**, enter the add-on's code from
[AnkiWeb](https://ankiweb.net/shared/addons), and restart Kioku. See
[Anki: Add-ons](https://docs.ankiweb.net/addons.html).

`.ankiaddon` files can be installed with **Install from file…** in the same
window.

## What works

On the native apps (iPhone, Android) add-ons work unless they need one of:

- **starting another program** (iOS forbids it; on Android there is nothing
  to start). Example: MeCab readings in Japanese Support.
- **Qt WebEngine** features, such as AnkiWebView Inspector. Use Safari's Web
  Inspector or `chrome://inspect` instead.
- **Native libraries** built for Windows, macOS or Linux PCs.

On the Termux variant, add-ons behave as on Linux.

## Extra files for add-ons

> **Applies to:** iPhone/iPad, Android native

To keep the app small, some files that only a few add-ons use aren't part
of the app. Kioku downloads them when an add-on needs them:

| Extra files | Size | For add-ons that |
| --- | --- | --- |
| Chinese word segmentation (jieba) | 5 MB | split Chinese text into words |
| Code highlighting (Pygments) | 1 MB | color source code |
| Text recognition languages (Tesseract) | 10 MB | read text from images (OCR) |
| Speech voices (eSpeak NG) | 9 MB | speak with eSpeak |

- When you install an add-on that needs some, or start Kioku with one
  installed, Kioku asks whether to download them. Downloading runs in the
  background: keep using Kioku. If an add-on that loaded before the
  download still can't find them, restart Kioku.
- **Tools › Add-ons › Extra Files…** lists them: select an add-on first to
  see what it needs. Download, update or remove them there; removing frees
  the space until an add-on needs them again.
- If you choose **Not now**, Kioku doesn't ask again at start-up. It asks
  again when you install an add-on that needs them.

The files come from the [Kioku repository on GitHub](https://github.com/krmanik/kioku/tree/packs).

## Tested

All load on iPhone and Android:

| Add-on | Code | Result |
| --- | --- | --- |
| AnkiConnect | 2055492159 | works (HTTP API on 127.0.0.1:8765) |
| Review Heatmap | 1771074083 | works; slightly wider than a phone screen |
| Anki Simulator | 817108664 | opens |
| AnKing Note Types Easy Customization | 952691989 | works |
| Advanced Browser | 874215009 | loads |
| Fill the blanks | 1933645497 | loads |
| Colorful Tags / Hierarchical Tags | 594329229 | works |
| Customize Keyboard Shortcuts | 24411424 | loads |
| Edit Field During Review Cloze | 385888438 | works |
| Speed Focus Mode | 1046608507 | loads |
| True Retention | 613684242 | works |
| HyperTTS | 111623432 | works on Android |
| Color Confirmation | 1084228676 | works |
| Japanese Support | 3918629684 | Kanji Stats works; MeCab readings don't |
| AnkiWebView Inspector | 31746032 | doesn't work (needs Qt WebEngine) |

Full results: [docs/testing.md](https://github.com/krmanik/kioku/blob/main/docs/testing.md).

## A broken add-on

If Kioku fails at start-up after installing an add-on:

- **Termux:** use **Safe mode** on the error screen, then remove the add-on.
- **iPhone, iPad:** delete the add-on's folder in Files › Kioku ›
  `Anki2/addons21/` (Tools › Add-ons shows each add-on's folder name).
- **Android, native:** if Kioku still opens, disable the add-on in Tools ›
  Add-ons. Otherwise open an issue on
  [GitHub](https://github.com/krmanik/kioku/issues): reinstalling keeps the
  add-on.

Report add-ons that work or don't on
[GitHub](https://github.com/krmanik/kioku/issues).
