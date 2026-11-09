#!/usr/bin/env python3
"""AirPods battery + ear state for the shell.

Two sources, published as one JSON file ($XDG_RUNTIME_DIR/airpods-battery.json):

  1. AACP over L2CAP (PSM 0x1001): the AirPods' own protocol, the same one LibrePods
     uses. Live and exact while the AirPods are connected: per-component level and
     charge state, plus ear detection (in ear / out of ear / in case).
  2. BLE advertisements (Apple continuity, proximity pairing): used while the AirPods
     are not connected (lid open next to the computer).

JSON:
  {"left": 0-100|null, "right": ..., "case": ...,
   "charging": {"left": bool, "right": bool, "case": bool},
   "inCase":   {"left": bool, "right": bool} | absent,   # AACP ear detection
   "source": "aacp" | "adv", "usb": bool, "seen": <unix>, "ts": <unix>}

Usage: airpods_battery.py [--seconds N]   (default: run forever)"""
import asyncio, json, os, re, socket, subprocess, sys, tempfile, threading, time

OUT = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "airpods-battery.json")
APPLE = 0x004C
MIN_RSSI = -75
USB_POLL = 1.0
KEEPALIVE = 15
AACP_PSM = 0x1001
ADV_FILL = 180   # how long a readable broadcast may fill in what the connection cannot report
CASE_CHARGE_TTL = 150  # seconds a case charge flag from a broadcast stays believable
CASE_KEEP = 6 * 3600  # the case level changes slowly: keep the last decrypted value this long
ENC_MIN_RSSI = -92    # encrypted broadcasts are validated by the key, so weak signals are safe
STATE_DIR = os.path.join(os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")), "airpods-battery")
CASE_CACHE = os.path.join(STATE_DIR, "case.json")

# Packets LibrePods sends to start the stream: handshake, feature flags, notification request.
INIT = [
    bytes.fromhex("00000400010002000000000000000000"),
    bytes.fromhex("040004004d00ff00000000000000"),
    bytes.fromhex("040004000f00ffffffff"),
    bytes.fromhex("0400040030000500"),  # request the proximity keys (identity + encryption)
]

lock = threading.Lock()
aacp = {"res": None, "seen": 0.0, "bat": {}, "ear": None}
adv = {"res": None, "seen": 0.0}
# The case's level, read from the encrypted broadcast (AirPods Pro 2/3): {"level": 0-100|None, "seen": t}
enc = {"key": None, "case": None, "pods": {}}
last_level = {}  # last level the connection reported per pod
try:  # the last known case level survives a restart
    with open(CASE_CACHE) as _f:
        _c = json.load(_f)
    if time.time() - _c["seen"] < CASE_KEEP:
        enc["case"] = {"level": _c["level"], "charging": bool(_c.get("charging")), "seen": _c["seen"]}
except (OSError, ValueError, KeyError):
    pass
last_written = {"body": None, "at": 0.0}
loop_ref = {"loop": None}


# ---------------------------------------------------------------- helpers

def case_on_usb() -> bool:
    """True while the AirPods charging case is plugged into this computer."""
    base = "/sys/bus/usb/devices"
    try:
        for d in os.listdir(base):
            try:
                with open(os.path.join(base, d, "idVendor")) as f:
                    if f.read().strip() != "05ac":
                        continue
                with open(os.path.join(base, d, "product")) as f:
                    if "airpods" in f.read().lower():
                        return True
            except OSError:
                continue
    except OSError:
        pass
    return False


USB_OUT = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "usb-products.json")
usb_last = {"list": None}


def usb_products():
    """Lower-cased product names of the USB devices plugged in right now. The shell matches a
    Bluetooth device to these by name to tell that it is plugged in, i.e. charging."""
    base = "/sys/bus/usb/devices"
    out = set()
    try:
        for d in os.listdir(base):
            try:
                with open(os.path.join(base, d, "product")) as f:
                    name = f.read().strip().lower()
                if name:
                    out.add(name)
            except OSError:
                continue
    except OSError:
        pass
    return sorted(out)


