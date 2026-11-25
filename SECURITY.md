# Security

Nostos reads a Windows profile over the network and writes into the home folder of whoever runs it. Things worth knowing:

- **Nostos app on Windows (recommended path):** the Windows app connects out to Nostos; nothing on Windows listens for connections. The link is TLS with a certificate made for that session, and both sides must prove they know the 12-character pairing code shown in Nostos; the proof is bound to the certificate. The protocol has only "info", "list" and "read", and the app serves only the folders its user chose. The app's own page is served to the Windows PC itself (127.0.0.1) and needs a one-time token.
- Wi-Fi passwords are sent only if the box is ticked in the Windows app, travel inside the encrypted link, and are never written to disk on the Windows side beyond the moment Windows exports them.
- **Windows file sharing path:** the Windows side is opened read-only. The helper creates a temporary local account with a random password, read-only on one profile folder, and removes it when you press Enter (or with `"Prepare this PC.cmd" -Undo`).
- While the helper is waiting, `NostosExport\manifest.json` in the Windows profile holds saved Wi-Fi passwords in clear text. The helper deletes that folder on clean-up. Use `-NoWifi` to leave Wi-Fi out.
- The password typed into Nostos is kept in memory for the session only and is never written to disk.
- OneDrive sign-in is handled by rclone; its token is stored in `~/.config/rclone/rclone.conf`.

## Reporting a problem

Please open a private security advisory on the GitHub repository rather than a public issue.
