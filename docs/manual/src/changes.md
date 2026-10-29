# Changes

All releases: [GitHub Releases](https://github.com/krmanik/kioku/releases).

## Next release: add-ons that start programs (iOS, Android)

- The apps include FFmpeg, MeCab, KAKASI, Tesseract (English, Japanese,
  Chinese, Korean), eSpeak NG, LAME and cwebp, the programs add-ons such as
  Japanese Support, AJT Media Converter and OCR add-ons start. An add-on's
  own copy of one of them (made for Windows, macOS or Linux) is replaced by
  Kioku's.
- numpy, Pillow and cryptography for add-ons that import them.
- The app is larger: about 140 MB on Android.

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
