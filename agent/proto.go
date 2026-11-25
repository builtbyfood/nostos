// Nostos agent 0.2.3 - proto.go
//
// The link between this (Windows) app and Nostos on the new computer.
//
//   - This app dials OUT to Nostos, so Windows needs no sharing, no firewall
//     rule and no account changes.
//   - The connection is TLS. Nostos uses a throw-away certificate; both sides
//     then prove they know the pairing code with an HMAC that is bound to that
//     certificate, so a machine in the middle with its own certificate fails.
//   - After that Nostos asks and this app answers: "info", "list", "read".
//     There is no write, rename or delete operation in the protocol at all,
//     and only paths under the folders the user chose are served.
package main

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

const (
	protoVersion = 1
	maxFrame     = 16 << 20
	maxRead      = 8 << 20
)

// Root is one folder (or whole drive) the user agreed to share.
type Root struct {
	Name  string `json:"name"`  // first path component Nostos uses: "C", "Profile"
	Path  string `json:"path"`  // real path on this PC: `C:\`
	Label string `json:"label"` // shown to the user
}

type request struct {
	Op   string `json:"op"`
	Path string `json:"path,omitempty"`
	Off  int64  `json:"off,omitempty"`
	Len  int    `json:"len,omitempty"`
}

type entry struct {
	N string  `json:"n"`
	D bool    `json:"d"`
	S int64   `json:"s"`
	M float64 `json:"m"`
}

// Session is one connection to Nostos.
type Session struct {
	Roots    []Root
	Manifest map[string]any

	BytesSent atomic.Int64
	FilesRead atomic.Int64
	mu        sync.Mutex
	current   string
	state     string // "", "connecting", "connected", "done", "error"
	errText   string
	peer      string

	conn     net.Conn
	openPath string
	openFile *os.File
}

func (s *Session) setState(state, detail string) {
	s.mu.Lock()
	s.state = state
	if state == "error" {
		s.errText = detail
	} else if detail != "" {
		s.peer = detail
	}
	s.mu.Unlock()
}

// Snapshot is what the local window shows.
func (s *Session) Snapshot() map[string]any {
	s.mu.Lock()
	defer s.mu.Unlock()
	return map[string]any{
		"state": s.state, "error": s.errText, "peer": s.peer,
		"current": s.current, "bytes": s.BytesSent.Load(), "files": s.FilesRead.Load(),
	}
}

// NormalizeCode makes "abcd-efgh jklm" and "ABCDEFGHJKLM" the same thing.
func NormalizeCode(code string) string {
	var b strings.Builder
	for _, r := range strings.ToUpper(code) {
		if (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9') {
			b.WriteRune(r)
		}
	}
	return b.String()
}

func proof(code, who string, fingerprint []byte, nonceServer, nonceAgent string) string {
	mac := hmac.New(sha256.New, []byte(NormalizeCode(code)))
	mac.Write([]byte(who))
	mac.Write([]byte{0})
	mac.Write(fingerprint)
	mac.Write([]byte{0})
	mac.Write([]byte(nonceServer))
	mac.Write([]byte{0})
	mac.Write([]byte(nonceAgent))
	return hex.EncodeToString(mac.Sum(nil))
}

func writeMsg(w io.Writer, v any) error {
	data, err := json.Marshal(v)
	if err != nil {
		return err
	}
	head := make([]byte, 4)
	binary.BigEndian.PutUint32(head, uint32(len(data)))
	if _, err := w.Write(append(head, data...)); err != nil {
		return err
	}
	return nil
}

func readMsg(r io.Reader, v any) error {
	head := make([]byte, 4)
	if _, err := io.ReadFull(r, head); err != nil {
		return err
	}
	n := binary.BigEndian.Uint32(head)
	if n > maxFrame {
		return errors.New("message too large")
	}
	data := make([]byte, n)
	if _, err := io.ReadFull(r, data); err != nil {
		return err
	}
	return json.Unmarshal(data, v)
}

