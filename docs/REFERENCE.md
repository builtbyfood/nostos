# Nostos reference

Version 0.2.3. For the person setting Nostos up, or anyone who wants the details. The walkthrough is in [USER-GUIDE.md](USER-GUIDE.md); problems are in [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

**Contents**

- [Installing](#installing)
- [Updating and removing](#updating-and-removing)
- [What Nostos puts on the Linux computer](#what-nostos-puts-on-the-linux-computer)
- [What happens on the Windows PC](#what-happens-on-the-windows-pc)
- [Network ports](#network-ports)
- [The Windows app from the command line](#the-windows-app-from-the-command-line)
- [The file-sharing helper](#the-file-sharing-helper)
- [How files are matched and skipped](#how-files-are-matched-and-skipped)
- [The program table](#the-program-table)
- [Building the Windows app](#building-the-windows-app)
- [Tests and screenshots](#tests-and-screenshots)

---

## Installing

```bash
git clone https://github.com/builtbyfood/nostos.git
cd nostos
./install.sh --dry-run     # shows what it would do, changes nothing
./install.sh
```

Without Git: download the repository as a zip from GitHub, unpack it, and run the same two `install.sh` commands inside the unpacked folder.

`install.sh` asks for the administrator password (it uses `sudo` for each step that needs it) and:

1. Installs the packages Nostos needs with your distribution's package manager.
2. Copies Nostos to `/opt/nostos`, a launcher to `/usr/local/bin/nostos`, and a menu entry to `/usr/share/applications/nostos.desktop`.
3. If a Python part is not packaged for your distribution, builds a private Python environment in `/opt/nostos/venv` and downloads the missing parts into it. The system Python is left alone.

| Distribution family | Package manager | Status |
|---|---|---|
| Fedora (KDE, Workstation) | `dnf` | Installed and run on Fedora 45 KDE at 0.1.0 and 0.2.x |
| Debian, Ubuntu, Mint | `apt-get` | Unverified |
| Arch, Manjaro, EndeavourOS | `pacman` | Unverified |
| openSUSE | `zypper` | Unverified |
| Anything else | none | Falls back to the private Python environment; needs `python3` with `venv` |

Packages, by purpose:

| Purpose | Fedora name | Needed for |
|---|---|---|
| Python 3 | `python3` | Everything |
| Qt for Python | `python3-pyside6` | The window |
| SMB library | `python3-smbprotocol` | Windows file sharing |
| Cryptography | `python3-cryptography` | The encrypted link to the Windows app |
| Samba client | `samba-client` | Listing shares (optional) |
| rclone, FUSE 3 | `rclone`, `fuse3` | OneDrive (optional) |
| Flatpak | `flatpak` | Installing programs and app store search (optional) |
| XDG user dirs | `xdg-user-dirs` | Finding Documents, Pictures and so on when they are renamed or translated (optional) |

Desktop support:

| Feature | KDE Plasma | GNOME | Cinnamon | MATE | Others |
|---|---|---|---|---|---|
| Window | Yes | Yes | Yes | Yes | Yes |
| Wallpaper set automatically | Yes | Yes | Yes | Yes | Saved in Pictures only |
| Network folders in file manager side panel | Dolphin | Files | Nemo | Caja | GTK bookmarks file |

Only KDE Plasma on Fedora 45 has been used for real so far.

To run without installing, from the unpacked folder: `python3 -m nostos`.

## Updating and removing

- **Update:** `git pull` (or unpack the new version) and run `./install.sh` again. It replaces the old one. Close Nostos first.
- **Remove:** `./install.sh --remove`. This removes `/opt/nostos`, the launcher and the menu entry. It does not remove anything Nostos copied or set up for a user (see the next section).

## What Nostos puts on the Linux computer

Everything goes into the Home folder of the person who ran it.

| What | Where |
|---|---|
| Desktop, Documents, Pictures, Music, Videos, Downloads | The matching folders (as reported by `xdg-user-dir`) |
| Other profile folders and picked folders | `~/From Windows/<folder name>` |
| OneDrive folder from the PC, if ticked | `~/From Windows/OneDrive` |
| Bookmarks | `~/Documents/Bookmarks from Windows.html`; and `Default/Bookmarks` in the profile of an installed Chrome, Edge or Brave that had none |
| Wallpaper | `~/Pictures/Windows wallpaper.jpg` (or `.png`) |
| Report | `~/Documents/Moving from Windows - report.html` (replaced on each run) |
| Steam games | `~/SteamLibrary-Windows/steamapps` |
| Network folders (KDE) | `~/.local/share/user-places.xbel`; the original is kept once as `user-places.xbel.before-nostos` |
| Network folders (GTK desktops) | `~/.config/gtk-3.0/bookmarks` |
| Wi-Fi networks | NetworkManager connections named after each network |
| Programs | Flatpak, installed for this user (`flatpak install --user`) from Flathub |
| OneDrive sign-in | `~/.config/rclone/rclone.conf`, remote named `onedrive` |
| OneDrive folder | `~/OneDrive`, kept connected by `~/.config/systemd/user/nostos-onedrive.service` |
| OneDrive full download | `~/From Windows/OneDrive download` |
| Error log | `~/.cache/nostos/nostos.log` |

While a file is being copied it has a temporary name ending `.nostos-part`. It is renamed when complete, so a stopped copy never leaves a half-written file under its real name. Leftover `.nostos-part` files (after a crash or power cut) can be deleted.

To undo the OneDrive folder:

```bash
systemctl --user disable --now nostos-onedrive.service
rm ~/.config/systemd/user/nostos-onedrive.service
rclone config delete onedrive
```

## What happens on the Windows PC

**With the Nostos app (`NostosAgent.exe`):**

- Nothing is installed. The app is one file and runs from wherever it is.
- It reads a list of installed programs, fixed drives, printers, mapped drives and the Steam folder, by running a read-only PowerShell script from a temporary file that it deletes afterwards.
- If the Wi-Fi box is ticked, it asks Windows (with the administrator prompt) to export saved Wi-Fi networks to a temporary folder, reads them, and deletes the folder.
- It asks Windows not to sleep while it is connected.
- It opens a page served only to that PC (`127.0.0.1`).
- It makes no changes to files, accounts, sharing, the firewall or the registry.

**With the file-sharing helper (`Prepare this PC.cmd`):** see [The file-sharing helper](#the-file-sharing-helper). It does make temporary changes and undoes them.

## Network ports

| Port | Direction | Used for |
|---|---|---|
| TCP 47801 | Windows PC to Linux computer | The encrypted link. If the port is busy Nostos picks another and shows it after the address. |
| UDP 47800 | Windows PC to Linux computer, and the reply back | Finding Nostos automatically. Optional: the address can be typed instead. |
| TCP 445 | Linux computer to Windows PC | Windows file sharing only. |

Nothing listens on the Windows PC when the Nostos app is used. The link stays on the local network.

## The Windows app from the command line

Double-clicking is the normal way. For testing or scripting, open a Command Prompt in the app's folder:

```
NostosAgent.exe -version
NostosAgent.exe -find
NostosAgent.exe -no-ui -connect 192.168.1.50 -code K7QM-4XWD-9RTB -mode everything
NostosAgent.exe -no-ui -connect 192.168.1.50 -code K7QM-4XWD-9RTB -mode mine -wifi
NostosAgent.exe -no-ui -connect 192.168.1.50 -code K7QM-4XWD-9RTB -share "Photos=D:\Photos" -share "E:\Scans"
```

| Option | Meaning |
|---|---|
| `-find` | Look for Nostos on the network, print what answers, and exit. |
| `-no-ui` | Do not open the page; use the options below. |
| `-connect ADDRESS` | Address of the Linux computer, as shown in Nostos. Add `:PORT` if Nostos shows one. |
| `-code CODE` | The pairing code shown in Nostos. Dashes and case do not matter. |
| `-mode everything` | Share every fixed drive. |
| `-mode mine` | Share only the signed-in user's folder. The default when no `-share` is given. |
| `-share NAME=PATH` | Share one folder under a name. Repeatable. `NAME=` can be left out. |
| `-wifi` | Include saved Wi-Fi passwords (shows the administrator prompt). |
| `-manifest FILE` | Use a ready-made inventory file instead of looking at the PC (for testing). |
| `-version` | Print the version. |

It exits with 0 when Nostos finishes normally, 1 when the connection fails, 2 for a wrong option.

## The file-sharing helper

`Prepare this PC.cmd` starts `Prepare-Windows.ps1` with the permission it needs. Run the `.cmd`, not the `.ps1`.

What it sets up:

1. `NostosExport\manifest.json` in the user's folder: programs, mapped drives, printers and, unless `-NoWifi` is given, saved Wi-Fi networks with their passwords in clear text.
2. A local account named `nostos` with a random password, hidden from the sign-in screen.
3. Read-only permission for that account on the user's folder, and a share named `Nostos` of that folder.
4. Any network marked "Public" is switched to "Private", and the File and Printer Sharing firewall rules are enabled if they were off.

Pressing Enter in its window, or running `"Prepare this PC.cmd" -Undo`, removes the account, the permission, the share and the export folder, and puts the network category and firewall rules back as they were.

| Option | Meaning |
|---|---|
| `-Undo` | Remove everything the helper set up. |
| `-NoWifi` | Do not read Wi-Fi passwords. |

## How files are matched and skipped

- A file is treated as **already there** when a file of the same name exists in the destination with the same size and a modification time within two seconds. It is skipped without being transferred.
- If a file of the same name exists but differs, the existing file is left alone and the Windows file is written next to it as `name (from Windows).ext` (then `(from Windows 2)`, and so on).
- Modification times are preserved.
- Left out on purpose: `desktop.ini`, `Thumbs.db`, `NTUSER.*`, shortcuts (`.lnk`), temporary files, Office lock files (`~$…`), the recycle bin, and for Steam the `downloading`, `temp` and `shadercache` folders.
- Links and junctions on the Windows side are not followed.
- Before copying, Nostos checks free space and refuses to start unless everything fits with 2 GB to spare.

## The program table

`nostos/appmap.py` maps Windows program names to what to use on Linux. Each line is a pattern, a Linux name, a kind, an id, and an optional note:

```python
(r"handbrake", "HandBrake", "flatpak", "fr.handbrake.ghb", ""),
```

| Kind | Meaning |
|---|---|
| `flatpak` | Offered as "Install …"; the id is the Flathub app id. |
| `builtin` | Shown as "Already on this computer". |
| `web` | The report says to use the website given as the id. |
| `none` | No Linux version; the note says what to do. |

Programs that match nothing are searched for with `flatpak search` and offered unticked as possible matches. Windows components (drivers, runtimes, built-in Windows tools) are filtered out by the `IGNORE` pattern in the same file.

The Flatpak ids in the table have not each been checked against Flathub. A wrong id does no harm: the report says that program could not be installed.

## Building the Windows app

The source is in `agent/` (Go, standard library only). From Linux:

```bash
./build-agent.sh            # writes nostos/windows_helper/NostosAgent.exe
./build-agent.sh --linux    # also builds ./nostos-agent for this machine
```

Go 1.21 or newer is needed. The result is not code-signed, which is why Windows shows "Windows protected your PC" on first run.

## Tests and screenshots

```bash
python3 -m pip install --user pytest impacket     # impacket is only for the SMB test
python3 -m pytest tests -q                        # tests of the app link need Go
QT_QPA_PLATFORM=offscreen python3 tests/gui_smoke.py
python3 tools/make_screenshots.py                 # rebuilds docs/screenshots
```

What has and has not been checked on real machines is listed in the README under "Verified / unverified".
