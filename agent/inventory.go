// Nostos agent 0.2.3 - inventory.go
// What is on this PC: programs, drives, printers, Wi-Fi. Windows only; on
// other systems (used for testing) it returns an almost empty inventory.
package main

import (
	"bytes"
	"encoding/json"
	"encoding/xml"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
)

// Inventory looks at the PC. It never fails: whatever could not be read is
// simply left out.
func Inventory(withWifi bool) map[string]any {
	host, _ := os.Hostname()
	home, _ := os.UserHomeDir()
	manifest := map[string]any{
		"version": 2, "computer": host, "profile": home,
		"user": filepath.Base(home), "apps": []any{}, "wifi": []any{},
	}
	if runtime.GOOS != "windows" {
		return manifest
	}
	// The script is written to a temporary file and run with -File: feeding
	// a multi-line script to PowerShell on standard input is unreliable.
	script, _ := assets.ReadFile("inventory.ps1")
	tmp, err := os.MkdirTemp("", "nostos-inv-")
	if err != nil {
		return manifest
	}
	defer os.RemoveAll(tmp)
	file := filepath.Join(tmp, "inventory.ps1")
	if os.WriteFile(file, script, 0o600) != nil {
		return manifest
	}
	cmd := exec.Command("powershell.exe", "-NoProfile", "-NonInteractive",
		"-ExecutionPolicy", "Bypass", "-File", file)
	hideWindow(cmd)
	out, err := cmd.Output()
	if err == nil {
		if i := bytes.IndexByte(out, '{'); i >= 0 {
			parsed := map[string]any{}
			if json.Unmarshal(out[i:], &parsed) == nil {
				for _, key := range []string{"computer", "user", "profile"} {
					if v, _ := parsed[key].(string); v == "" {
						parsed[key] = manifest[key]
					}
				}
				manifest = parsed
			}
		}
	}
	if withWifi {
		manifest["wifi"] = wifiProfiles()
	}
	return manifest
}

type wlanProfile struct {
	SSID string `xml:"SSIDConfig>SSID>name"`
	Auth string `xml:"MSM>security>authEncryption>authentication"`
	Key  string `xml:"MSM>security>sharedKey>keyMaterial"`
}

// wifiProfiles exports saved Wi-Fi networks with their passwords. Windows
// only gives out the passwords to an administrator, so this shows the
// "Do you want to allow..." prompt once. The export files are deleted as
// soon as they have been read.
func wifiProfiles() []any {
	out := []any{}
	tmp, err := os.MkdirTemp("", "nostos-wifi-")
	if err != nil {
		return out
	}
	defer os.RemoveAll(tmp)
	ps := `Start-Process -FilePath netsh.exe -Verb RunAs -Wait -WindowStyle Hidden ` +
		`-ArgumentList 'wlan','export','profile','key=clear','folder="` + tmp + `"'`
	cmd := exec.Command("powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
		"-Command", ps)
	hideWindow(cmd)
	if cmd.Run() != nil {
		return out
	}
	files, _ := filepath.Glob(filepath.Join(tmp, "*.xml"))
	for _, f := range files {
		data, err := os.ReadFile(f)
		if err != nil {
			continue
		}
		var p wlanProfile
		if xml.Unmarshal(data, &p) == nil && strings.TrimSpace(p.SSID) != "" {
			out = append(out, map[string]any{"ssid": p.SSID, "auth": p.Auth, "key": p.Key})
		}
	}
	return out
}
