# Changes

All releases: [GitHub Releases](https://github.com/krmanik/kioku/releases).

## Next release

- Termux app: Anki starts again inside the desktop. 0.2.9 left out a file
  Preferences › Advanced needs, so the desktop came up without Anki
  ([issue #13](https://github.com/krmanik/kioku/issues/13)). The Termux
  app no longer shows the Gamepad settings: its desktop gets no
  controller input.
- iOS: add-ons that other apps connect to, such as AnkiConnect, can keep
  answering after you leave Kioku. Turn on **Preferences › Advanced ›
  Background › Keep running in the background** (off by default). iOS
  pauses apps a few seconds after they leave the screen, so dictionary and
  reader apps couldn't reach AnkiConnect and kept spinning. The option uses
  location updates to keep Kioku running, at the lowest accuracy and
  approximate by default. Kioku ignores the location: nothing is saved or
  sent. Only Kioku's own location request works: add-ons and web pages
  that ask for location get nothing
  ([Add-ons that other apps connect to](using/addons.md#add-ons-that-other-apps-connect-to-iphone-ipad),
  [issue #21](https://github.com/krmanik/kioku/issues/21)).
- iOS, Android: pictures and sounds keep downloading after a sync with
  AnkiWeb when the connection drops. On iPhone, leaving Kioku or locking
  the screen during the download stopped it with "Connection timed out"
  (or an `HttpError` message): the cards were there, but most pictures,
  image occlusion ones included, were missing until the next manual
  sync. Kioku now tries again by itself, and again when you come back
  to it, until the download completes. While it runs, the Sync button
  shows how many files came down.
- iOS: a sync keeps running for a short while after you leave Kioku,
  and the screen doesn't lock while one runs.
- iOS, Android: show and hide the browser's columns with touch, in
  **View › Columns**. Anki offers them in the column headers' context
  menu, which needs a right-click
  ([issue #20](https://github.com/krmanik/kioku/issues/20)).
- iPhone: number fields, such as Custom Study's "Increase today's new
  card limit by", get a **Done** button above the number pad. The pad
  has no Return key, so the keyboard couldn't be closed and covered the
  OK button.

## 0.2.9

- iOS, Android: gamepads and game controllers (Bluetooth or USB: Xbox,
  PlayStation, Switch Pro, 8BitDo…) study and move around Kioku. A shows
  the answer, then answers Good; B, X and Y answer Again, Hard and Easy;
  the d-pad moves through the deck list, dialogs and menus. Set each
  action's buttons by pressing them, per card side, as in AnkiDroid, or
  turn it off, in **Preferences › Advanced › Gamepad › Controls…**
  ([Gamepads and Controllers](features/gamepad.md),
  [issue #18](https://github.com/krmanik/kioku/issues/18)).
- iOS: the editor's formatting buttons work on selected text: bold,
  italic, underline, superscript, subscript, text colour, highlight and
  remove formatting. MathJax and cloze keep the selected text
  ([issue #17](https://github.com/krmanik/kioku/issues/17)).
- iOS: add-ons can record from the microphone, for example with
  `AVAudioRecorder` through rubicon-objc. iOS asks for access the first
  time; before, it closed Kioku
  ([issue #19](https://github.com/krmanik/kioku/issues/19)).
- iOS: a field keeps its caret when it gets the focus back without a tap
  (Tab with a keyboard, back from a dialog); the caret went to the end.
- Self-hosted server (Docker): FFmpeg is in the image, so add-ons that
  use `ffmpeg`, `ffprobe` or `ffplay` work without installing it
  ([issue #15](https://github.com/krmanik/kioku/issues/15)).
- Self-hosted server (Docker): `INSTALL_PACKAGES` installs Debian
  packages that add-ons need when the container starts, such as
  `INSTALL_PACKAGES: "imagemagick sox"`. A restart finds them installed
  and downloads nothing
  ([issue #15](https://github.com/krmanik/kioku/issues/15)).
- Phones with a narrow screen (such as 720 px wide ones) or a larger
  interface size: the main screen fits the screen. The top bar, the
  deck list and the buttons under it were shifted right and cut off
  ([issue #14](https://github.com/krmanik/kioku/issues/14)).
- Android phones with an older system WebView (before Chrome 105, such
  as Android 11's built-in one without updates): the deck list fits the
  screen again; its Learn and Due columns ran off the right side.
- iOS, Android: add-ons with a hidden page, such as Contanki, no longer
  leave a white box over the top left of the main window.
- Phones: the top bar's buttons wrap to a second row when their labels
  are too long for the screen (Russian, German). They ran off both sides.
- iOS: no crash after shaking the device and choosing Undo. Shake to
  undo and the three-finger undo gestures are off; use Anki's Undo
  (Edit menu or Cmd-Z).
- iPad: no crash on a touch after using an Apple Pencil.
- iPad (iPadOS 26): the iPad's menu bar (swipe down from the top of the
  screen) has Anki's menus, with their ⌘ shortcuts, instead of empty File,
  Edit, Format, View, Window and Help menus. Browse's menus are there while
  Browse is open. Anki's own menu row stays; with the iPad's menu bar
  always shown, turn it off with **View › Show Menu Row**. Anki's View ›
  Full Screen is called **Hide Toolbars** on the iPad, next to the iPad's
  own Window › Full Screen.
- iOS, Android: `kioku://` links let other apps and Shortcuts add notes,
  sync and search, with AnkiMobile's actions and parameters
  ([kioku:// links](features/links.md)).

## 0.2.8

Anki 26.09.4.

- Termux: Kioku 0.2.7 didn't start ("the sip module implements ABI v13.0
  to v13.12"): a Termux update of PyQt6 needed a newer sip module than the
  one in the app. The build now picks the sip module PyQt6 needs.
- Android: turning the sync server on and off again quickly no longer
  closes the app.

## 0.2.7

- Pictures and sounds attached with the paperclip or recorded with the
  microphone show in the field right away. They used to show only after
  opening the field's HTML editor (`<>`).
- Pictures copied in another app can be pasted into a field on Android, and
  pictures, sounds and videos can be dropped onto a field.
- Anki Leaderboard's table on the home screen scrolls sideways in its own
  box on phones, like the deck list. It used to make the whole home screen
  wider than the screen and zoom it out.
- Card preview on phones shows the whole answer: an image occlusion card's
  Toggle Masks button and Back Extra were cut off under the picture.
- Kioku Web shows pictures whose file name contains `#` or `%` (they were
  missing, e.g. on image occlusion cards).
- Android 14 and older: the edges of the Add, Edit and Browse windows no
  longer flash black when the keyboard opens or closes.
- Tapping next to a field (just above or below it, or between two fields)
  moves to that field instead of closing the keyboard: on iPhone the keyboard
  used to pop up and go down again.
- iPhone and iPad in dark mode: pages no longer flash white when they open
  (the deck list at start, Add, Browse).

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
