# Juriscite — Install & Mobile Build Guide

**Updated:** 2026-06-24 · Owner: Kavela Narula

There are **two** ways to put Juriscite on a phone. Path A is **done and free**; Path B (app stores)
is **owner-gated** because it needs hardware and paid accounts I can't provision.

---

## Path A — PWA (installable web app) ✅ BUILT, works on Android **and** iOS

The app is a Progressive Web App: a real installable app with its own icon, splash, and standalone
window — no app store, no Mac, no fees.

**Requirement:** the site must be served over **trusted HTTPS** (a service worker won't register on a
self-signed cert). On `localhost` it works as-is. In production, point a domain at the EC2 box and run
certbot for a real cert (already on the founder TODO) → then it's installable for everyone.

### How a user installs it
- **Android (Chrome):** open the site → tap the **"Install Juriscite"** button (or ⋮ menu → *Install
  app / Add to Home screen*). Installs as a WebAPK with the gold "J" icon.
- **iOS (Safari 16.4+):** open the site → **Share** → **Add to Home Screen** → *Add*. Launches
  full-screen with the icon.

### What's in the repo (Path A)
- `app/static/manifest.webmanifest` — name, icons, theme, `display: standalone`.
- `app/static/service-worker.js` — offline shell; **never caches `/api` (tenant data)**.
- `app/static/offline.html` — branded offline screen.
- Icons: `icon-192/512`, `icon-maskable-512`, `apple-touch-icon` (gold "J" on black).
- Served at root scope via `/manifest.webmanifest` + `/service-worker.js`; injected on every page by
  `utils.js` (`injectPWA`). Guarded by `tests/test_pwa.py`.

---

## Path B — Native App Store / Play Store apps ⛔ OWNER-GATED

A thin **Capacitor** wrapper (in `mobile/`) loads the hosted Juriscite app inside a native shell you
can submit to the stores. The **scaffold is ready**; the build/publish steps need *your* machine +
accounts.

### Why I can't finish this for you (honest constraints)
- **iOS cannot be built on Windows at all** — Apple requires **macOS + Xcode**. You need a Mac (or a
  cloud-Mac/CI like Codemagic/EAS).
- **Store accounts are paid and personal:** Apple Developer (**$99/yr**) and Google Play (**$25 once**).
  I'm not permitted to create accounts or handle signing credentials.
- **Signing certificates / keystores** are secrets only you should hold.

### Prerequisites
- **Android:** Node.js 18+, Android Studio (SDK + Gradle), a JDK.
- **iOS:** a **Mac** with Xcode + CocoaPods, an Apple Developer account.

### Build steps (run in `mobile/`)
```bash
cd mobile
npm install
# set your real production URL in capacitor.config.json (server.url), e.g. https://app.juriscite.in

# Android (Windows/Mac/Linux)
npm run add:android
npm run sync
npm run open:android      # Android Studio → Build > Generate Signed Bundle (.aab) → Play Console

# iOS (Mac only)
npm run add:ios
npm run sync
npm run open:ios          # Xcode → set Team/signing → Archive → upload to App Store Connect
```

### Store submission checklist (you/your reviewers)
- App icon (1024²), screenshots, descriptions — use the gold-"J" brand.
- **Privacy/Data-Safety forms** — fill from `docs/legal/DATA_MAP_AND_STORE_DISCLOSURE_MATRIX.md` +
  `docs/legal/APP_STORE_PRIVACY_PACKET.md` (must match real behaviour).
- Public **Privacy Policy URL** → `/legal/privacy`; **account deletion** path → `/account`.
- **Abuse reporting** path → in-app `/api/misuse` (LEGAL-16).
- Human gates **G6 privacy + G7 security** signed before real client data (pre-publish lock, LEGAL-22).

### Note on the wrapper
The current `capacitor.config.json` uses `server.url` (loads the hosted site — fast to ship, always
up to date). Later you can switch to **bundling** the frontend offline-first if you split the UI into a
static client. For the current server-rendered app, the hosted-wrapper approach is correct.