def publish_usb():
    now = usb_products()
    if now == usb_last["list"]:
        return
    usb_last["list"] = now
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(USB_OUT), prefix=".usb-")
    with os.fdopen(fd, "w") as f:
        json.dump(now, f)
    os.replace(tmp, USB_OUT)


def connected_airpods():
    """MAC of a connected AirPods/Beats device, from BlueZ."""
    try:
        out = subprocess.run(["bluetoothctl", "devices", "Connected"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines():
        m = re.match(r"Device ([0-9A-F:]{17}) (.*)", line)
        if m and re.search(r"airpods|beats", m.group(2), re.I):
            return m.group(1)
    return None


# ---------------------------------------------------------------- AACP

COMPONENT = {0x02: "right", 0x04: "left", 0x08: "case"}
CHARGING, NOT_CHARGING, DISCONNECTED = 0x01, 0x02, 0x04
EAR_IN, EAR_OUT, EAR_CASE = 0x00, 0x01, 0x02


def handle_packet(p: bytes):
    if len(p) < 8 or p[:4] != b"\x04\x00\x04\x00":
        return
    opcode = p[4] | (p[5] << 8)
    changed = False
    with lock:
        if opcode == 0x0004:  # battery: count, then [component, 0x01, level, status, 0x01] x count
            count = p[6]
            for i in range(count):
                e = p[7 + 5 * i: 12 + 5 * i]
                if len(e) < 5 or e[0] not in COMPONENT:
                    continue
                level, status = e[2], e[3]
                aacp["bat"][COMPONENT[e[0]]] = {
                    # A disconnected component (pod missing, case out of range) has no real level.
                    "level": None if status == DISCONNECTED else min(100, level),
                    "charging": status == CHARGING,
                    "disc": status == DISCONNECTED,
                }
            changed = True
        elif opcode == 0x0031:  # proximity keys: count, then [type, 0x00, len(2), data] x count
            i = 7
            for _ in range(p[6]):
                if i + 4 > len(p):
                    break
                ktype, klen = p[i], p[i + 2] | (p[i + 3] << 8)
                if ktype == 4 and klen == 16:
                    enc["key"] = bytes(p[i + 4:i + 4 + klen])
                i += 4 + klen
        elif opcode == 0x0006:  # ear detection: primary pod, secondary pod
            aacp["ear"] = (p[6], p[7])
            changed = True
        if changed:
            aacp["seen"] = time.time()
            aacp["res"] = build_aacp()
    if changed:
        schedule_publish()


def build_aacp():
    bat = aacp["bat"]
    g = lambda c, k, d=None: (bat.get(c) or {}).get(k, d)
    res = {
        "left": g("left", "level"), "right": g("right", "level"), "case": g("case", "level"),
        "charging": {c: bool(g(c, "charging", False)) for c in ("left", "right", "case")},
        "source": "aacp",
    }
    disc = {c: bool(g(c, "disc", False)) for c in ("left", "right")}
    in_case = {"left": disc["left"], "right": disc["right"]}  # a pod the connection lost is in the closed case
    if aacp["ear"] is not None:
        a, b = aacp["ear"]
        # Ear values: 0 in ear, 1 out of ear, 2 in case, 3 disconnected. The pair is (primary, secondary);
        # pick the assignment that agrees with which pod's battery component is disconnected.
        def score(l, r):
            return (l == 3) == disc["left"], (r == 3) == disc["right"]
        l, r = (a, b) if sum(score(a, b)) >= sum(score(b, a)) else (b, a)
        in_case["left"] = in_case["left"] or l in (EAR_CASE, 3)
        in_case["right"] = in_case["right"] or r in (EAR_CASE, 3)
        # A charging pod is in the case too; if the sides still disagree, trust the charge state.
        cl, cr = res["charging"]["left"], res["charging"]["right"]
        if cl != cr and (in_case["left"], in_case["right"]) == (cr, cl):
            in_case["left"], in_case["right"] = cl, cr
    res["inCase"] = in_case
    for c in ("left", "right"):
        if res[c] is not None:
            last_level[c] = res[c]
    # The connection cannot see the case: take its level from the decrypted broadcast.
    if res["case"] is None and enc["case"] and enc["case"]["level"] is not None \
            and time.time() - enc["case"]["seen"] < CASE_KEEP:
        res["case"] = enc["case"]["level"]
    # Case charge flag from the broadcast. The case only reports when it is plugged in or out
    # (with a short delay), so the last report stays true until the next one arrives.
    if enc["case"] and time.time() - enc["case"]["seen"] < CASE_KEEP:
        res["charging"]["case"] = bool(enc["case"].get("charging"))
    # The connection cannot see a pod that is in the closed case, nor the case itself:
    # fill those from the last readable broadcast, if it is recent.
    if adv["res"] is not None and time.time() - adv["seen"] < ADV_FILL:
        for c in ("left", "right", "case"):
            lost = res[c] is None or (c in disc and disc[c])
            if lost and adv["res"].get(c) is not None:
                res[c] = adv["res"][c]
                res["charging"][c] = adv["res"]["charging"][c]
    # A pod in the case: its level comes from the broadcast (the case reports it), else the last
    # level seen; it is charging by definition.
    for c in ("left", "right"):
        if in_case[c]:
            pod = enc["pods"].get(c)
            if pod and time.time() - pod["seen"] < 900:
                res[c] = pod["level"]
            elif res[c] is None:
                res[c] = last_level.get(c)
            res["charging"][c] = True
    return res


def aacp_thread():
    while True:
        mac = connected_airpods()
        if not mac:
            time.sleep(3)
            continue
        sock = None
        try:
            sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
            sock.settimeout(10)
            sock.connect((mac, AACP_PSM))
            for pkt in INIT:
                sock.send(pkt)
                time.sleep(0.05)
            sock.settimeout(60)
            while True:
                data = sock.recv(1024)
                if not data:
                    break
                handle_packet(data)
        except (OSError, socket.timeout):
            pass
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            with lock:
                aacp["res"] = None  # the stream is gone; do not keep reporting its last state
            schedule_publish()
        time.sleep(2)


# ---------------------------------------------------------------- advertisements

def nib(v):
    return None if v == 0xF else min(100, v * 10)


def parse_adv(data: bytes):
    # Only the old, readable layout (0x07, length 0x19). Newer AirPods (AirPods Pro 2/3) send a
    # 0x11-length message whose payload is encrypted; reading it like this gives garbage.
    if len(data) < 27 or data[0] != 0x07 or data[1] != 0x19:
        return None
    status, pods, flags = data[5], data[6], data[7]
    flipped = (status & 0x02) == 0
    hi, lo = pods >> 4, pods & 0xF
    left, right = (hi, lo) if flipped else (lo, hi)
    charge = flags >> 4
    return {
        "left": nib(left), "right": nib(right), "case": nib(flags & 0xF),
        # A pod that charges is in the case.
        "charging": {
            "left": bool(charge & (0x02 if flipped else 0x01)),
            "right": bool(charge & (0x01 if flipped else 0x02)),
            "case": bool(charge & 0x04),
        },
        "source": "adv",
    }


DEBUG = bool(os.environ.get("AIRPODS_DEBUG"))  # log your own decrypted broadcasts to help map the layout
DEBUG_LOG = os.path.join(STATE_DIR, "decrypted.log")


def log_decrypted(plain: bytes):
    """Append each valid decrypted broadcast with the state around it, to work out the layout."""
    if not DEBUG:
        return
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with lock:
            bat = {c: (v.get("level"), v.get("charging")) for c, v in aacp["bat"].items()}
            ear = aacp["ear"]
        line = f"{time.strftime('%H:%M:%S')} plain={plain.hex()} usb={int(case_on_usb())} aacp={bat} ear={ear}\n"
        # keep the file small
        if os.path.exists(DEBUG_LOG) and os.path.getsize(DEBUG_LOG) > 100_000:
            os.replace(DEBUG_LOG, DEBUG_LOG + ".old")
        with open(DEBUG_LOG, "a") as f:
            f.write(line)
    except OSError:
        pass


def read_encrypted(raw: bytes):
    """Newer AirPods: 0x07, 0x11, 0x06, then 16 bytes encrypted with AES-128-ECB under the
    encryption key the AirPods hand out over AACP. Returns the case level (0-100) or None.
    Only accepted when the plaintext has the shape of our AirPods' message: other people's
    AirPods decrypt to noise."""
    key = enc["key"]
    if key is None or len(raw) != 19 or raw[0] != 0x07 or raw[1] != 0x11:
        return False
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    plain = Cipher(algorithms.AES(key), modes.ECB()).decryptor().update(raw[3:19])
    if plain[8:12] != b"\x00\x00\x00\x00" and not (plain[12] == 0x4C and plain[13] == 0x01):
        return False
    # Same byte layout as the other open decoders (apple-ble, LinuxPods): bit 7 = charging,
    # low 7 bits = percent, 0x7F = not reported.
    level, charging = plain[3] & 0x7F, bool(plain[3] & 0x80)
    # Bytes 4 and 5: a pod that is in the case (left, right), charging bit + percent, 0xFF = not in the case.
    for side, b in (("left", plain[4]), ("right", plain[5])):
        if b != 0xFF and (b & 0x7F) <= 100:
            with lock:
                enc["pods"][side] = {"level": b & 0x7F, "charging": bool(b & 0x80), "seen": time.time()}
    log_decrypted(plain)
    with lock:
        if level <= 100:
            enc["case"] = {"level": level, "charging": charging, "seen": time.time()}
            try:
                os.makedirs(STATE_DIR, exist_ok=True)
                with open(CASE_CACHE, "w") as f:
                    json.dump(enc["case"], f)
            except OSError:
                pass
        if aacp["bat"]:
            aacp["res"] = build_aacp() if aacp["res"] is not None else None
    return True


def on_adv(device, data):
    raw = data.manufacturer_data.get(APPLE)
    if raw is None:
        return
    if data.rssi >= ENC_MIN_RSSI and read_encrypted(bytes(raw)):
        publish()
        return
    if data.rssi < MIN_RSSI:
        return
    res = parse_adv(bytes(raw))
    if res:
        with lock:
            adv["res"], adv["seen"] = res, time.time()
            if aacp["bat"]:
                aacp["res"] = build_aacp() if aacp["res"] is not None else None
        publish()


# ---------------------------------------------------------------- publishing

def schedule_publish():
    loop = loop_ref["loop"]
    if loop is not None:
        loop.call_soon_threadsafe(publish)


def publish(force=False):
    now = time.time()
    with lock:
        if aacp["res"] is not None:
            res, seen = aacp["res"], aacp["seen"]
        elif adv["res"] is not None:
            res, seen = adv["res"], adv["seen"]
        else:
            return
        res = json.loads(json.dumps(res))
    usb = case_on_usb()
    # Plugged in is not the same as charging: a full case on a cable is not charging.
    res["charging"]["case"] = res["charging"]["case"] or (usb and (res.get("case") is None or res["case"] < 100))
    body = dict(res, usb=usb, seen=int(seen))
    if not force and body == last_written["body"] and now - last_written["at"] < KEEPALIVE:
        return
    last_written["body"], last_written["at"] = body, now
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(OUT), prefix=".ab-")
    with os.fdopen(fd, "w") as f:
        json.dump(dict(body, ts=int(now)), f)
    os.replace(tmp, OUT)


async def main(seconds):
    from bleak import BleakScanner

    loop_ref["loop"] = asyncio.get_running_loop()
    threading.Thread(target=aacp_thread, daemon=True).start()
    end = time.time() + seconds if seconds else None
    async with BleakScanner(on_adv):
        while end is None or time.time() < end:
            await asyncio.sleep(USB_POLL)
            publish_usb()
            publish()  # case plugged in/out, keepalive


secs = int(sys.argv[sys.argv.index("--seconds") + 1]) if "--seconds" in sys.argv else 0
asyncio.run(main(secs))
