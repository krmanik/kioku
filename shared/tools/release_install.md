## 1. iOS variant

Two ways to get Kioku for iOS:

- **TestFlight**, Apple's beta app: no signing, no 7-day refresh. Sign up with a [short form](https://forms.gle/fw4YMTdGbgD8nqPe8) to get the link.
- **Sideloading** the unsigned `.ipa` from GitHub Releases: you sign it with your own Apple ID while installing.

> Kioku won't be in the App Store; TestFlight is the only Apple-signed way.

#### TestFlight
TestFlight has a limited number of testers, so the link comes from a signup form that allows one signup per Google account.

1. Fill in the [signup form](https://forms.gle/fw4YMTdGbgD8nqPe8); the TestFlight link is shown after you submit.
2. Install [TestFlight](https://apps.apple.com/app/testflight/id899247664) from the App Store.
3. Open the link on your iPhone or iPad and tap **Accept**, then **Install**.
[Read more](https://krmanik.github.io/kioku/install/ios.html#testflight)

#### AltStore
In AltStore, add the source `https://github.com/$repo/releases/latest/download/altstore.json` (Sources → +) and install Kioku from it; updates then show up in AltStore. Use a spare Apple ID for it, not your main one.
Or install `Kioku-iOS-$version-unsigned.ipa` with any tool that signs apps with your Apple ID. Needs iOS 17 or newer.

## 2. Android (native) variant
Download `Kioku-Android-$version-arm64.apk` on your phone and open it (allow installing from your browser or file manager when Android asks).
Needs a 64-bit ARM phone (arm64-v8a) with Android 9 or newer. It installs next to the Termux variant.

## 3. Termux variant
Download `Kioku-Termux-$version-arm64.apk` on your phone and open it (allow installing from your browser or file manager when Android asks).
Needs a 64-bit ARM phone (arm64-v8a), Android 7 or newer and about 1 GB of free storage.
The first start unpacks the runtime, which takes about a minute.