// Run connects to Nostos at addr ("192.168.1.50:47801"), pairs with the code
// and then serves requests until Nostos says goodbye or the link drops.
func (s *Session) Run(addr, code string) error {
	s.setState("connecting", "")
	if !strings.Contains(addr, ":") {
		addr += ":47801"
	}
	dialer := &net.Dialer{Timeout: 10 * time.Second}
	conn, err := tls.DialWithDialer(dialer, "tcp", addr, &tls.Config{
		// The certificate is a throw-away one; it is authenticated by the
		// pairing-code proof below instead of by a certificate authority.
		InsecureSkipVerify: true,
		MinVersion:         tls.VersionTLS12,
	})
	if err != nil {
		return fmt.Errorf("Could not reach the new computer at %s. Check that Nostos is open there and showing a code, and that both computers are on the same network", addr)
	}
	defer conn.Close()
	s.conn = conn
	certs := conn.ConnectionState().PeerCertificates
	if len(certs) == 0 {
		return errors.New("The other side did not identify itself")
	}
	fp := sha256.Sum256(certs[0].Raw)

	var hello struct {
		Hello string `json:"hello"`
		V     int    `json:"v"`
		Nonce string `json:"nonce"`
		Name  string `json:"name"`
	}
	conn.SetDeadline(time.Now().Add(20 * time.Second))
	if err := readMsg(conn, &hello); err != nil || hello.Hello != "nostos" {
		return errors.New("That address answered, but it is not Nostos")
	}
	nonceBytes := make([]byte, 16)
	if _, err := rand.Read(nonceBytes); err != nil {
		return err
	}
	nonce := hex.EncodeToString(nonceBytes)
	host, _ := os.Hostname()
	if err := writeMsg(conn, map[string]any{
		"hello": "agent", "v": protoVersion, "nonce": nonce,
		"proof":    proof(code, "agent", fp[:], hello.Nonce, nonce),
		"computer": host, "version": Version,
	}); err != nil {
		return err
	}
	var reply struct {
		OK    bool   `json:"ok"`
		Proof string `json:"proof"`
		Error string `json:"error"`
	}
	if err := readMsg(conn, &reply); err != nil {
		return errors.New("The new computer closed the connection. Check the code and try again")
	}
	if !reply.OK {
		return errors.New("The code does not match the one shown in Nostos. Check it and try again")
	}
	want := proof(code, "server", fp[:], hello.Nonce, nonce)
	if !hmac.Equal([]byte(reply.Proof), []byte(want)) {
		return errors.New("The other computer could not prove it knows the code. Stopped for safety")
	}
	conn.SetDeadline(time.Time{})
	name := hello.Name
	if name == "" {
		name = addr
	}
	s.setState("connected", name)
	defer s.closeFile()

	for {
		var req request
		if err := readMsg(conn, &req); err != nil {
			if errors.Is(err, io.EOF) {
				s.setState("done", "")
				return nil
			}
			return errors.New("The connection to the new computer was lost")
		}
		switch req.Op {
		case "bye":
			writeMsg(conn, map[string]any{"ok": true})
			s.setState("done", "")
			return nil
		case "info":
			err = writeMsg(conn, map[string]any{"ok": true, "roots": s.Roots,
				"manifest": s.Manifest, "version": Version})
		case "list":
			err = s.handleList(req)
		case "read":
			err = s.handleRead(req)
		default:
			err = writeMsg(conn, map[string]any{"ok": false, "error": "unknown request"})
		}
		if err != nil {
			return errors.New("The connection to the new computer was lost")
		}
	}
}

// resolve turns "C/Users/Dana" into `C:\Users\Dana`, refusing anything
// outside the shared roots.
func (s *Session) resolve(path string) (string, error) {
	parts := []string{}
	for _, p := range strings.Split(path, "/") {
		if p == "" {
			continue
		}
		if p == "." || p == ".." || strings.ContainsAny(p, `\:`) {
			return "", errors.New("not allowed")
		}
		parts = append(parts, p)
	}
	if len(parts) == 0 {
		return "", errors.New("root")
	}
	for _, r := range s.Roots {
		if strings.EqualFold(r.Name, parts[0]) {
			return filepath.Join(append([]string{r.Path}, parts[1:]...)...), nil
		}
	}
	return "", errors.New("not shared")
}

func (s *Session) handleList(req request) error {
	entries := []entry{}
	if strings.Trim(req.Path, "/") == "" {
		for _, r := range s.Roots {
			entries = append(entries, entry{N: r.Name, D: true})
		}
		return writeMsg(s.conn, map[string]any{"ok": true, "entries": entries})
	}
	real, err := s.resolve(req.Path)
	if err != nil {
		return writeMsg(s.conn, map[string]any{"ok": false, "error": err.Error()})
	}
	items, err := os.ReadDir(real)
	if err != nil {
		return writeMsg(s.conn, map[string]any{"ok": false, "error": shortErr(err)})
	}
	for _, it := range items {
		mode := it.Type()
		if mode&os.ModeSymlink != 0 {
			continue // links and junctions lead to loops or "access denied"
		}
		if mode.IsDir() {
			entries = append(entries, entry{N: it.Name(), D: true})
			continue
		}
		var info os.FileInfo
		if mode&os.ModeIrregular != 0 {
			// Junctions ("My Documents") resolve to folders: skip those.
			// Cloud placeholders resolve to ordinary files: keep those.
			info, err = os.Stat(filepath.Join(real, it.Name()))
			if err != nil || info.IsDir() {
				continue
			}
		} else if mode.IsRegular() {
			info, err = it.Info()
			if err != nil {
				continue
			}
		} else {
			continue
		}
		entries = append(entries, entry{N: it.Name(), S: info.Size(),
			M: float64(info.ModTime().UnixNano()) / 1e9})
	}
	return writeMsg(s.conn, map[string]any{"ok": true, "entries": entries})
}

