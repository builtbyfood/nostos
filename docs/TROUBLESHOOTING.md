# Nostos troubleshooting

Version 0.2.4. Find the message you see, or the thing that is happening. For how to use Nostos, see [USER-GUIDE.md](USER-GUIDE.md).

Two things are true whatever went wrong:

- Nothing on the Windows PC has been changed.
- Anything already copied stays copied. Starting again carries on from there.

**Contents**

- [On the Windows PC](#on-the-windows-pc)
- [Connecting](#connecting)
- [The Choose page](#the-choose-page)
- [While copying](#while-copying)
- [Files that could not be copied](#files-that-could-not-be-copied)
- [After the move](#after-the-move)
- [Windows file sharing](#windows-file-sharing)
- [Getting more detail, and reporting a problem](#getting-more-detail-and-reporting-a-problem)

---

## On the Windows PC

| What you see | What it means | What to do |
|---|---|---|
| **"Windows protected your PC"** when starting NostosAgent | The app is not registered with Microsoft. | Click **More info**, then **Run anyway**. |
| Your antivirus blocks or removes NostosAgent | Same reason: it does not know the app. | Allow it in the antivirus, or use [Windows file sharing](USER-GUIDE.md#windows-file-sharing-no-app-on-windows) instead. |
| A black window opens but no web page | The browser did not start. | The black window shows an address beginning `http://127.0.0.1`. Copy it into any web browser on that PC. |
| The page says **"Open the address shown in the Nostos window"** | The page was opened without its one-time key. | Use the full address from the black window, including everything after the `?`. |
| The page shows **"This app has stopped. Start it again."** | The black window was closed. | Double-click NostosAgent again and type the code again. |
| "Do you want to allow this app to make changes?" | You ticked the Wi-Fi box; Windows only gives Wi-Fi passwords to an administrator. | Choose **Yes**, or untick the Wi-Fi box and connect without it. |

## Connecting

| What you see | Where | What to do |
|---|---|---|
| **"Still looking for the new computer…"** | Windows app | 1. Check Nostos is open on the Linux computer and showing a code. 2. Check both are on the same network (not one on a guest Wi-Fi). 3. Click **"Type the address myself"** and type the address shown under the code in Nostos. |
| **"The new computer was not found automatically…"** | Windows app, after pressing Connect | Same as above: type the address. |
| **"Could not reach the new computer at …"** | Windows app | The address is wrong, Nostos is not waiting, or a firewall on the Linux computer is in the way. See [Firewall on the Linux computer](#firewall-on-the-linux-computer). |
| **"The code does not match the one shown in Nostos"** | Windows app | Type the code again. If you went Back in Nostos or restarted it, the code changed: use the one on screen now. |
| **"That address answered, but it is not Nostos"** | Windows app | The address belongs to a different device. Use the one shown in Nostos. |
| **"The other computer could not prove it knows the code. Stopped for safety"** | Windows app | Something other than your Nostos answered. Do not continue on this network until you know why. On a home network this should never appear. |
| **"The connection to the new computer was lost"** | Windows app | Nostos was closed, or the network dropped. Open Nostos again, press **Try again** in the Windows app, and type the new code. |
| **"Could not start waiting for the Windows PC"** | Nostos | Close Nostos and start it again. If it repeats, [send the log](#getting-more-detail-and-reporting-a-problem). |
| **"The Windows app (NostosAgent.exe) is missing from this copy of Nostos"** | Nostos, when writing the USB stick | This copy was installed from source without the built app. See [REFERENCE.md](REFERENCE.md#building-the-windows-app). |
| **"Could not write to that drive"** | Nostos, when writing the USB stick | The stick is read-only or full. Try another stick, or copy `NostosAgent.exe` to the Windows PC any other way. |

### Firewall on the Linux computer

The Windows app connects to the Linux computer on TCP port 47801, and finds it using UDP port 47800. Fedora Workstation and Fedora KDE allow these by default. If your Linux computer blocks incoming connections, open them for this session.

With firewalld (Fedora, openSUSE); these last until the next restart:

```bash
sudo firewall-cmd --add-port=47801/tcp
sudo firewall-cmd --add-port=47800/udp
```

With ufw (Ubuntu, Mint):

```bash
sudo ufw allow 47801/tcp
sudo ufw allow 47800/udp
```

To check from the Windows PC whether Nostos can be found, open a Command Prompt in the folder with the app and run:

```
NostosAgent.exe -find
```

It prints the address and name of each Nostos it finds, or says none was found.

## The Choose page

| What you see | What it means | What to do |
|---|---|---|
| **"Looking at what is there…"** for a long time | Nostos is reading the PC and searching the app store for programs it does not know. | Wait a minute or two. On a very slow Wi-Fi link it can take longer. |
| A red box: **"Everything below is ready to use. These could not be checked and are left out: …"** | One kind of thing (for example Steam, or the app store search) could not be worked out. | You can carry on; only the named part is missing. To get it fixed, [send the log](#getting-more-detail-and-reporting-a-problem). |
| A blue box: **"Tip: files and bookmarks are ready to copy…"** | You connected by file sharing or a drive without the helper, so programs, Wi-Fi and network drives are not available. | Carry on, or go back and use the Nostos app on Windows. |
| No **Games** section | Steam was not found, or its folder was not shared. | In the Windows app choose **Everything on this PC**, then connect again. |
| No **Saved Wi-Fi networks** line | The Wi-Fi box was not ticked in the Windows app. | Connect again with it ticked. |
| A folder you expected is not listed | It is outside your Windows user folder. | Press **Choose more folders…** and tick it. |
| Only the folders you picked are listed, with no Desktop or Documents | In the Windows app you chose "Only folders I pick" and did not include your user folder. | That is fine if intended. Otherwise connect again with a wider choice. |
| **"OneDrive needs a small extra piece called rclone"** | OneDrive support is not installed. | Install `rclone` with your package manager (on Fedora: `sudo dnf install rclone`), then start Nostos again. |
| **"Tick at least one thing to bring over."** | Nothing is ticked. | Tick something. |

## While copying

| What you see | What it means | What to do |
|---|---|---|
| **"There is not enough room on this computer"** | The ticked things are bigger than the free space (Nostos keeps 2 GB spare). | Go back and untick something large: Videos, Pictures and Steam games are usually the biggest. Or free up space first. |
| It is very slow | Almost always the network. | Use a network cable on both computers if you can. Press **Stop**, plug in, and start again; it carries on. |
| The speed shows nothing for a while at the start | Files already copied on an earlier run are being skipped. | Nothing; the speed appears once new files start. |
| The time left jumps around | Many small files copy more slowly than a few large ones. | Nothing; it settles. |
| **"The connection to the Windows PC was lost"** | The Windows PC went to sleep, lost Wi-Fi, or the app was closed. | Wake the PC, start the Windows app again, and run Nostos again with the new code. Files already copied are skipped. |
| **"Something went wrong:"** with other text | An unexpected error. | Note the text and [send the log](#getting-more-detail-and-reporting-a-problem). Starting again is safe. |
| A sign-in page opens in the browser | You ticked OneDrive. | Sign in with your Microsoft account and allow access. |
| It seems stuck on **"Installing …"** | A program is being downloaded; large ones take minutes. | Wait. If it truly never finishes, press **Stop**; the files are already copied. |

## Files that could not be copied

The report lists each file with one of these reasons.

| Reason | What it means | What to do |
|---|---|---|
| **in use on the Windows PC** | A program has the file open and locked (often Outlook data, or a document left open). | Close the program on Windows and run Nostos again. |
| **Windows would not allow it to be read** | The Windows account does not have permission for that file. | Usually system files you do not need. If it is yours, copy it by hand on a USB stick. |
| **stored only in OneDrive, not on the Windows PC** | The file shows in the folder but its contents are in the cloud (cloud icon in Windows). | Connect OneDrive in Nostos, or on Windows right-click the folder and choose **Always keep on this device**, wait, and run again. |
| **this computer is out of space** | The disk filled up during the copy. | Free up space and run again. |
| Anything else | An error Nostos does not have plain words for. | Run again; if it repeats, [report it](#getting-more-detail-and-reporting-a-problem). |

**"Folders Windows would not open"** in the report are usually system folders inside your user folder. They can be ignored unless you recognise one as yours.

## After the move

| Problem | What to do |
|---|---|
| A file seems to be missing | Check **From Windows** in Home, and look for a copy with **(from Windows)** in its name next to an older file. Then check the report's "could not be copied" list. |
| Two copies of a file, one named "(from Windows)" | A different file with that name was already on the Linux computer. Both were kept. Open both and delete the one you do not want. |
| Bookmarks did not appear in the browser | Import **Bookmarks from Windows.html** from Documents: bookmarks menu, **Import**, **from HTML file**. |
| A program "could not be installed automatically" | Open your software centre and search for the name given in the report. |
| A "possible match" you ticked is the wrong program | Remove it in your software centre. Nothing else is affected. |
| A network folder asks for a password | Use the same name and password you used on Windows for that drive. |
| A Wi-Fi network was not remembered | The report lists networks that need a sign-in. Join them once by hand. |
| Steam does not show the copied games | Check you added **SteamLibrary-Windows** under Settings > Storage and turned on Steam Play for all titles. If it still does not, delete the folder and let Steam download them. |
| The OneDrive folder is empty or missing | Check the report's "Things left for you to do". OneDrive support is not yet confirmed working; please [report](#getting-more-detail-and-reporting-a-problem) what it says. |
| The wallpaper did not change | It is saved in Pictures as **Windows wallpaper**. Right-click the desktop to set it. |

## Windows file sharing

| What you see in Nostos | What to do |
|---|---|
| **"Could not find a computer called …"** | Type the PC's address instead of its name. The helper window shows it; otherwise on Windows open Settings > Network > Properties and look for "IPv4 address". |
| **"Could not reach …"** | Check both computers are on the same network and the Windows PC is awake. |
| **"The Windows PC said no to that name and password."** | Check them against the helper window. With your own account, use the account's real password, not a PIN. |
| **"The Windows PC was found, but it has no shared folder called …"** | Run **Prepare this PC** on Windows first, or tick "I shared a folder myself" and type the real share name. |
| **"Connected, but no Windows user folders were found in that shared folder."** | The share does not contain a user folder. Share `C:\Users`, or the user's own folder. |
| Nothing in the "Windows PCs found" list | That is fine: type the name or address below the list. |

On Windows:

| What you see | What to do |
|---|---|
| "…cannot be loaded because running scripts is disabled on this system" | You ran `Prepare-Windows.ps1` directly. Double-click **Prepare this PC** (the `.cmd` file) instead. |
| The helper window shows red text | Nothing in your files was changed. Run `"Prepare this PC.cmd" -Undo` to remove anything it set up, then try again or use the Nostos app. |
| You closed the helper window before pressing Enter | Run `"Prepare this PC.cmd" -Undo` from the same folder. |
| Connecting to `C$` is refused | Windows blocks administrator shares for ordinary accounts by default. Use the Nostos app, which does not need them. |

## Getting more detail, and reporting a problem

Nostos writes the full detail of unexpected errors to a log file on the Linux computer:

```
~/.cache/nostos/nostos.log
```

To see the latest entries, open a terminal and run:

```bash
tail -40 ~/.cache/nostos/nostos.log
```

When reporting a problem, include:

1. The Nostos version (bottom of the Start page, or `nostos --version`).
2. The Linux distribution and desktop, and the Windows version.
3. Which way you connected (Nostos app, file sharing, drive, OneDrive).
4. Which page it happened on, and the exact message.
5. The last lines of the log file.
6. If files were skipped, the "could not be copied" part of the report.

The log holds file names and error text. Nostos does not write passwords or the pairing code to it.
