# Troubleshooting

For problems inside Anki itself (a deck, a sync error message, card
templates), see [Anki: Troubleshooting](https://docs.ankiweb.net/troubleshooting.html).

## Known issues

| Issue | Variant | Workaround |
| --- | --- | --- |
| Exports and PDFs are in `Android/data/…`, hidden from most file managers on Android 11+ | Android | copy over USB, or use AnkiWeb sync |
| Back while reviewing leaves the app instead of returning to the deck list | Android | tap **Decks** in the top bar |
| The card types editor (Cards…) is cramped in portrait | iOS, Android | turn the phone |
| The sync conflict box (Upload/Download) has a large empty gap | iOS | it works; tap a button |
| Review Heatmap is slightly wider than the screen | iOS, Android | drag sideways |
| History button shows "History ▯" in Add | Android | cosmetic |
| Add-ons that start a program Kioku doesn't bundle (mpv, osascript, ...; bundled: FFmpeg, MeCab, KAKASI, Tesseract, eSpeak NG, LAME, cwebp) | iOS, Android | use the Termux variant or the Docker image |

iOS = iPhone/iPad, Android = Android native, Termux = Android Termux.

## iPhone, iPad

### Kioku closes right after choosing the language (iPad, iOS 18)

Fixed in 0.2.2. Two causes: VoiceOver or another accessibility feature
running, and iOS 18's WebKit. Update to 0.2.2 or newer.

### Kioku doesn't open any more

A free Apple ID's signature expires after 7 days. Refresh it in AltStore or
SideStore, or install the `.ipa` again: your data is kept.

From TestFlight: the build expired (90 days after upload). Install the newer
build in TestFlight, or get the link again from the
[signup form](https://forms.gle/fw4YMTdGbgD8nqPe8) if there's none. Your data is kept.

### AltServer

**"AltServer could not retrieve anisette data value “machineID”"** (newer
macOS, such as the macOS 27 betas): AltServer can't get the device data
Apple's sign-in needs. Until AltStore fixes it:

- install the `.ipa` with [Sideloadly](https://sideloadly.io) instead;
- or try a community AltServer build with an anisette fix, such as
  [kimziro/altserver-macos27-anisette-fix](https://github.com/kimziro/altserver-macos27-anisette-fix)
  or [an-vo90/AltServer-1.8-build97-Anisette-Fix-macos27-alpha](https://github.com/an-vo90/AltServer-1.8-build97-Anisette-Fix-macos27-alpha).
  These are unofficial and not reviewed by Kioku: they handle your Apple ID
  sign-in, so use them only if you trust them, preferably with a separate
  Apple ID made for sideloading.

**"Failed to verify code signature … (The provisioning profile is banned.)"**:
Apple has temporarily blocked sideloading for that Apple ID. Wait, or use
another Apple ID only for sideloading.

## Android, native

### No sync server notification

Allow Kioku's notifications in Android's settings (Apps › Kioku ›
Notifications). See [Sync server](features/sync-server.md).

### Card audio or `{{tts}}` is silent

Check the media volume. For `{{tts}}`, install a voice for the card's
language in Android's Settings › Text-to-speech.

## Android, Termux

### The first start takes long

Unpacking the runtime takes about a minute (longer on slow phones), after
installing and after each update.

### Start-up fails

Use the buttons on the error screen: **Retry**, **Safe mode** (Anki without
add-ons), **Repair runtime** (decks kept), **Share log**. See
[Termux desktop](using/termux.md#if-start-up-fails).

### A Linux app doesn't scroll or select as expected

Switch Settings › Touch screen / Mouse pad. See
[Termux desktop](using/termux.md#touch-screen-or-mouse-pad).

## Self-hosted server (Docker)

### The page stays black or doesn't connect

Browsers play the stream only from a secure page: open it through your
reverse proxy's `https://` address (or `http://localhost` on the server
itself), not `http://<server address>:3000`. The proxy must pass
WebSockets. See [HTTPS](install/self-hosted.md#https).

### No sound

Click the page once (browsers wait for a click before playing sound), and
check the speaker button in the side menu.

### Anki says it can't write its files

`anki-config` must belong to the `PUID`/`PGID` user, for example after
copying a collection there: `sudo chown -R 1000:1000 anki-config`.

### Anki was closed

It opens again by itself after a second. To change what runs, right-click
the empty desktop.

### What the container did

`docker compose logs anki`. Anki's own log is in `anki-config/Anki2/logs`.

## Reporting a bug

Open an issue on [GitHub](https://github.com/krmanik/kioku/issues) with:

- the variant, Kioku version (Help › About) and phone model/OS version
  (Docker: the image tag and your browser);
- what you did and what happened;
- the log, if you can: iPhone, `kioku.log` in Files › Kioku; Android
  native, `Android/data/io.ankidesk.kioku/files/kioku.log`; Termux, **Share
  log** on the error screen.
