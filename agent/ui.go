// Nostos agent 0.2.4 - ui.go
// The window. It is a page in the PC's own web browser, served only to this
// PC (127.0.0.1) and protected by a one-time token, so nothing else on the
// network or in another browser tab can drive it.
package main

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"
)

type uiServer struct {
	token    string
	mu       sync.Mutex
	session  *Session
	manifest map[string]any
	ready    bool
	quit     chan struct{}
}

func runUI() {
	raw := make([]byte, 16)
	rand.Read(raw)
	ui := &uiServer{token: hex.EncodeToString(raw), quit: make(chan struct{})}

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		fmt.Println("Could not start:", err)
		os.Exit(1)
	}
	url := fmt.Sprintf("http://%s/?t=%s", listener.Addr().String(), ui.token)

	mux := http.NewServeMux()
	mux.HandleFunc("/", ui.page)
	mux.HandleFunc("/api/state", ui.guard(ui.state))
	mux.HandleFunc("/api/discover", ui.guard(ui.discover))
	mux.HandleFunc("/api/browse", ui.guard(ui.browse))
	mux.HandleFunc("/api/connect", ui.guard(ui.connect))
	mux.HandleFunc("/api/quit", ui.guard(func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, map[string]any{"ok": true})
		close(ui.quit)
	}))
	go http.Serve(listener, mux)

	go func() { // look at the PC while the user reads the first screen
		m := Inventory(false)
		ui.mu.Lock()
		ui.manifest, ui.ready = m, true
		ui.mu.Unlock()
	}()

	fmt.Println()
	fmt.Println("  Nostos - moving to a new computer")
	fmt.Println()
	fmt.Println("  A page has opened in your web browser. Use that page.")
	fmt.Println("  Keep this window open until the move is finished.")
	fmt.Println("  Closing this window stops everything straight away.")
	fmt.Println()
	fmt.Println("  If no page opened, copy this address into your browser:")
	fmt.Println("  " + url)
	fmt.Println()
	openBrowser(url)
	<-ui.quit
	keepAwake(false)
	time.Sleep(300 * time.Millisecond)
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(v)
}

func (ui *uiServer) page(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" || r.URL.Query().Get("t") != ui.token {
		http.Error(w, "Open the address shown in the Nostos window.", http.StatusForbidden)
		return
	}
	data, _ := assets.ReadFile("ui.html")
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	w.Write(data)
}

func (ui *uiServer) guard(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Nostos-Token") != ui.token {
			http.Error(w, "forbidden", http.StatusForbidden)
			return
		}
		next(w, r)
	}
}

func (ui *uiServer) state(w http.ResponseWriter, r *http.Request) {
	ui.mu.Lock()
	defer ui.mu.Unlock()
	home, _ := os.UserHomeDir()
	out := map[string]any{"version": Version, "ready": ui.ready, "home": home,
		"session": map[string]any{"state": ""}}
	if ui.manifest != nil {
		out["computer"] = ui.manifest["computer"]
		out["user"] = ui.manifest["user"]
		out["drives"] = fixedDrives(ui.manifest)
		if apps, ok := ui.manifest["apps"].([]any); ok {
			out["apps"] = len(apps)
		}
	}
	if ui.session != nil {
		out["session"] = ui.session.Snapshot()
	}
	writeJSON(w, out)
}

func (ui *uiServer) discover(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, map[string]any{"found": Discover(1500 * time.Millisecond)})
}

// browse lists the folders inside a folder, for the "choose folders" picker.
func (ui *uiServer) browse(w http.ResponseWriter, r *http.Request) {
	path := r.URL.Query().Get("path")
	dirs := []map[string]string{}
	if path == "" {
		ui.mu.Lock()
		drives := fixedDrives(ui.manifest)
		ui.mu.Unlock()
		for _, d := range drives {
			dirs = append(dirs, map[string]string{"name": d, "path": d + string(filepath.Separator)})
		}
		if home, err := os.UserHomeDir(); err == nil {
			dirs = append([]map[string]string{{"name": "My files (" + filepath.Base(home) + ")", "path": home}}, dirs...)
		}
		writeJSON(w, map[string]any{"path": "", "parent": "", "dirs": dirs})
		return
	}
	items, err := os.ReadDir(path)
	if err != nil {
		writeJSON(w, map[string]any{"path": path, "parent": filepath.Dir(path), "dirs": dirs,
			"error": "This folder cannot be opened."})
		return
	}
	for _, it := range items {
		if it.Type().IsDir() && !strings.HasPrefix(it.Name(), "$") {
			dirs = append(dirs, map[string]string{"name": it.Name(), "path": filepath.Join(path, it.Name())})
		}
	}
	sort.Slice(dirs, func(i, j int) bool {
		return strings.ToLower(dirs[i]["name"]) < strings.ToLower(dirs[j]["name"])
	})
	parent := filepath.Dir(path)
	if parent == path {
		parent = ""
	}
	writeJSON(w, map[string]any{"path": path, "parent": parent, "dirs": dirs})
}

func (ui *uiServer) connect(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Code    string   `json:"code"`
		Address string   `json:"address"`
		Mode    string   `json:"mode"`
		Folders []string `json:"folders"`
		Wifi    bool     `json:"wifi"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, map[string]any{"ok": false, "error": "bad request"})
		return
	}
	if len(NormalizeCode(req.Code)) < 8 {
		writeJSON(w, map[string]any{"ok": false, "error": "Type the code shown in Nostos on the new computer."})
		return
	}
	ui.mu.Lock()
	if ui.session != nil {
		st := ui.session.Snapshot()["state"]
		if st == "connecting" || st == "connected" {
			ui.mu.Unlock()
			writeJSON(w, map[string]any{"ok": false, "error": "Already connected."})
			return
		}
	}
	manifest := ui.manifest
	ui.mu.Unlock()
	if manifest == nil {
		manifest = Inventory(false)
	}
	address := strings.TrimSpace(req.Address)
	if address == "" {
		found := Discover(2 * time.Second)
		if len(found) == 0 {
			writeJSON(w, map[string]any{"ok": false, "error": "The new computer was not found automatically. " +
				"Type its address: Nostos shows it under the code (it looks like 192.168.1.50)."})
			return
		}
		address = found[0]["address"]
	}
	roots, err := BuildRoots(req.Mode, req.Folders, manifest)
	if err != nil {
		writeJSON(w, map[string]any{"ok": false, "error": err.Error()})
		return
	}
	if req.Wifi {
		manifest["wifi"] = wifiProfiles()
	}
	session := &Session{Roots: roots, Manifest: manifest}
	session.setState("connecting", "")
	ui.mu.Lock()
	ui.session = session
	ui.mu.Unlock()
	go func() {
		keepAwake(true)
		defer keepAwake(false)
		if err := session.Run(address, req.Code); err != nil {
			session.setState("error", err.Error())
		}
	}()
	writeJSON(w, map[string]any{"ok": true})
}
