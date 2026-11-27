// Nostos agent 0.2.4 - sys_other.go
// Stand-ins so the agent also builds on Linux and macOS for testing.
//go:build !windows

package main

import "os/exec"

func keepAwake(on bool)        {}
func hideWindow(cmd *exec.Cmd) {}

func openBrowser(url string) error {
	return exec.Command("xdg-open", url).Start()
}

func probeDrives() []string { return []string{} }
