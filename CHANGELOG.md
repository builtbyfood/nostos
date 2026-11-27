# Changelog

## 0.2.4 - 2026-11-26

From the report of the first complete real move (Windows 10 to Fedora 45 KDE, 49,290 files, 117.7 GB, no files failed).

- **Programs, one line each.** A program that Windows lists under many names is now reported once: the real report had eleven lines for OpenVPN (its Wiki, HOWTO, Manual Page and so on). Start-menu documentation links, add-ins, "Add a new … adapter" entries and maintenance services are no longer treated as programs.
- **Less noise in "no Linux match found".** Things that come with Windows or the PC maker (Money, News, Sports, Copilot, PC Health Check, Mobile Plans, Candy Crush and similar) are left out.
- **Better answers** for Skype, Sway, SatDump and DVD players (Nero, AnyDVD). Snipping Tool now points at the desktop's own screenshot tool instead of installing another one.
- **App store guesses are stricter.** One-word names such as "Money" or "News" produced wrong guesses; a one-word name must now match the app's title exactly, and longer names must have every word present.
- **Open Wi-Fi networks are no longer joined automatically.** Networks without a password (cafes, hotels) are remembered but set not to connect by themselves, and the report says so. Networks with a password behave as before.
- README status table updated with what the real run confirmed.

## 0.2.3 - 2026-11-24

Housekeeping after the first push to GitHub; no change to how Nostos behaves.

- Removed a real first name, PC name, NAS name and home network addresses that had been left in a code comment, tests, examples and two messages. They are replaced by the same made-up names the documentation uses.
- CI: the build step calls `bash build-agent.sh`, so it no longer depends on the executable bit. CI badge added to the README.
- README and reference: install instructions now start from `git clone`.
- `LICENSE`: copyright line filled in properly. `.gitattributes` tidied.
- The screenshot generator takes the version number from the code.

## 0.2.2 - 2026-11-24

- **Documentation:** `docs/USER-GUIDE.md` (the whole move, step by step, with 15 screenshots), `docs/TROUBLESHOOTING.md` (every message and what to do) and `docs/REFERENCE.md` (installing, file locations, ports, command line, helper, program table). `tools/make_screenshots.py` regenerates all screenshots from made-up data.
- Fixed: speed and time left were overstated when a run resumed, because files skipped as "already here" were counted as transferred. Both now come only from bytes actually sent. Long estimates are shown in hours.
- Fixed: bookmarks were written into a Chrome/Edge/Brave profile folder even when that browser was not installed, and the report claimed they had been "put straight in". They now go only into a browser that is installed (as a package or a Flatpak).
- Programs are now installed before bookmarks are handled, so a browser installed during the run receives them.
- The report shows locations as "Documents/… in your Home folder" instead of full paths, and says "1 file" correctly.
- The Windows app's messages start with a capital letter.

## 0.2.1 - 2026-11-24

From the first real run of the Windows app (Windows 10 to Fedora 45 KDE): the app paired and connected, then the Choose page stopped with "'lazy_import' object is not callable".

- Fixed: the Choose page no longer fails as a whole when one thing cannot be worked out. Programs, app-store search, Steam, bookmarks, wallpaper, Wi-Fi, network drives and printers are each checked on their own; a part that fails is named on the page and left out, and the rest is shown.
- Changed how the thread pool is imported (top of the file, from its concrete module). The error text points at a lazily imported name being called before it was loaded, and the only such import on that code path was a function-level `from concurrent.futures import ThreadPoolExecutor`. Not reproduced here (needs the Python on Fedora 45), so treat as the likely cause until the next run confirms it.
- Errors are now written with full detail to `~/.cache/nostos/nostos.log`, and the window says so.

## 0.2.0 - 2026-11-24

- **Nostos app for Windows** (`NostosAgent.exe`, Go source in `agent/`): double-click, type the code Nostos shows, choose what may be copied (everything, only my files, or picked folders). It connects out to Nostos over an encrypted link, so Windows needs no sharing, firewall, account or registry changes. Finds Nostos on the network by itself; the address can be typed as a fallback. Keeps the PC awake while connected.
- New first option on the Start page for the app; Windows file sharing, drive and OneDrive sources remain.
- **Any folder, any drive:** "Choose more folders…" on the Choose page browses everything the source exposes.
- **Steam libraries** (experimental): found through the Steam folder and its library list, shown with game count and size, copied to `~/SteamLibrary-Windows` for Steam to adopt.
- **Programs:** the built-in table roughly doubled (game launchers, media, developer, hardware, CAD tools); programs it does not know are looked up on Flathub and offered unticked as "possible matches"; the report now gives a next step for every program.
- **Other distributions:** `install.sh` handles Fedora, Debian/Ubuntu, Arch and openSUSE package names and falls back to a private Python environment. Wallpaper works on GNOME, Cinnamon and MATE as well as KDE; network folders are added to GTK file-manager sidebars as well as Dolphin.
- Fixed: "Start copying" could be pressed while Nostos was still looking at the PC.
- Copy block size raised to 4 MB.
- Tests: 17 engine/link tests, and a window test that runs a whole move through the app link.

## 0.1.2 - 2026-11-24

Repository housekeeping only; no code changes from 0.1.1.

- Screenshots in `docs/screenshots/` and in the README.
- `SECURITY.md`, a bug-report issue template, and a roadmap section in the README.

## 0.1.1 - 2026-11-24

From the first real run (Windows 10 PC to Fedora 45 KDE, own account, `Users` share).

- Fixed: picking a PC from the list, or typing its name, failed with "Could not reach" because Windows PC names often do not resolve on Linux. Nostos now always connects to the address: it uses the address found by the network scan, then DNS, NetBIOS and mDNS, and if none works it asks for the address and says where to find it.
- Password box is hidden by default, with a show/hide button.
- Copy page shows the transfer speed next to the amount and time left.
- Window title no longer repeats the name.
- Added `.gitignore` and `LICENSE` for publishing.

## 0.1.0 - 2026-11-24

First version.

- Step-by-step Qt (PySide6) window: Start, Connect, Choose, Copy, Done.
- Sources: Windows PC over SMB (no mount, no root), USB drive / Windows disk / any folder, OneDrive.
- Windows helper (`Prepare this PC.cmd`): temporary read-only account and share, inventory of programs, mapped drives, printers and Wi-Fi; cleans up after itself.
- Copies Desktop, Documents, Pictures, Music, Videos, Downloads (including OneDrive-redirected ones) into the matching Linux folders; other profile folders go to `~/From Windows`.
- Never overwrites; safe to stop and re-run.
- Bookmarks from Chrome, Edge, Brave and Firefox; wallpaper; Wi-Fi networks; mapped drives into Dolphin Places.
- Windows program to Linux replacement table with one-click Flatpak installs.
- OneDrive through rclone: sign-in, `~/OneDrive` folder kept connected by a systemd user service, optional full download.
- HTML report of what was done and what is left to do.
