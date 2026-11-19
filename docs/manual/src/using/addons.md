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

## Add-ons that other apps connect to (iPhone, iPad)

> **Applies to:** iPhone and iPad

Some add-ons answer requests from other apps. **AnkiConnect** is the best
known: dictionary and reader apps (Yomitan, Hoshi Reader and others) send it
new cards at `http://127.0.0.1:8765`.

iOS pauses an app a few seconds after you leave it, and a paused app
answers nothing. The other app then waits, or shows "can't connect" or a
spinner that never stops. On Android this doesn't happen.

To keep such add-ons answering, turn on **Preferences › Advanced ›
Background › Keep running in the background**:

1. Tick **Keep running in the background**, read the note and choose
   **Yes**.
2. iOS asks whether Kioku may use your location: choose **Allow While Using
   the App**, and leave **Precise** off (iOS's default for Kioku). Location
   is only the means, see below.
3. The group shows **On: Kioku keeps running in the background.** Now
   switch to the other app.

When Kioku goes to the background, iOS shows the location arrow at the top
of the screen; with approximate location it can disappear after a while,
and Kioku keeps running. It keeps running, with the screen locked too,
until you turn the option off or close Kioku from the app switcher.

**Why location?** iOS lets an app keep running in the background only for a
few purposes: playing audio, navigation, calls and a few others. Location
updates are the one that fits a server best; terminal apps such as Termius
use them to keep connections open the same way.

**Your location is not collected.** Kioku asks iOS for the lowest accuracy
it offers (about 3 km, from cell towers and Wi-Fi, without GPS) and ignores
what it receives: the location isn't read, saved, shown or sent anywhere.
See the [privacy policy](../privacy.md).

**Add-ons and location.** iOS gives location access to the whole app, and
add-ons are programs that run inside Kioku. Kioku protects your location
from them:

- Only Kioku's own location request works. When an add-on, or a web page
  in a card or add-on window, asks iOS for location access or for
  locations, it gets nothing, and no permission prompt appears.
- iOS gives Kioku **approximate** location (several kilometres) unless you
  turn **Precise** on in the Settings app. Leave it off: the option works
  without it.
- Kioku never asks for **Always** access, and add-ons can't ask for it.

An add-on written on purpose to get around these protections could still
read your approximate location while access is allowed, since it runs
inside Kioku. Install only add-ons you trust, as on a computer.

**Turning it off.** Untick the option and Kioku stops using location at
once. iOS keeps the permission until you take it back: the Settings app ›
**Apps** › **Kioku** › **Location** › **Never**. The group reminds you of
this while access is still allowed.

**Battery:** at this accuracy iOS uses no GPS and wakes Kioku rarely, but an
app that stays running uses more battery than a paused one, especially if
an add-on keeps working in the background. Turn the option off when you
don't need it.

If you chose **Don't Allow**, the group says that location access is off:
turn it on in the **Settings** app › **Apps** › **Kioku** › **Location** ›
**While Using the App**.

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
