# Nostos 0.2.3 - appmap.py
"""Windows program -> what to use on Fedora KDE.

kind:
  "flatpak"  one-click install from Flathub (id is the Flathub app id)
  "builtin"  already part of Fedora KDE, nothing to install
  "web"      use it in the browser
  "none"     no Linux version; note says what to do instead
Add a line here to teach Nostos a new program. Patterns are regular
expressions matched against the Windows program name, case-insensitive.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class AppMatch:
    windows: str        # name as found on Windows
    linux: str          # what to use here
    kind: str
    id: str = ""
    note: str = ""
    guess: bool = False     # found by searching Flathub, not from the table


_T = [
    # pattern, linux name, kind, id, note
    (r"google chrome", "Google Chrome", "flatpak", "com.google.Chrome", ""),
    (r"mozilla firefox|^firefox", "Firefox", "builtin", "", "Already installed."),
    (r"microsoft edge(?! webview| update)", "Microsoft Edge", "flatpak", "com.microsoft.Edge", ""),
    (r"\bbrave\b", "Brave", "flatpak", "com.brave.Browser", ""),
    (r"\bvlc\b", "VLC", "flatpak", "org.videolan.VLC", ""),
    (r"spotify", "Spotify", "flatpak", "com.spotify.Client", ""),
    (r"\bzoom\b", "Zoom", "flatpak", "us.zoom.Zoom", ""),
    (r"discord", "Discord", "flatpak", "com.discordapp.Discord", ""),
    (r"\bslack\b", "Slack", "flatpak", "com.slack.Slack", ""),
    (r"microsoft teams|^teams", "Teams for Linux", "flatpak",
     "com.github.IsmaelMartinez.teams_for_linux", "Unofficial app around the Teams website."),
    (r"telegram", "Telegram", "flatpak", "org.telegram.desktop", ""),
    (r"\bsignal\b", "Signal", "flatpak", "org.signal.Signal", ""),
    (r"whatsapp", "WhatsApp Web", "web", "https://web.whatsapp.com", ""),
    (r"\bsteam\b", "Steam", "flatpak", "com.valvesoftware.Steam", ""),
    (r"minecraft", "Minecraft", "flatpak", "com.mojang.Minecraft", ""),
    (r"libreoffice", "LibreOffice", "flatpak", "org.libreoffice.LibreOffice", ""),
    (r"microsoft (office|365)|office 16|\b(word|excel|powerpoint)( 20\d\d)?$",
     "LibreOffice (or Office on the web)", "flatpak", "org.libreoffice.LibreOffice",
     "Opens Word, Excel and PowerPoint files. Microsoft's own Office also works "
     "in the browser at office.com."),
    (r"\boutlook\b", "Thunderbird", "flatpak", "org.mozilla.Thunderbird",
     "Or use outlook.com in the browser. Mail itself stays on the mail server."),
    (r"thunderbird", "Thunderbird", "flatpak", "org.mozilla.Thunderbird", ""),
    (r"onenote", "OneNote on the web", "web", "https://www.onenote.com", ""),
    (r"\bgimp\b", "GIMP", "flatpak", "org.gimp.GIMP", ""),
    (r"photoshop", "GIMP", "flatpak", "org.gimp.GIMP",
     "Photoshop has no Linux version. GIMP is the closest free editor."),
    (r"paint\.net|^paint$|paint 3d", "Pinta", "flatpak", "com.github.PintaProject.Pinta", ""),
    (r"inkscape|illustrator", "Inkscape", "flatpak", "org.inkscape.Inkscape", ""),
    (r"\bkrita\b", "Krita", "flatpak", "org.kde.krita", ""),
    (r"audacity", "Audacity", "flatpak", "org.audacityteam.Audacity", ""),
    (r"obs studio", "OBS Studio", "flatpak", "com.obsproject.Studio", ""),
    (r"kdenlive|movie maker|clipchamp", "Kdenlive", "flatpak", "org.kde.kdenlive", ""),
    (r"blender", "Blender", "flatpak", "org.blender.Blender", ""),
    (r"calibre", "calibre", "flatpak", "com.calibre_ebook.calibre", ""),
    (r"kindle", "Kindle Cloud Reader", "web", "https://read.amazon.com", ""),
    (r"itunes", "Apple Music on the web", "web", "https://music.apple.com",
     "Music files copied from the Music folder play in Elisa, which is already installed."),
    (r"dropbox", "Dropbox", "flatpak", "com.dropbox.Client", ""),
    (r"google drive", "Google Drive in the browser", "web", "https://drive.google.com", ""),
    (r"1password", "1Password", "flatpak", "com.onepassword.OnePassword", ""),
    (r"bitwarden", "Bitwarden", "flatpak", "com.bitwarden.desktop", ""),
    (r"keepass", "KeePassXC", "flatpak", "org.keepassxc.KeePassXC", "Opens the same .kdbx file."),
    (r"visual studio code|vs ?code", "Visual Studio Code", "flatpak", "com.visualstudio.code", ""),
    (r"notepad\+\+", "Kate", "builtin", "", "Already installed."),
    (r"7-zip|winrar|winzip", "Ark", "builtin", "", "Already installed. Right-click a zip to extract."),
    (r"adobe (acrobat|reader)|foxit", "Okular", "builtin", "", "Already installed. Opens PDFs."),
    (r"putty|winscp", "Konsole and Dolphin", "builtin", "", "Already installed."),
    (r"filezilla", "FileZilla", "flatpak", "org.filezillaproject.Filezilla", ""),
    (r"qbittorrent|utorrent|bittorrent", "qBittorrent", "flatpak", "org.qbittorrent.qBittorrent", ""),
    (r"obsidian", "Obsidian", "flatpak", "md.obsidian.Obsidian", ""),
    (r"evernote", "Evernote on the web", "web", "https://www.evernote.com/client/web", ""),
    (r"zotero", "Zotero", "flatpak", "org.zotero.Zotero", ""),
    (r"anydesk", "AnyDesk", "flatpak", "com.anydesk.Anydesk", ""),
    # --- games
    (r"epic games", "Heroic Games Launcher", "flatpak", "com.heroicgameslauncher.hgl",
     "Sign in with your Epic account. Many Windows games run through Proton."),
    (r"gog galaxy|gog\.com", "Heroic Games Launcher", "flatpak", "com.heroicgameslauncher.hgl",
     "Sign in with your GOG account."),
    (r"battle\.net|ubisoft connect|uplay|ea app|\borigin\b|rockstar games", "Lutris",
     "flatpak", "net.lutris.Lutris",
     "Lutris has installers for these Windows launchers. Games with kernel anti-cheat may not run."),
    (r"xbox", "Xbox Cloud Gaming", "web", "https://www.xbox.com/play",
     "Game Pass PC installs do not move over; cloud gaming works in the browser."),
    (r"prism ?launcher|multimc|curseforge", "Prism Launcher", "flatpak",
     "org.prismlauncher.PrismLauncher", "For modded Minecraft."),
    (r"moonlight", "Moonlight", "flatpak", "com.moonlight_stream.Moonlight", ""),
    (r"geforce experience|nvidia app", "", "none", "",
     "Not needed. NVIDIA drivers come from the distribution (on Fedora: RPM Fusion)."),
    (r"msi afterburner|rivatuner", "MangoHud", "none", "",
     "Use MangoHud for the in-game overlay (install it from your software centre)."),
    # --- media
    (r"handbrake", "HandBrake", "flatpak", "fr.handbrake.ghb", ""),
    (r"\bplex\b", "Plex", "flatpak", "tv.plex.PlexDesktop", ""),
    (r"\bkodi\b", "Kodi", "flatpak", "tv.kodi.Kodi", ""),
    (r"musicbee|foobar2000|winamp|aimp|mediamonkey", "Strawberry", "flatpak",
     "org.strawberrymusicplayer.strawberry", "A music library player."),
    (r"sharex|greenshot|lightshot|snagit|snipping", "Flameshot", "flatpak",
     "org.flameshot.Flameshot", "Your desktop also has a built-in screenshot tool (Print Screen key)."),
    (r"davinci resolve", "DaVinci Resolve", "none", "",
     "Has a Linux version; download it from Blackmagic Design."),
    (r"draw\.io|diagrams\.net|visio", "draw.io", "flatpak", "com.jgraph.drawio.desktop", ""),
    # --- work and developer tools
    (r"postman", "Postman", "flatpak", "com.getpostman.Postman", ""),
    (r"github desktop", "GitHub Desktop", "flatpak", "io.github.shiftey.Desktop", ""),
    (r"arduino", "Arduino IDE", "flatpak", "cc.arduino.IDE2", ""),
    (r"wireshark", "Wireshark", "flatpak", "org.wireshark.Wireshark", ""),
    (r"remote desktop connection|mremoteng|royal ts", "Remmina", "flatpak",
     "org.remmina.Remmina", "Remote Desktop (RDP), VNC and SSH client."),
    (r"virtualbox|vmware (workstation|player)|hyper-v", "GNOME Boxes", "flatpak",
     "org.gnome.Boxes", "Simple virtual machines. virt-manager is the fuller tool."),
    (r"docker desktop", "", "none", "",
     "Use Podman (already on Fedora) or install Docker Engine from docker.com."),
    (r"\bgit\b(?! ?hub)|python \d|node\.js|windows subsystem for linux", "", "none", "",
     "Part of Linux already, or one command away in the package manager."),
    (r"rufus|balena ?etcher|win32 disk imager", "Fedora Media Writer", "flatpak",
     "org.fedoraproject.MediaWriter", ""),
    (r"rustdesk", "RustDesk", "flatpak", "com.rustdesk.RustDesk", ""),
    (r"proton ?vpn", "Proton VPN", "flatpak", "com.protonvpn.www", ""),
    (r"wireguard|openvpn", "", "none", "",
     "Built in: add the VPN in your network settings and import the config file."),
    # --- hardware tools
    (r"logitech (g hub|options|gaming)|logi options", "Solaar", "flatpak",
     "io.github.pwr_solaar.solaar", "For Logitech keyboards and mice. Piper handles gaming mice."),
    (r"icue|aura sync|armoury crate|mystic light|rgb fusion|openrgb|razer synapse",
     "OpenRGB", "flatpak", "org.openrgb.OpenRGB", "Controls RGB lighting from most brands."),
    (r"hwmonitor|hwinfo|cpu-z|speccy|crystaldisk", "Mission Center", "flatpak",
     "io.missioncenter.MissionCenter", "Shows CPU, memory, disk and GPU use."),
    # --- 3D and CAD
    (r"freecad|autocad|fusion ?360|solidworks", "FreeCAD", "flatpak", "org.freecad.FreeCAD",
     "The Autodesk and SolidWorks programs have no Linux version; FreeCAD is the free alternative."),
    (r"\bkicad\b", "KiCad", "flatpak", "org.kicad.KiCad", ""),
    (r"ultimaker cura|\bcura\b", "Cura", "flatpak", "com.ultimaker.cura", ""),
    (r"prusaslicer", "PrusaSlicer", "flatpak", "com.prusa3d.PrusaSlicer", ""),
    (r"bambu studio", "Bambu Studio", "flatpak", "com.bambulab.BambuStudio", ""),
    # --- not needed on Linux
    (r"mcafee|norton|avast|\bavg\b|malwarebytes|kaspersky|bitdefender|ccleaner|driver booster",
     "", "none", "", "Not needed on Linux."),
    (r"quicken|turbotax|quickbooks", "", "none", "",
     "No Linux version. Use the company's website version."),
    (r"cricut|silhouette studio", "", "none", "",
     "No Linux version. Cricut Design Space has no web version either; keep a "
     "Windows machine or virtual machine for it."),
]
TABLE = [(re.compile(p, re.I), *rest) for p, *rest in _T]

# Windows plumbing that should never be shown to the user as "an app".
IGNORE = re.compile(
    r"redistributable|\bruntime\b|update|driver|webview|\.net|uninstall|"
    r"^microsoft visual c|^windows |^intel|^realtek|^nvidia|^amd |^acer|"
    r"bonjour|helper|\bsdk\b|setup|installer|readme|help$|^administrative|"
    r"^accessibility|^accessories|^startup$|^system tools|^maintenance|"
    r"^microsoft (edge|onedrive|store|update|teams meeting)|vulkan|physx|directx|"
    r"openal|^hp |^dell |^lenovo|^asus |launcher prerequisites|redist|"
    r"^(calculator|calendar|camera|clock|cortana|maps|photos|settings|weather|"
    r"notepad|wordpad|file explorer|command prompt|control panel|run|"
    r"task manager|this pc|windows powershell.*|tips|get help|feedback hub|"
    r"mail|people|movies & tv|groove music|voice recorder|snip & sketch|"
    r"sticky notes|solitaire.*|your phone|phone link|narrator|magnifier|"
    r"character map|steps recorder|remote desktop connection|internet explorer|"
    r"windows media player.*|xbox game bar|game bar|mixed reality portal|"
    r"3d viewer|print 3d|alarms & clock|microsoft solitaire collection|"
    r"quick assist|on-screen keyboard|math input panel|windows fax and scan|"
    r"odbc data sources.*|iscsi initiator|services|event viewer|"
    r"component services|computer management|disk cleanup|registry editor|"
    r"resource monitor|system configuration|system information|"
    r"task scheduler|windows memory diagnostic|performance monitor|"
    r"defragment and optimize drives|recovery drive|local security policy|"
    r"print management|windows security|microsoft edge|office)$", re.I)


def match_apps(names: list[str]) -> tuple[list[AppMatch], list[str]]:
    """Return (recognised apps, names Nostos does not know)."""
    matched: dict[str, AppMatch] = {}
    unknown: list[str] = []
    for raw in sorted({n.strip() for n in names if n and n.strip()}, key=str.lower):
        for rx, linux, kind, ident, note in TABLE:
            if rx.search(raw):
                key = ident or linux or raw
                matched.setdefault(key, AppMatch(raw, linux, kind, ident, note))
                break
        else:
            if not IGNORE.search(raw):
                unknown.append(raw)
    return list(matched.values()), unknown
