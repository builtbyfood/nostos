// Nostos agent 0.2.3 - main.go
//
// The small app that runs on the OLD Windows PC. Double-click it, type the
// code that Nostos shows on the new computer, choose what may be copied.
//
// It can also run without a window (for testing, or for people who prefer a
// command line):
//
//	NostosAgent.exe -no-ui -connect 192.168.1.50 -code ABCD-EFGH-JKLM -mode mine
//	NostosAgent.exe -no-ui -connect HOST -code CODE -share "Photos=D:\Photos"
package main

import (
	"embed"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// Version is stamped on every build.
const Version = "0.2.3"

//go:embed ui.html inventory.ps1
var assets embed.FS

type shareList []string

func (s *shareList) String() string     { return strings.Join(*s, ",") }
func (s *shareList) Set(v string) error { *s = append(*s, v); return nil }

func main() {
	var shares shareList
	connect := flag.String("connect", "", "address of the new computer (shown in Nostos)")
	code := flag.String("code", "", "pairing code shown in Nostos")
	mode := flag.String("mode", "", "what to share: everything, mine, or custom (with -share)")
	noUI := flag.Bool("no-ui", false, "do not open the window; use the flags instead")
	wifi := flag.Bool("wifi", false, "include saved Wi-Fi passwords (asks for administrator permission)")
	manifestFile := flag.String("manifest", "", "use this inventory file instead of looking at the PC")
	showVersion := flag.Bool("version", false, "print the version")
	find := flag.Bool("find", false, "look for Nostos on the network, print what answers, and exit")
	flag.Var(&shares, "share", "share one folder as NAME=PATH (repeatable)")
	flag.Parse()

	if *showVersion {
		fmt.Println("Nostos agent", Version)
		return
	}

	if *find {
		found := Discover(2 * time.Second)
		if len(found) == 0 {
			fmt.Println("Nostos was not found on this network.")
			os.Exit(1)
		}
		for _, f := range found {
			fmt.Println(f["address"], f["name"])
		}
		return
	}

	if !*noUI {
		runUI()
		return
	}

	if *connect == "" || *code == "" {
		fmt.Fprintln(os.Stderr, "-no-ui needs -connect and -code")
		os.Exit(2)
	}
	if *mode == "" {
		*mode = "custom"
		if len(shares) == 0 {
			*mode = "mine"
		}
	}
	manifest := map[string]any{}
	if *manifestFile != "" {
		data, err := os.ReadFile(*manifestFile)
		if err == nil {
			data = []byte(strings.TrimPrefix(string(data), "\ufeff"))
			err = json.Unmarshal(data, &manifest)
		}
		if err != nil {
			fmt.Fprintln(os.Stderr, "could not read the manifest:", err)
			os.Exit(2)
		}
	} else {
		manifest = Inventory(*wifi)
	}
	roots, err := BuildRoots(*mode, shares, manifest)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	session := &Session{Roots: roots, Manifest: manifest}
	keepAwake(true)
	defer keepAwake(false)
	if err := session.Run(*connect, *code); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Printf("Finished. %d files, %d bytes sent.\n",
		session.FilesRead.Load(), session.BytesSent.Load())
}

// BuildRoots turns the user's choice into the list of shared folders.
//
//	everything  every fixed drive (C:, D:, ...)
//	mine        only this user's own folder
//	custom      exactly the folders given as NAME=PATH (or just PATH)
func BuildRoots(mode string, custom []string, manifest map[string]any) ([]Root, error) {
	roots := []Root{}
	used := map[string]bool{}
	add := func(name, path, label string) {
		name = strings.Map(func(r rune) rune {
			if strings.ContainsRune(`/\:*?"<>|`, r) {
				return '_'
			}
			return r
		}, strings.TrimSpace(name))
		if name == "" {
			name = "Folder"
		}
		base, n := name, 2
		for used[strings.ToLower(name)] {
			name = fmt.Sprintf("%s %d", base, n)
			n++
		}
		used[strings.ToLower(name)] = true
		roots = append(roots, Root{Name: name, Path: path, Label: label})
	}
	switch mode {
	case "everything":
		for _, d := range fixedDrives(manifest) {
			add(strings.TrimSuffix(d, ":"), d+string(filepath.Separator), "Drive "+d)
		}
		if len(roots) == 0 {
			return nil, fmt.Errorf("no drives were found on this PC")
		}
	case "mine":
		home, err := os.UserHomeDir()
		if err != nil {
			return nil, fmt.Errorf("could not find your user folder")
		}
		add("Profile", home, filepath.Base(home))
	case "custom":
		for _, item := range custom {
			name, path := "", item
			if i := strings.Index(item, "="); i > 0 && !strings.ContainsAny(item[:i], `\/:`) {
				name, path = item[:i], item[i+1:]
			}
			path = strings.TrimSpace(path)
			if info, err := os.Stat(path); err != nil || !info.IsDir() {
				return nil, fmt.Errorf("%q is not a folder on this PC", path)
			}
			if name == "" {
				name = filepath.Base(filepath.Clean(path))
				if len(path) <= 3 && strings.Contains(path, ":") {
					name = strings.TrimRight(path, `:\/`)
				}
			}
			add(name, path, path)
		}
		if len(roots) == 0 {
			return nil, fmt.Errorf("choose at least one folder")
		}
	default:
		return nil, fmt.Errorf("unknown mode %q", mode)
	}
	return roots, nil
}

func fixedDrives(manifest map[string]any) []string {
	out := []string{}
	if list, ok := manifest["drives"].([]any); ok {
		for _, d := range list {
			if m, ok := d.(map[string]any); ok {
				if letter, _ := m["letter"].(string); letter != "" {
					out = append(out, letter)
				}
			}
		}
	}
	if len(out) == 0 {
		out = probeDrives()
	}
	return out
}
