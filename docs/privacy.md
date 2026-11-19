# Kioku privacy policy

Last updated: 19 November 2026

Kioku (the iOS, native Android and Termux apps, the web version and the
Docker image from [github.com/krmanik/kioku](https://github.com/krmanik/kioku))
does not collect, store or share any personal data. It has no analytics, no ads, no tracking
and no account of its own.

## Your data

Your collections, media, add-ons and settings stay on your device, in the
app's own storage (on iOS, Kioku's folder in the Files app). The developer
never receives them.

- **Web version:** they stay in your browser's storage on that device. The
  site is served by Cloudflare Workers, which stores nothing of yours. Its
  relay passes AnkiWeb sync (and the few services it allows for add-ons)
  through as an encrypted connection made in your browser, so the relay
  can't read it.
- **Docker image:** they stay on the server you run it on. The browser
  receives only the picture and sound of Anki's screen, from your server.

## Network connections

Kioku only connects to the internet when you use a feature that needs it:

- **AnkiWeb sync**, when you sign in with your AnkiWeb account. Your login and
  collection go to AnkiWeb, run by Ankitects, under
  [AnkiWeb's terms and privacy policy](https://ankiweb.net/account/privacy).
- **Downloading add-ons and shared decks** from AnkiWeb.
- **Content in your cards** that points to the internet, such as images,
  audio, videos or fonts loaded by a card template.
- **Add-ons you install**: they are third-party programs and may connect to
  their own services (for example text-to-speech). Check each add-on's
  description.
- **Kioku's sync server and remote desktop**, only if you turn them on: they
  accept connections from the devices you choose (this phone, your Tailscale
  network or your Wi-Fi). Nothing is sent to the developer.

## Location (iPhone, iPad)

Kioku asks for location access only if you turn on **Preferences › Advanced
› Background › Keep running in the background**, which keeps add-ons such as
AnkiConnect answering other apps after you leave Kioku. iOS keeps an app
running in the background while it receives location updates; that is the
only reason Kioku asks for them.

- Kioku asks iOS for the lowest accuracy it offers (about 3 km, without
  GPS), and iOS grants only approximate location unless you turn Precise
  on yourself.
- The locations iOS delivers are ignored: Kioku doesn't read, save, show or
  send them.
- No location data leaves your device, and the developer never receives
  any.
- With the option off (the default), Kioku receives no location at all.
  Turning it off stops location use at once; to take back the permission,
  use the Settings app › Apps › Kioku › Location › Never.
- **Add-ons** are third-party programs that run inside Kioku and share its
  permissions. Kioku lets only its own location request work: add-ons and
  web pages that ask for location get nothing. An add-on written to get
  around this could still read your approximate location while access is
  allowed, so install only add-ons you trust.

## TestFlight

If you install Kioku through Apple's TestFlight, Apple handles the beta under
[its own terms and privacy policy](https://www.apple.com/legal/privacy/). Apple
then shows the developer what TestFlight collects for every beta app: the
name and email address you were invited with (if invited by email), your
device model and iOS version, installs and sessions, crash reports, and any
feedback or screenshots you send through TestFlight. Kioku itself still sends
nothing. The TestFlight signup form (Google Forms) collects your Google
account's email address only to allow one signup per account, because
TestFlight has a limited number of testers.

## Children

Kioku does not knowingly collect information from anyone, including children.

## Changes and contact

Changes to this policy are published on this page. Questions:
[open an issue](https://github.com/krmanik/kioku/issues).
