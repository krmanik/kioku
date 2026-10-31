# Changes

All releases: [GitHub Releases](https://github.com/krmanik/kioku/releases).

## 0.2.6

Add-ons that start programs, read PDFs or import native packages now work on
iOS and Android.

- The apps include FFmpeg, MeCab, KAKASI, Tesseract (English, Japanese,
  Chinese, Korean), eSpeak NG, LAME and cwebp, the programs add-ons such as
  Japanese Support, AJT Media Converter and OCR add-ons start. An add-on's
  own copy of one of them (made for Windows, macOS or Linux) is replaced by
  Kioku's.
- numpy, Pillow and cryptography for add-ons that import them.
- PDF add-ons such as Incremento: `PyQt6.QtPdf` and PyMuPDF 1.28 are built
  in, and add-ons' pdf.js readers can open local files (also Termux).
- Chinese word segmentation (jieba), code highlighting (Pygments),
  Tesseract's OCR languages and eSpeak NG's voices are not in the app. Kioku
  offers to download them when an add-on needs them, and
  **Tools › Add-ons › Extra Files…** downloads, updates and removes them.
  [Details](using/addons.md#extra-files-for-add-ons)
- Smaller app despite all this: about 215 MB installed on iPhone, a 94 MB
  APK on Android.
- On phone screens, add-on panels that open on the side go under the main
  view; several panels become tabs, and ▲ / ▼ expand a panel or split the
  screen again (also Termux).
- Syncing with AnkiWeb keeps going when you leave the app, with a
  notification while it runs. Leaving during the first download used to fail
  it with a network error and leave the deck list empty (Android).
- A sync error while switching profiles is now shown. It used to stay hidden
  and block the app until a restart (Android).
- HTTPS (sync, downloads) no longer fails after Android frees storage by
  clearing app caches (Android).
- Menus opened from a page (the review screen's **More**) show where you
  tapped and close on a tap outside them (iOS, Android).
- A hardware keyboard's Space and Return turn cards over after a tap on the
  card (iOS).
- Database writes from some add-ons no longer fail with "SQL statements in
  progress" (iOS).
- The first-run language list shows the selected row in dark mode (Android).

## Self-hosted server (Docker)

New: `ghcr.io/krmanik/kioku-desktop`, Anki desktop 26.09.3 on your server
or NAS, used from any browser. Your collection, media and add-ons stay on
the server; the browser only shows Anki's screen.
[Guide](install/self-hosted.md).

## 0.2.5

- Preferences › User interface size works (50–200%), and Preferences pages
  scroll instead of squeezing their rows (iOS, Android).
- No black flash when the keyboard opens in Add and Browse; the Add
  window's tags and buttons stay above the keyboard (Android).
- **Sync server on the phone** and **AnkiDroid's media** (Termux), like the
  native variants.
- Remote desktop: a custom screen size from 640 × 480 to 7680 × 4320, and
  its own interface size (Termux).
- Fixed a crash on a tap after a window or dialog closed (iOS).

## 0.2.4

- Add-on pages fit the phone screen; the deck list no longer flickers from
  desktop to phone layout (iOS, Android).
- Browse: add-on buttons next to the search box get their own row, and the
  sidebar edge is wider and easier to drag (iOS, Android).
- The progress window has a Cancel button and shows as a small card (iOS,
  Android).
- No more freezes at start or when opening Preferences or a menu while an
  accessibility service (a password manager, Switch Access) is on (Android).

## 0.2.3

Anki 26.09.3.

- **TestFlight** builds for iPhone and iPad ([sign up](https://forms.gle/fw4YMTdGbgD8nqPe8)).
- Full screen: swipe right to get **Exit Full Screen** (iOS, Android).
- Add-on side panels and pop-ups fit the phone; tooltips fit its width
  (iOS, Android).
- Anki's update prompt points to Kioku's releases.

## 0.2.2

Anki 26.08.1.

New:

- **Sync server on the phone** (iOS, Android, Preferences › Advanced): AnkiDroid,
  Kioku's profiles and Anki on your computers can sync with the phone instead
  of AnkiWeb. [Guide](features/sync-server.md).
- **AnkiDroid's media** (Android): a profile can use AnkiDroid's media folder, and
  syncs when you switch between the apps. [Guide](features/ankidroid.md).
- **Remote desktop** (Termux): use the phone's Anki from a computer's web browser
  or VNC viewer. [Guide](features/remote-desktop.md).
- **`{{tts}}` text-to-speech** with the phone's voices (iOS, Android).
- **Statistics › Save PDF** on iPhone (iOS).
- **Ogg/Opus card audio** on iPhone (iOS).
- The review screen's **Edit** and **More** are in the Edit menu (iOS, Android).

Fixed:

- Crash right after choosing the language on first start with VoiceOver or
  another accessibility feature on, and on iOS 18 (iOS).
- The keyboard's Enter key now submits Browse's search, prompts and the login
  (Android).
- Status and navigation bars disappeared after another app's popup, such as
  the "Open with" chooser (Android).
- Power off in the Termux desktop didn't end the session (Termux).

iOS = iPhone/iPad, Android = Android native, Termux = Android Termux.

## Earlier

See [GitHub Releases](https://github.com/krmanik/kioku/releases).
