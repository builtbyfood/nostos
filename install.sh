#!/usr/bin/env bash
# Nostos 0.2.4 - install.sh
# Installs Nostos for every user of this computer.
# Fedora, Debian/Ubuntu/Mint, Arch and openSUSE families are recognised;
# anything else falls back to a private Python environment.
#
#   ./install.sh            install
#   ./install.sh --dry-run  show what would be done
#   ./install.sh --remove   uninstall
set -uo pipefail

VERSION="0.2.4"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="/opt/nostos"
DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

run() { if (( DRY )); then echo "would run: $*"; else "$@"; fi; }

if [[ "${1:-}" == "--remove" ]]; then
    sudo rm -rf "$DEST"
    sudo rm -f /usr/local/bin/nostos
    sudo rm -f /usr/share/applications/nostos.desktop
    echo "Nostos removed."
    exit 0
fi

echo "Installing Nostos $VERSION"

# Package names per family. REQUIRED: Python, the window toolkit, the two
# network libraries. OPTIONAL: share listing, OneDrive, app installs.
if command -v dnf >/dev/null 2>&1; then
    FAMILY="Fedora"; INSTALL=(sudo dnf install -y)
    REQUIRED=(python3 python3-pyside6 python3-smbprotocol python3-cryptography)
    OPTIONAL=(samba-client rclone fuse3 flatpak xdg-user-dirs)
elif command -v apt-get >/dev/null 2>&1; then
    FAMILY="Debian/Ubuntu"; INSTALL=(sudo apt-get install -y)
    REQUIRED=(python3 python3-venv python3-pyside6.qtwidgets python3-pyside6.qtgui
              python3-pyside6.qtcore python3-smbprotocol python3-cryptography)
    OPTIONAL=(smbclient rclone fuse3 flatpak xdg-user-dirs)
elif command -v pacman >/dev/null 2>&1; then
    FAMILY="Arch"; INSTALL=(sudo pacman -S --needed --noconfirm)
    REQUIRED=(python pyside6 python-smbprotocol python-cryptography)
    OPTIONAL=(smbclient rclone fuse3 flatpak xdg-user-dirs)
elif command -v zypper >/dev/null 2>&1; then
    FAMILY="openSUSE"; INSTALL=(sudo zypper --non-interactive install)
    REQUIRED=(python3 python3-pyside6 python3-smbprotocol python3-cryptography)
    OPTIONAL=(samba-client rclone fuse3 flatpak xdg-user-dirs)
else
    FAMILY="unknown"; INSTALL=()
    REQUIRED=(); OPTIONAL=()
fi
echo "Package family: $FAMILY"

# One package at a time, so one missing name does not stop the rest.
for pkg in "${REQUIRED[@]}" "${OPTIONAL[@]}"; do
    if (( DRY )); then
        echo "would run: ${INSTALL[*]} $pkg"
    else
        echo "  $pkg"
        "${INSTALL[@]}" "$pkg" >/dev/null 2>&1 || echo "  note: package $pkg was not installed"
    fi
done

run sudo rm -rf "$DEST"
run sudo mkdir -p "$DEST"
run sudo cp -r "$HERE/nostos" "$DEST/"
run sudo find "$DEST" -name __pycache__ -type d -prune -exec rm -rf {} +
run sudo install -m 0755 "$HERE/packaging/nostos-launcher" /usr/local/bin/nostos
run sudo install -m 0644 "$HERE/packaging/nostos.desktop" /usr/share/applications/nostos.desktop
run sudo update-desktop-database /usr/share/applications >/dev/null 2>&1 || true

# If the distribution packages did not provide everything, build a private
# Python environment just for Nostos (leaves the system Python alone).
CHECK='import PySide6.QtWidgets, smbclient, cryptography'
if (( ! DRY )) && ! python3 -c "$CHECK" >/dev/null 2>&1; then
    echo "Some Python parts are not packaged here; setting up a private environment."
    sudo python3 -m venv --system-site-packages "$DEST/venv" || {
        echo "Could not create the environment. Install your distribution's python3-venv package and run this again."
        exit 1
    }
    sudo "$DEST/venv/bin/python" -m pip install --quiet --upgrade pip
    sudo "$DEST/venv/bin/python" -m pip install --quiet PySide6 smbprotocol cryptography || {
        echo "Could not download the Python parts. Check the internet connection and run this again."
        exit 1
    }
fi

if (( ! DRY )); then
    [[ -f "$DEST/nostos/windows_helper/NostosAgent.exe" ]] || \
        echo "note: NostosAgent.exe is missing; build it with ./build-agent.sh (needs Go) and install again."
    /usr/local/bin/nostos --version || exit 1
    echo
    echo "Done. Find \"Nostos\" in the application menu, or run: nostos"
    echo "If this computer runs a firewall that blocks incoming connections, the"
    echo "Windows app needs TCP port 47801 and UDP port 47800 open on this side."
fi
