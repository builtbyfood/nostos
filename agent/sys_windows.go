// Nostos agent 0.2.3 - sys_windows.go
//go:build windows

package main

import (
	"os"
	"os/exec"
	"syscall"
	"unsafe"
)

var (
	kernel32                = syscall.NewLazyDLL("kernel32.dll")
	setThreadExecutionState = kernel32.NewProc("SetThreadExecutionState")
	getDriveTypeW           = kernel32.NewProc("GetDriveTypeW")
)

// keepAwake stops Windows from going to sleep while files are being sent.
func keepAwake(on bool) {
	const esContinuous, esSystemRequired = 0x80000000, 0x00000001
	flags := uintptr(esContinuous)
	if on {
		flags |= esSystemRequired
	}
	setThreadExecutionState.Call(flags)
}

func hideWindow(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
}

func openBrowser(url string) error {
	return exec.Command("rundll32", "url.dll,FileProtocolHandler", url).Start()
}

// probeDrives is the fallback when the inventory could not list drives.
func probeDrives() []string {
	const driveFixed = 3
	out := []string{}
	for c := 'A'; c <= 'Z'; c++ {
		root := string(c) + `:\`
		ptr, _ := syscall.UTF16PtrFromString(root)
		kind, _, _ := getDriveTypeW.Call(uintptr(unsafe.Pointer(ptr)))
		if kind == driveFixed {
			if _, err := os.Stat(root); err == nil {
				out = append(out, string(c)+":")
			}
		}
	}
	return out
}