func (s *Session) closeFile() {
	if s.openFile != nil {
		s.openFile.Close()
		s.openFile, s.openPath = nil, ""
	}
}

func (s *Session) handleRead(req request) error {
	real, err := s.resolve(req.Path)
	if err != nil {
		return writeMsg(s.conn, map[string]any{"ok": false, "error": err.Error()})
	}
	if s.openPath != real {
		s.closeFile()
		f, err := os.Open(real)
		if err != nil {
			return writeMsg(s.conn, map[string]any{"ok": false, "error": shortErr(err)})
		}
		s.openFile, s.openPath = f, real
		s.FilesRead.Add(1)
		s.mu.Lock()
		s.current = real
		s.mu.Unlock()
	}
	n := req.Len
	if n <= 0 || n > maxRead {
		n = maxRead
	}
	buf := make([]byte, n)
	got, err := s.openFile.ReadAt(buf, req.Off)
	eof := false
	if err != nil {
		if errors.Is(err, io.EOF) {
			eof = true
		} else {
			s.closeFile()
			return writeMsg(s.conn, map[string]any{"ok": false, "error": shortErr(err)})
		}
	}
	if err := writeMsg(s.conn, map[string]any{"ok": true, "n": got, "eof": eof}); err != nil {
		return err
	}
	if got > 0 {
		if _, err := s.conn.Write(buf[:got]); err != nil {
			return err
		}
		s.BytesSent.Add(int64(got))
	}
	if eof {
		s.closeFile()
	}
	return nil
}

func shortErr(err error) string {
	var pe *os.PathError
	if errors.As(err, &pe) {
		return pe.Err.Error()
	}
	return err.Error()
}

// Discover asks the local network "is Nostos waiting anywhere?".
// The question goes out as a broadcast; Nostos answers directly, which
// Windows Firewall allows without any rule because we asked first.
func Discover(wait time.Duration) []map[string]string {
	found := []map[string]string{}
	conn, err := net.ListenUDP("udp4", &net.UDPAddr{})
	if err != nil {
		return found
	}
	defer conn.Close()
	targets := []net.IP{net.IPv4bcast}
	if ifaces, err := net.Interfaces(); err == nil {
		for _, iface := range ifaces {
			if iface.Flags&net.FlagUp == 0 || iface.Flags&net.FlagLoopback != 0 {
				continue
			}
			addrs, _ := iface.Addrs()
			for _, a := range addrs {
				if ipn, ok := a.(*net.IPNet); ok && ipn.IP.To4() != nil {
					ip, mask := ipn.IP.To4(), ipn.Mask
					if len(mask) == 16 {
						mask = mask[12:]
					}
					bc := net.IPv4(ip[0]|^mask[0], ip[1]|^mask[1], ip[2]|^mask[2], ip[3]|^mask[3])
					targets = append(targets, bc)
				}
			}
		}
	}
	targets = append(targets, net.IPv4(127, 0, 0, 1))
	for _, t := range targets {
		conn.WriteToUDP([]byte("NOSTOS?1"), &net.UDPAddr{IP: t, Port: 47800})
	}
	conn.SetReadDeadline(time.Now().Add(wait))
	seen := map[string]bool{}
	buf := make([]byte, 512)
	for {
		n, from, err := conn.ReadFromUDP(buf)
		if err != nil {
			break
		}
		fields := strings.Fields(string(buf[:n]))
		if len(fields) >= 2 && fields[0] == "NOSTOS!1" {
			addr := net.JoinHostPort(from.IP.String(), fields[1])
			if !seen[addr] {
				seen[addr] = true
				name := from.IP.String()
				if len(fields) >= 3 {
					name = strings.Join(fields[2:], " ")
				}
				found = append(found, map[string]string{"address": addr, "name": name})
			}
		}
	}
	return found
}
