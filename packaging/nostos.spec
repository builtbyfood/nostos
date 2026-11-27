# Nostos 0.2.4 - nostos.spec   (UNVERIFIED: not yet built with rpmbuild)
Name:           nostos
Version:        0.2.4
Release:        1%{?dist}
Summary:        Move from Windows to Linux: files, bookmarks, Wi-Fi, apps, OneDrive
License:        Apache-2.0
URL:            https://github.com/builtbyfood/nostos
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
Requires:       python3 python3-pyside6 python3-smbprotocol python3-cryptography
Recommends:     samba-client rclone fuse3 flatpak xdg-user-dirs

%description
A step-by-step window that copies a Windows user's documents, pictures,
bookmarks, wallpaper, Wi-Fi networks and network drives to this computer
over the network or from a drive, suggests Linux replacements for Windows
programs, and connects OneDrive.

%prep
%autosetup

%install
mkdir -p %{buildroot}/opt/nostos %{buildroot}%{_bindir} %{buildroot}%{_datadir}/applications
cp -r nostos %{buildroot}/opt/nostos/
install -m 0755 packaging/nostos-launcher %{buildroot}%{_bindir}/nostos
install -m 0644 packaging/nostos.desktop %{buildroot}%{_datadir}/applications/nostos.desktop

%files
/opt/nostos
%{_bindir}/nostos
%{_datadir}/applications/nostos.desktop

%changelog
* Tue Nov 24 2026 Travis DeLuca - 0.2.4-1
- Windows app link, Steam libraries, more distributions
