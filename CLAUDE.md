# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

YTLite (published as **YouTube Plus**) is an iOS tweak for the YouTube app that adds 100+ customizable features via Objective-C runtime method hooking. It targets `com.google.ios.youtube` and is distributed as a Debian `.deb` package for jailbroken devices, or injected into a sideloaded `.ipa` for non-jailbroken devices.

- **Package ID:** `com.dvntm.ytlite`
- **Preferences suite:** `com.dvntm.ytlite`
- **Supported iOS:** 13.0+ (arm64 only)
- **Build framework:** [Theos](https://theos.dev)

## Build Commands

Requires Theos installed with `$THEOS` set and an iPhoneOS 16.5 SDK.

```sh
make                          # Build tweak (.deb)
make clean package            # Clean rebuild
make ROOTLESS=1               # Build for rootless jailbreak
make ROOTHIDE=1               # Build for roothide jailbreak
```

CI builds happen via GitHub Actions (`main.yml`) on `macos-latest` using Theos commit `9bc73406cf80b711ef4d02c15ff1dedc4478a275` and iPhoneOS 16.5 SDK. There is no conventional test suite — verification is manual on a jailbroken device.

## Architecture

The tweak is structured as a set of Theos `.x` files that compile to a single dylib injected into YouTube at runtime:

| File | Role |
|---|---|
| `YTLite.x` | Core hooks (~1400 lines): ads, background playback, downloads, UI hiding, SponsorBlock, player settings, gestures |
| `Settings.x` | Injects a "YouTube Plus" section (ID `789`) into YouTube's native Settings UI; all toggles and controls are wired here |
| `Sideloading.x` | Identity spoofing and keychain patching for non-jailbroken sideloaded installs |
| `YTNativeShare.x` | Replaces YouTube's share sheet with the native iOS share sheet |
| `YTLite.h` | Master header: global macros, forward declarations for 100+ private YouTube framework classes |
| `YouTubeHeaders.h` | Aggregates YouTube private headers from the Theos include path |

**Utils/**

| File | Role |
|---|---|
| `YTLUserDefaults.{h,m}` | Singleton `NSUserDefaults` subclass scoped to `com.dvntm.ytlite`; registers default values on first launch |
| `NSBundle+YTLite.{h,m}` | Category providing `+ytl_defaultBundle` for rootless/roothide-aware resource bundle access |
| `Reachability.{h,m}` | BSD-licensed network reachability utility |

## Key Patterns

**Reading/writing preferences** — always use these macros from `YTLite.h`:

```objc
ytlBool(@"preferenceKey")           // read BOOL
ytlInt(@"preferenceKey")            // read NSInteger
ytlSetBool(value, @"preferenceKey") // write BOOL
ytlSetInt(value, @"preferenceKey")  // write NSInteger
```

**Localized strings** — all UI text must go through the `LOC()` macro and have entries in every language bundle under `layout/Library/Application Support/YTLite.bundle/<lang>.lproj/Localizable.strings` (16 languages: ar, en, es, fr, it, ja, ko, pl, ru, tr, vi, zh-Hans, zh-Hant, and others).

```objc
LOC(@"StringKey")
```

**Adding a new toggle** — the typical pattern:
1. Add a default value in `YTLUserDefaults.m → registerDefaults` if needed.
2. Add localized string keys (`KeyName` and `KeyNameDesc`) to all 16 `Localizable.strings` files.
3. Add `[self switchWithTitle:@"KeyName" key:@"preferenceKey"]` in the appropriate section inside `Settings.x`.
4. Hook the relevant YouTube class in `YTLite.x` gated on `ytlBool(@"preferenceKey")`.

**Settings UI accent color:** `rgb(191, 128, 230)` / `colorWithRed:0.75 green:0.50 blue:0.90 alpha:1.0` — used for switch tint and touch feedback in `Settings.x`.

**Hook syntax (Theos Logos):**
```objc
%hook YouTubeClassName
- (ReturnType)methodName:(ArgType)arg {
    if (ytlBool(@"featureKey")) {
        // custom behavior
    }
    return %orig;
}
%end
```

## GitHub Actions Workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| `main.yml` | Manual (`workflow_dispatch`) | Downloads decrypted YouTube IPA, builds selected optional tweaks, injects all `.deb`s via `cyan`, publishes modified IPA to Releases as a draft |
| `_build_tweaks.yml` | Called by other workflows | Reusable: sets up Theos + SDK, clones and builds optional tweaks (YouPiP, YTUHD, YouQuality, ReturnYouTubeDislikes, YTABConfig, DontEatMyContent) |
| `cyan_ts.yml` | Manual | Produces `.cyan` and `.zip` artifacts for TrollFools/Cyan injection (non-jailbreak sideloading) |
| `ytp_beta.yml` | Manual | Same as `main.yml` but accepts a custom tweak URL for beta `.deb` files |

Optional tweak integrations bundled at build time: **YouPiP**, **YTUHD**, **YouQuality**, **Return YouTube Dislikes**, **YTABConfig**, **DontEatMyContent**. Each has its own preferences visible under YouTube Settings.

## Distribution

- Jailbroken: install `.deb` via a package manager (Sileo/Zebra); requires `mobilesubstrate`.
- Non-jailbroken: use the GitHub Actions workflow to inject the tweak into a decrypted IPA, then sideload via AltStore/TrollStore/Cyan.
- Version 5.2+ requires a subscription; last free release is tagged `v5.2b4`.
