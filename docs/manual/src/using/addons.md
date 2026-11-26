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

## For add-on developers: windows on a phone

> **Applies to:** iPhone/iPad, Android native

Phones have no window manager, so Kioku shows every window except Anki's
main window full screen, with a title bar (**‹ Back** and the window's
title). Small dialogs show as a card in the middle of the screen. Kioku
keeps windows clear of the status bar, the notch and the home indicator
or gesture bar.

An add-on with its own touch layout can opt out, one window at a time,
with Qt properties. Set them before or after the window is shown. They do
nothing on Anki desktop or on Termux.

```python
window.setProperty("kioku_hide_titlebar", True)  # no title bar
window.setProperty("kioku_edge_to_edge", True)   # reach the screen's edges
```

- **`kioku_hide_titlebar`**: no title bar. Give the window its own way
  back (Android's Back still closes it).
- **`kioku_edge_to_edge`**: the window reaches under the status bar, the
  home indicator and, in landscape, the notch. Pad your contents by the
  safe area:
  - in web views, with the CSS properties `--kioku-safe-top`,
    `--kioku-safe-right`, `--kioku-safe-bottom` and `--kioku-safe-left`
    on `<html>`. They follow a rotation.

    ```css
    body {
      padding: var(--kioku-safe-top, 0) var(--kioku-safe-right, 0)
               var(--kioku-safe-bottom, 0) var(--kioku-safe-left, 0);
    }
    ```
  - in Qt widgets, with `kioku.windows.safe_area(window)` (a `QMargins`).
    Read it again when the window is resized.

  While the title bar is shown, the window starts below it and the top
  inset is 0. The values are 0 for windows that aren't edge to edge.

Anki's menu row (File, Edit, View…) can be hidden while your add-on needs
the room, and given back:

```python
aqt.mw.setProperty("kioku_hide_menu_row", True)   # hide
aqt.mw.setProperty("kioku_hide_menu_row", None)   # back to normal
```

Its shortcuts keep working. On an iPad with iPadOS 26 or later, the menus
stay in the iPad's menu bar. On a phone they are out of reach until you
give the row back.

To check that you're running in Kioku:
`sys.platform in ("ios", "android")`.

## A broken add-on

If an add-on keeps Kioku from starting, start in **safe mode**: Anki
without add-ons (and without syncing automatically). Then turn the add-on
off in **Tools › Add-ons** and start Kioku again.

- **iPhone, iPad, Android (native):** touch and hold Kioku's icon and
  choose **Start in Safe Mode**. If Kioku closed while starting the last
  time, it also asks on the next start: **Start Without Add-ons** or
  **Start Normally**. The log of that start is kept as
  `kioku-previous.log` in Kioku's files.
- **Web:** open the address with `?safe=1` at the end, or use the
  **Start without add-ons** link on the loading page.
- **Termux:** use **Safe mode** on the error screen.

In safe mode the deck list says so. Tap **What now?** there for the way
to Tools › Add-ons. Add-ons load again the next time Kioku starts: close it
in the app switcher (iPhone, iPad) or Recents (Android) and open it again,
or reload the page (web).

If Kioku is already running, **Start in Safe Mode** offers to close it.
Open it again to start in safe mode.

Report add-ons that work or don't on
[GitHub](https://github.com/krmanik/kioku/issues).
