# Sync server on the phone

> **Applies to:** iPhone/iPad, Android native, Android Termux

Kioku adds an **Advanced** tab to Anki's Preferences, with options for
experienced users. Everything there is off until
you turn it on, and each option explains its risks first.

## Sync server on this phone

Kioku can run Anki's own sync server (the one behind `anki --syncserver`) on
the phone. Then the phone can be the sync server, with no AnkiWeb needed:

- **AnkiDroid on the same phone** syncs with Kioku: Settings › Sync ›
  Custom sync server › Sync URL `http://127.0.0.1:8080/`, then log in with the
  user name and password shown in Kioku.
- **Kioku's own profiles** sync with it: press **Use for this profile**.
- **Anki on your computers** syncs with it over Tailscale (or your Wi-Fi):
  Preferences › Syncing › Self-hosted sync server.

| Android | iPhone | Android's notification |
| --- | --- | --- |
| <img src="../images/advanced-android-sync-server.png" width="240" alt="Preferences, Advanced tab on Android: the sync server is running on port 8080, with its address, user name and password"> | <img src="../images/advanced-ios-sync-server.png" width="240" alt="Preferences, Advanced tab on iPhone: the sync server is running on port 8080"> | <img src="../images/advanced-android-notification.png" width="240" alt="Android notification: Sync server running, listening on port 8080, with a Stop button"> |

| Setting | Meaning |
| --- | --- |
| Listen on: This phone only | only apps on the phone can connect (default) |
| Listen on: Tailscale | the phone's Tailscale address; your Tailscale devices can connect, encrypted by Tailscale |
| Listen on: All networks | any device on the same Wi-Fi or VPN can connect. Plain HTTP: only on networks you trust |
| Port | 8080 by default; choose another if an app already uses it |
| User name, password | a password is made up when you first turn the server on. **New** makes another one; devices then log in again |
| Delete server data | removes everything synced to the phone's server; each device's next sync is a full upload |

Things to know:

- The server keeps **its own copy** of everything synced to it (collection and
  media) in Kioku's private storage. It needs that much free space.
- A device that syncs with the phone **no longer syncs with AnkiWeb**.
- The first time, choose **Upload** on the device that has your cards and
  **Download** on the others.
- Two devices syncing at the same moment: one of them gets Anki's "Only one
  copy of Anki can sync to your account at once" error. Nothing is lost; sync
  it again a moment later.
- **Android:** while the server runs, a notification shows and Kioku keeps
  running in the background (its **Stop** action stops the server until
  Kioku starts again). Allow notifications when Android asks, or the
  notification stays hidden.
- **iPhone:** iOS pauses apps in the background, so the server only answers
  while Kioku is open. It starts again by itself when you come back.


## Step by step: syncing a computer or tablet with the phone

Based on a tutorial shared in
[issue #25](https://github.com/krmanik/kioku/issues/25), tested with an
iPhone running Kioku and a Mac.

**Before you start:** make a backup, and pick the one device whose
collection is the newest. If several devices have changes that haven't
synced yet, sync them with AnkiWeb first. To keep a copy outside the phone,
export a collection package with media
([Anki's manual: Exporting](https://docs.ankiweb.net/exporting.html)). The
server and Kioku live on the same phone, so losing the phone loses both.

### 1. Start the server

Preferences › Advanced › **Run a sync server on this phone**. Under
**Listen on**, choose **All networks** for Wi-Fi or the phone's hotspot,
or **Tailscale**. Wait for **Running** and note the port, user name and
password. They are the server's own and don't match your AnkiWeb login.

On iPhone, keep Kioku open on the screen while the other device syncs.

### 2. Find the address the other device uses

| Connection | Listen on | Address to enter on the other device |
| --- | --- | --- |
| Same Wi-Fi | All networks | the one Kioku shows for **Other devices on this network**, e.g. `http://192.168.1.42:8080/` |
| The phone's hotspot | All networks | the **router** (gateway) address in the other device's network settings, plus Kioku's port, e.g. `http://172.20.10.1:8080/` on an iPhone hotspot |
| Tailscale | Tailscale | the one Kioku shows, e.g. `http://100.101.102.103:8080/`. Both devices need Tailscale on and in the same tailnet; works across networks |

- With a hotspot, the address Kioku shows can be the phone's mobile-data
  address, which doesn't work. Use the router address instead.
- `http://127.0.0.1:…` means "this device". It only works for apps on the
  phone itself (AnkiDroid, Kioku), never from another device.
- Wi-Fi addresses can change when the phone reconnects. If syncing stops
  working, check the address again.

### 3. Upload once, from the device with the newest collection

- **It's Kioku on the server phone:** press **Use for this profile**,
  close Preferences, sync, and choose **Upload** if asked.
- **It's another device:** set it up as in step 4 and choose **Upload**
  there.

Wait for media to finish too. After that, never choose **Upload** on
another device: it would replace the server's collection.

### 4. Connect the other devices

Enter the address from step 2 as the self-hosted or custom sync server,
log in with the **server's** user name and password (the field may still
say Email or AnkiWeb), sync, and choose **Download** if asked.

- **Anki on a computer:** Preferences › Syncing. Log out of AnkiWeb first.
  See [Anki's manual: Self-hosted sync server](https://docs.ankiweb.net/sync-server.html).
- **Kioku on another iPhone, iPad or Android:** Preferences › Syncing.
- **AnkiMobile:** its custom sync server setting. If it can't connect over
  Wi-Fi, allow **Local Network** for it in iOS Settings.
- **AnkiDroid:** Settings › Sync › Custom sync server.

### Switching between Wi-Fi, hotspot and Tailscale

The server keeps the same collection, so nothing needs deleting. Change
**Listen on** if needed, put the new address on each device, press **Use
for this profile** again on the server phone if its address changed, and
sync one device at a time. If Anki suddenly asks for a full Upload or
Download, stop and check which copy is newest first: changing networks is
no reason to pick either.

### If it doesn't work

- **Can't connect:** Kioku open, server **Running**, address and port
  right. Some Wi-Fi networks (guest, office) don't let devices reach each
  other; use the hotspot or Tailscale.
- **Login fails:** use the server's user name and password from Kioku.
  After **New**, every device logs in again.
- **Cards sync but not images or sounds:** let media sync finish; it takes
  much longer than cards.
- **Delete server data** removes everything on the server. It isn't a
  troubleshooting step: use it only to start over, with backups checked.
