#!/usr/bin/env python3
"""
WAL Contest Logger - Lietuvos mobiliuju/portabiliuju RS cempionatas
- Runs locally on a Windows laptop (Python stdlib + cryptography for the phone-GPS HTTPS page).
- Laptop UI:   http://localhost:8770
- Phone GPS:   https://<laptop-ip>:8443/gps   (Android Chrome -> allow location)

WAL square math matches ham.guide exactly:
    row letter = floor(-(lat - 56.5) / (10/60))   -> A..
    col number = floor((lon - 20.8333) / (10/60))
    square = LETTER + col.zfill(2)
"""
import http.server
import socketserver
import ssl
import json
import sqlite3
import threading
import socket
import os
import math
import re
import shutil
import datetime
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "wal_log.sqlite")
SEC_LOCAL = os.path.join(HERE, "LYWAL.sec")
SEC_N1MM = r"C:\Users\linut\Documents\N1MM Logger+\SupportFiles\LYWAL.sec"
CERT_PATH = os.path.join(HERE, "cert.pem")
KEY_PATH = os.path.join(HERE, "key.pem")

HTTP_PORT = 8782
HTTPS_PORT = 8443

# ---------------------------------------------------------------- WAL geometry
LAT0 = 56.5
LON0 = 20 + 50 / 60.0            # 20.8333... (20 deg 50 min)
STEP = 10 / 60.0                 # 10 arc-minutes
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def latlon_to_wal(lat, lon):
    """Exact ham.guide algorithm. Returns e.g. 'M27' or None if off-grid."""
    try:
        row = int(math.floor(-(float(lat) - LAT0) / STEP))
        col = int(math.floor((float(lon) - LON0) / STEP))
    except (TypeError, ValueError):
        return None
    if row < 0 or row >= len(LETTERS) or col < 0:
        return None
    return "%s%02d" % (LETTERS[row], col)


def load_valid_squares():
    path = SEC_LOCAL if os.path.exists(SEC_LOCAL) else SEC_N1MM
    valid = set()
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                tok = line.strip()
                if tok == "DX" or re.match(r"^[A-Z]\d{2}$", tok):
                    valid.add(tok)
    except OSError:
        pass
    return valid


VALID_SQUARES = load_valid_squares()


def read_asset(name):
    with open(os.path.join(HERE, name), "r", encoding="utf-8") as f:
        return f.read()

# ---------------------------------------------------------------- shared state
LOCK = threading.RLock()
STATE = {
    "sent_wal": "",        # current square we transmit
    "sent_source": "manual",
    "gps_lat": None,
    "gps_lon": None,
    "gps_ts": None,        # iso time of last GPS fix
    "gps_hold": None,      # GPS square at which a manual override was set; held until GPS moves off it
}


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def set_sent(wal, source):
    """Update the current sent square and persist it (survives a restart)."""
    with LOCK:
        STATE["sent_wal"] = wal
        STATE["sent_source"] = source
    cfg_set("sent_wal", wal)
    cfg_set("sent_source", source)


