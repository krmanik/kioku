# Native apps (iPhone, Android)

> **Applies to:** iPhone/iPad, Android native

| Deck list | Reviewing | Browse |
| :---: | :---: | :---: |
| <img src="../images/android-decks.png" width="200" alt="Deck list"> | <img src="../images/android-review-question.png" width="200" alt="Reviewing a card"> | <img src="../images/android-browse.png" width="200" alt="Browse, full screen"> |

## Windows

- **The main window** (deck list, overview, reviewer) fills the screen, with
  Anki's menu bar at the top: **File, Edit, View, Tools, Help** and add-on
  menus.
  - iPad with iPadOS 26 or later: Anki's menus are also in the iPad's own
    menu bar (swipe down from the top of the screen, or move the pointer
    there), with their ⌘, ⌃ and ⌥ shortcuts. Browse's menus are there while
    Browse is open. If you keep the iPad's menu bar on screen (iPadOS 27:
    Settings › Multitasking & Gestures, **Automatically Show and Hide Menu
    Bar** off), turn off **View › Show Menu Row** to have the menus only
    once. Kioku remembers it; turn it back on from the iPad's View menu.
- **Every other window** (Browse, Add, Statistics, Preferences, Deck Options…)
  opens full screen on top, with a title bar.
- **Closing a window:**
  - iPhone, iPad: **‹ Back** in its title bar.
  - Android: the **Back** key or gesture closes the top window. On the main
    window it moves Kioku to the background (Anki keeps running).
- **Small windows** (the AnkiWeb login, Create Deck, Rename, message boxes)
  are cards in the middle of the screen, sized to their content, and move up
  above the keyboard while you type.

| A prompt | A login | The Edit menu while reviewing |
| :---: | :---: | :---: |
| <img src="../images/android-create-deck.png" width="200" alt="Create Deck prompt as a card"> | <img src="../images/android-login.png" width="200" alt="AnkiWeb login as a card"> | <img src="../images/android-menu-edit.png" width="200" alt="Edit menu with Edit Current and More while reviewing"> |

## Touch

- **Tap** for a click, **drag** to scroll lists and pages.
- **While reviewing**, Anki hides its Edit and More buttons on a narrow
  screen; Kioku offers them in the **Edit** menu (**Edit Current**,
  **More**: flag, bury, suspend, card info…).
- **Landscape** works; windows follow the rotation.
- Keyboard shortcuts work with a hardware keyboard (Space to show the answer,
  1–4 to answer, as in [Anki](https://docs.ankiweb.net/studying.html#keyboard-shortcuts)).

## Full screen

**View › Full Screen** hides the menu bar (and the status bar) for more room.
To leave it, **swipe right** on the screen and tap **Exit Full Screen**
(or **Cancel** to stay in full screen).
Kioku reminds you of this for a few seconds when you enter full screen.
On a page that scrolls sideways, scroll it back to its left edge first.

On an iPad with iPadOS 26 or later this item is called **View › Hide
Toolbars**: it hides Anki's bars, but the iPad doesn't let apps resize
their window. To make the window fill the screen, use the iPad's **Window ›
Full Screen**. To get the bars back, choose **View › Show Toolbars** in the
iPad's menu bar (or press F11); a swipe right there is the iPad's own.

<img src="../images/ios-full-screen.png" width="200" alt="Full screen: after a swipe right, Kioku asks Exit full screen? with Cancel and Exit Full Screen">

## Keyboard

The on-screen keyboard opens when you tap a text field and closes when you
tap elsewhere. On Android the keyboard's Enter key (✓) submits single-line
fields: Browse's search, prompts, the login.

## Sound and speech

- **Card audio** (mp3, wav, Ogg Vorbis, Opus) plays as in Anki, with the
  replay buttons.
- **`{{tts}}` text-to-speech** uses the phone's voices: iOS's voices, and
  Android's text-to-speech engine (Settings › Text-to-speech on the phone).
  Install a voice for the language you need there.

## In the background

- **Android:** Kioku keeps running in the background like other apps; Android
  may stop it when memory runs low. Your collection is saved whenever Kioku
  leaves the screen.
- **iPhone, iPad:** iOS pauses Kioku in the background. It saves first.

## Web views

Cards, the editor and statistics are web pages in the system's web view. Card
JavaScript works. For card template authors: the web views can be inspected
with Safari's Web Inspector (iOS) or `chrome://inspect` (Android).

## Differences from Anki on a computer

- File dialogs are the phone's own file picker ([Your Files](files.md)).
- "Show in folder" / "Open folder" show the folder's path instead of a file
  manager on Android.
- Add-ons that start other programs don't work ([Add-ons](addons.md)).
- The card types editor (Cards…) is cramped in portrait; turn the phone.