# ---------------------------------------------------------------- database
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS qso(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_utc TEXT, freq_khz INTEGER, mode TEXT,
                call TEXT, rst_s TEXT, rst_r TEXT,
                sent_wal TEXT, rcv_wal TEXT, points INTEGER, rnd INTEGER DEFAULT 0)"""
        )
        try:
            c.execute("ALTER TABLE qso ADD COLUMN rnd INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        c.execute("CREATE TABLE IF NOT EXISTS cfg(k TEXT PRIMARY KEY, v TEXT)")
        for k, v in (("mycall", "LY5AT/M"), ("mode", "SSB"), ("freq", "3600"),
                     ("name", ""), ("category", "M"), ("round_override", "0"),
                     ("ly_default", "1")):
            if c.execute("SELECT 1 FROM cfg WHERE k=?", (k,)).fetchone() is None:
                c.execute("INSERT INTO cfg(k,v) VALUES(?,?)", (k, v))


def cfg_get(k, default=""):
    with db() as c:
        r = c.execute("SELECT v FROM cfg WHERE k=?", (k,)).fetchone()
        return r["v"] if r else default


def cfg_set(k, v):
    with db() as c:
        c.execute("INSERT INTO cfg(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=?", (k, v, v))


# ---------------------------------------------------------------- scoring
# Contest runs in three 1-hour rounds (turai): 06,07,08 UTC -> 1,2,3.
def round_for_hour(h):
    return {6: 1, 7: 2, 8: 3}.get(h, 0)


def current_round():
    """Effective round: manual override (1/2/3) if set, else from the UTC hour."""
    try:
        ov = int(cfg_get("round_override", "0"))
    except ValueError:
        ov = 0
    return ov if ov in (1, 2, 3) else round_for_hour(now_utc().hour)


def qso_points(call, rcv_wal):
    c = (call or "").upper().strip()
    if c.endswith("/M") or c.endswith("/MM"):
        return 5
    if c.endswith("/P"):
        return 3
    return 1                      # stationary LY and foreign stations


def call_prefix(call):
    """Rough DXCC-ish prefix for the foreign-country multiplier estimate."""
    c = (call or "").upper().strip()
    c = c.split("/")[0]
    m = re.match(r"^([A-Z0-9]*?\d)[A-Z]*$", c)
    return m.group(1) if m else c


def compute_stats():
    with db() as c:
        rows = c.execute("SELECT call,sent_wal,rcv_wal,points,rnd FROM qso").fetchall()
    squares, own, dxcc = set(), set(), set()
    rounds = {1: 0, 2: 0, 3: 0}
    pts = 0
    for r in rows:
        pts += r["points"] or 0
        if r["sent_wal"]:
            own.add(r["sent_wal"])
        rcv = (r["rcv_wal"] or "").upper()
        if rcv == "DX":
            dxcc.add(call_prefix(r["call"]))
        elif rcv:
            squares.add(rcv)
        if r["rnd"] in rounds:
            rounds[r["rnd"]] += 1
    mult = len(squares) + len(own) + len(dxcc)
    return {
        "qsos": len(rows),
        "points": pts,
        "squares": len(squares),
        "own_squares": len(own),
        "dx_countries": len(dxcc),
        "mult": mult,
        "score": pts * mult,
        "worked_squares": sorted(squares),
        "own_list": sorted(own),
        "rounds": rounds,
    }


# ---------------------------------------------------------------- exports
def cabrillo():
    mycall = cfg_get("mycall", "LY5AT/M")
    name = cfg_get("name", "")
    cat = cfg_get("category", "M")          # M / P / S / K / SWL / KL
    station = {"M": "MOBILE", "P": "PORTABLE", "S": "FIXED",
               "K": "FIXED", "SWL": "CHECKLOG", "KL": "FIXED"}.get(cat, "MOBILE")
    st = compute_stats()
    out = [
        "START-OF-LOG: 3.0",
        "CONTEST: LY-WAL",
        "CALLSIGN: %s" % mycall,
        "CATEGORY-OPERATOR: %s" % ("MULTI-OP" if cat == "KL" else "SINGLE-OP"),
        "CATEGORY-STATION: %s" % station,
        "CATEGORY-BAND: 80M",
        "CATEGORY-POWER: LOW",
        "CATEGORY-MODE: MIXED",
        "CLAIMED-SCORE: %d" % st["score"],
        "NAME: %s" % name,
        "SOAPBOX: WAL category %s" % cat,
        "CREATED-BY: WAL Logger",
    ]
    with db() as c:
        rows = c.execute("SELECT * FROM qso ORDER BY ts_utc, id").fetchall()
    # Cabrillo QSO line = freq mode date time MYCALL sRST sWAL CALL rRST rWAL
    for r in rows:
        ts = datetime.datetime.fromisoformat(r["ts_utc"])
        md = "CW" if r["mode"] == "CW" else "PH"
        out.append(
            "QSO: %5d %2s %s %s %-10s %-3s %-4s %-10s %-3s %-4s"
            % (
                r["freq_khz"] or 3600, md,
                ts.strftime("%Y-%m-%d"), ts.strftime("%H%M"),
                mycall, r["rst_s"], r["sent_wal"],
                r["call"].upper(), r["rst_r"], r["rcv_wal"],
            )
        )
    out.append("END-OF-LOG:")
    return "\n".join(out) + "\n"


def adif():
    def f(tag, val):
        val = str(val)
        return "<%s:%d>%s" % (tag, len(val), val)
    with db() as c:
        rows = c.execute("SELECT * FROM qso ORDER BY ts_utc, id").fetchall()
    out = ["WAL Contest ADIF export", "<ADIF_VER:5>3.1.0", "<PROGRAMID:10>WAL Logger", "<EOH>"]
    for r in rows:
        ts = datetime.datetime.fromisoformat(r["ts_utc"])
        rec = [
            f("CALL", r["call"].upper()),
            f("QSO_DATE", ts.strftime("%Y%m%d")),
            f("TIME_ON", ts.strftime("%H%M%S")),
            f("BAND", "80m"),
            f("FREQ", "%.3f" % ((r["freq_khz"] or 3600) / 1000.0)),
            f("MODE", "CW" if r["mode"] == "CW" else "SSB"),
            f("RST_SENT", r["rst_s"]),
            f("RST_RCVD", r["rst_r"]),
            f("STX_STRING", r["sent_wal"]),
            f("SRX_STRING", r["rcv_wal"]),
            f("COMMENT", "WAL %s" % r["rcv_wal"]),
            "<EOR>",
        ]
        out.append(" ".join(rec))
    return "\n".join(out) + "\n"


def backup_db():
    """Copy the whole database to backups/wal_log_<ts>.sqlite. Returns the filename or ''."""
    if not os.path.exists(DB_PATH):
        return ""
    bdir = os.path.join(HERE, "backups")
    os.makedirs(bdir, exist_ok=True)
    name = "wal_log_%s.sqlite" % now_utc().strftime("%Y%m%d_%H%M%S")
    try:
        shutil.copy2(DB_PATH, os.path.join(bdir, name))
        return name
    except OSError:
        return ""


# ---------------------------------------------------------------- HTTP handler
class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj), "application/json")

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except ValueError:
            return {}

    MACRO_EXT = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/wav": "wav",
                 "audio/x-wav": "wav", "audio/wave": "wav", "audio/mpeg": "mp3", "audio/mp4": "m4a"}

    def handle_macro_upload(self, path):
        n = path.rsplit("/", 1)[-1]
        if n not in ("1", "2", "3"):
            return self._send(404, "bad slot", "text/plain")
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        ctype = (self.headers.get("Content-Type", "audio/webm") or "audio/webm").split(";")[0].strip()
        fn = "macro_%s.%s" % (n, self.MACRO_EXT.get(ctype, "bin"))
        with open(os.path.join(HERE, fn), "wb") as f:
            f.write(raw)
        cfg_set("macro_%s_file" % n, fn)
        cfg_set("macro_%s_mime" % n, ctype)
        return self._json({"ok": True, "bytes": len(raw)})

    # ---- GET
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            return self._send(200, read_asset("logger.html"), "text/html; charset=utf-8")
        if path == "/gps":
            return self._send(200, read_asset("gps.html"), "text/html; charset=utf-8")
        if path == "/api/state":
            with LOCK:
                s = dict(STATE)
            s["stats"] = compute_stats()
            s["mycall"] = cfg_get("mycall", "LY5AT/M")
            s["mode"] = cfg_get("mode", "SSB")
            s["freq"] = cfg_get("freq", "3600")
            s["name"] = cfg_get("name", "")
            s["category"] = cfg_get("category", "M")
            s["round_override"] = cfg_get("round_override", "0")
            s["ly_default"] = cfg_get("ly_default", "1")
            s["valid_count"] = len(VALID_SQUARES)
            tnow = now_utc()
            s["utc"] = tnow.isoformat()
            s["current_round"] = current_round()
            return self._json(s)
        if path == "/api/valid":
            return self._json(sorted(VALID_SQUARES))
        if path == "/api/macros":
            defaults = {"1": "CQ", "2": "Rpt", "3": "TU"}
            out = {}
            for n in ("1", "2", "3"):
                out[n] = {"has": bool(cfg_get("macro_%s_file" % n, "")),
                          "label": cfg_get("macro_%s_label" % n, defaults[n])}
            return self._json(out)
        if path.startswith("/macro/"):
            n = path.rsplit("/", 1)[-1]
            fn = cfg_get("macro_%s_file" % n, "")
            full = os.path.join(HERE, fn) if fn else ""
            if not fn or not os.path.exists(full):
                return self._send(404, "no macro", "text/plain")
            with open(full, "rb") as f:
                body = f.read()
            return self._send(200, body, cfg_get("macro_%s_mime" % n, "audio/webm"))
        if path == "/api/qsos":
            with db() as c:
                rows = c.execute("SELECT * FROM qso ORDER BY id DESC LIMIT 300").fetchall()
            return self._json([dict(r) for r in rows])
        if path == "/export/cabrillo":
            fn = cfg_get("mycall", "LY5AT").replace("/", "_")
            return self._send(200, cabrillo(), "text/plain; charset=utf-8",
                              {"Content-Disposition": 'attachment; filename="%s_WAL.log"' % fn})
        if path == "/export/adif":
            fn = cfg_get("mycall", "LY5AT").replace("/", "_")
            return self._send(200, adif(), "text/plain; charset=utf-8",
                              {"Content-Disposition": 'attachment; filename="%s_WAL.adi"' % fn})
        return self._send(404, "not found", "text/plain")

    # ---- POST
    def do_POST(self):
        path = self.path.split("?")[0]
        if path.startswith("/api/macro/"):
            return self.handle_macro_upload(path)
        data = self._body()

        if path == "/api/gps":
            lat, lon = data.get("lat"), data.get("lon")
            sq = latlon_to_wal(lat, lon)
            with LOCK:
                STATE["gps_lat"], STATE["gps_lon"] = lat, lon
                STATE["gps_ts"] = now_utc().isoformat()
                src = STATE.get("sent_source")
                hold = STATE.get("gps_hold")
                cur_sent = STATE.get("sent_wal")
            if sq:
                # If the operator manually set a square, respect it while parked
                # (GPS square unchanged); auto-resume once GPS shows a different square.
                if src == "manual" and cur_sent:
                    if hold is None:
                        with LOCK:
                            STATE["gps_hold"] = sq
                    elif sq != hold:
                        set_sent(sq, "gps")
                        with LOCK:
                            STATE["gps_hold"] = None
                    # else: same spot -> keep manual override
                else:
                    set_sent(sq, "gps")
            return self._json({"ok": True, "square": sq})

        if path == "/api/sent":
            wal = (data.get("wal") or "").strip().upper()
            set_sent(wal, "manual")
            with LOCK:
                STATE["gps_hold"] = latlon_to_wal(STATE.get("gps_lat"), STATE.get("gps_lon"))
            return self._json({"ok": True, "sent_wal": wal})

        if path == "/api/mycall":
            cfg_set("mycall", (data.get("mycall") or "").strip().upper())
            return self._json({"ok": True})

        if path == "/api/qso":
            call = (data.get("call") or "").strip().upper()
            rcv_wal = (data.get("rcv_wal") or "").strip().upper()
            if not call or not rcv_wal:
                return self._json({"ok": False, "error": "call and received WAL required"}, 400)
            with LOCK:
                sent = (data.get("sent_wal") or STATE["sent_wal"] or "").strip().upper()
            mode = "CW" if (data.get("mode") or "SSB").upper() == "CW" else "SSB"
            rst_def = "599" if mode == "CW" else "59"
            pts = qso_points(call, rcv_wal)
            tnow = now_utc()
            rnd = current_round()
            with db() as c:
                c.execute(
                    "INSERT INTO qso(ts_utc,freq_khz,mode,call,rst_s,rst_r,sent_wal,rcv_wal,points,rnd)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (tnow.isoformat(), int(data.get("freq_khz") or 3600), mode, call,
                     data.get("rst_s") or rst_def, data.get("rst_r") or rst_def,
                     sent, rcv_wal, pts, rnd),
                )
            valid = (rcv_wal == "DX") or (rcv_wal in VALID_SQUARES)
            return self._json({"ok": True, "points": pts, "valid_square": valid, "round": rnd})

        if path == "/api/qso/update":
            qid = data.get("id")
            with db() as c:
                row = c.execute("SELECT * FROM qso WHERE id=?", (qid,)).fetchone()
                if not row:
                    return self._json({"ok": False, "error": "not found"}, 404)
                call = (data.get("call") or row["call"]).strip().upper()
                rcv_wal = (data.get("rcv_wal") or row["rcv_wal"]).strip().upper()
                sv = data.get("sent_wal")
                sent = (sv if sv is not None else row["sent_wal"]).strip().upper()
                mode = "CW" if (data.get("mode") or row["mode"]).upper() == "CW" else "SSB"
                rst_s = data.get("rst_s") or row["rst_s"]
                rst_r = data.get("rst_r") or row["rst_r"]
                freq = int(data.get("freq_khz") or row["freq_khz"] or 3600)
                pts = qso_points(call, rcv_wal)
                rnd = row["rnd"]          # keep the round the QSO was made in
                c.execute(
                    "UPDATE qso SET call=?,rcv_wal=?,sent_wal=?,mode=?,rst_s=?,rst_r=?,"
                    "freq_khz=?,points=?,rnd=? WHERE id=?",
                    (call, rcv_wal, sent, mode, rst_s, rst_r, freq, pts, rnd, qid),
                )
            return self._json({"ok": True, "points": pts})

        if path == "/api/band":
            cfg_set("mode", "CW" if (data.get("mode") or "SSB").upper() == "CW" else "SSB")
            cfg_set("freq", str(int(data.get("freq") or 3600)))
            return self._json({"ok": True})

        if path == "/api/macrolabel":
            n = str(data.get("n"))
            if n in ("1", "2", "3"):
                cfg_set("macro_%s_label" % n, (data.get("label") or "").strip())
            return self._json({"ok": True})

        if path == "/api/qso/delete":
            with db() as c:
                c.execute("DELETE FROM qso WHERE id=?", (data.get("id"),))
            return self._json({"ok": True})

        if path == "/api/backup":
            return self._json({"ok": True, "backup": backup_db()})

        if path == "/api/wipe":
            with db() as c:
                n = c.execute("SELECT COUNT(*) AS k FROM qso").fetchone()["k"]
            backup = backup_db()
            with db() as c:
                c.execute("DELETE FROM qso")
            return self._json({"ok": True, "cleared": n, "backup": backup})

        if path == "/api/cfgset":
            k = str(data.get("key"))
            v = (data.get("value") or "").strip()
            if k in ("mycall", "name", "category", "round_override", "ly_default"):
                cfg_set(k, v.upper() if k == "mycall" else v)
            return self._json({"ok": True})

        if path == "/api/dupe":
            call = (data.get("call") or "").strip().upper()
            mode = "CW" if (data.get("mode") or "SSB").upper() == "CW" else "SSB"
            rnd = current_round()
            with LOCK:
                mysq = STATE.get("sent_wal", "")
            # A QSO is a dupe only if worked this round, this mode, AND from MY current
            # square. If a mobile changes its own square it becomes a new correspondent,
            # so re-working the same station is then a valid (non-dupe) QSO.
            with db() as c:
                rows = c.execute(
                    "SELECT rcv_wal FROM qso WHERE call=? AND mode=? AND rnd=? AND sent_wal=?",
                    (call, mode, rnd, mysq)
                ).fetchall()
                anyr = c.execute(
                    "SELECT rcv_wal FROM qso WHERE call=? ORDER BY id DESC LIMIT 1", (call,)
                ).fetchone()
            return self._json({
                "count": len(rows),
                "prev_rcv": rows[-1]["rcv_wal"] if rows else "",
                "last_rcv": anyr["rcv_wal"] if anyr else "",
                "round": rnd,
                "my_square": mysq,
            })

        return self._send(404, "not found", "text/plain")


class ThreadingHTTP(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# ---------------------------------------------------------------- cert + net
def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def ensure_cert(ip):
    """Self-signed cert with SAN for localhost + current LAN ip (for phone HTTPS)."""
    stamp = os.path.join(HERE, ".certip")
    if os.path.exists(CERT_PATH) and os.path.exists(KEY_PATH):
        if os.path.exists(stamp) and open(stamp).read().strip() == ip:
            return
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    import ipaddress as ipa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "WAL Logger")])
    san = x509.SubjectAlternativeName([
        x509.DNSName("localhost"),
        x509.IPAddress(ipa.IPv4Address("127.0.0.1")),
        x509.IPAddress(ipa.IPv4Address(ip)),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=825))
        .add_extension(san, critical=False)
        .sign(key, hashes.SHA256())
    )
    with open(KEY_PATH, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM,
                                  serialization.PrivateFormat.TraditionalOpenSSL,
                                  serialization.NoEncryption()))
    with open(CERT_PATH, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(stamp, "w") as f:
        f.write(ip)


# ---------------------------------------------------------------- main
def serve_https(ip):
    try:
        ensure_cert(ip)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(CERT_PATH, KEY_PATH)
        httpsd = ThreadingHTTP(("0.0.0.0", HTTPS_PORT), Handler)
        httpsd.socket = ctx.wrap_socket(httpsd.socket, server_side=True)
        httpsd.serve_forever()
    except Exception as e:
        print("[https] disabled:", e)


def main():
    init_db()
    with LOCK:
        STATE["sent_wal"] = cfg_get("sent_wal", "")
        STATE["sent_source"] = cfg_get("sent_source", "manual")
    ip = lan_ip()
    threading.Thread(target=serve_https, args=(ip,), daemon=True).start()
    httpd = ThreadingHTTP(("0.0.0.0", HTTP_PORT), Handler)
    print("=" * 60)
    print(" WAL Contest Logger")
    print(" Laptop UI :  http://localhost:%d" % HTTP_PORT)
    print(" Phone GPS :  https://%s:%d/gps   (allow location)" % (ip, HTTPS_PORT))
    print(" Valid squares loaded:", len(VALID_SQUARES))
    print("=" * 60)
    try:
        webbrowser.open("http://localhost:%d" % HTTP_PORT)
    except Exception:
        pass
    httpd.serve_forever()


if __name__ == "__main__":
    main()
