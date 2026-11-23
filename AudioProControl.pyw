"""
Audio Pro Control — control Audio Pro Wi-Fi speakers from Windows, and play your own music on them.

Talks to the speakers directly on your home network:
  * LinkPlay HTTP API for commands, device info and multiroom grouping
      - first-generation models answer on plain HTTP port 80
      - MkII / W-series answer on HTTPS port 4443 with the generic LinkPlay client certificate
  * UPnP (AVTransport / RenderingControl) for live playback state, track info and volume,
    which MkII firmware no longer reports over HTTP.
Each speaker is asked what it supports and the answers are remembered, so both generations
(and firmware in between) are driven the way they expect.

The interface is a local web page (ui.html) shown in a chromeless Microsoft Edge app window.
Local music is streamed to the speakers from a small HTTP server on this PC.

No internet, no account, no extra packages: only the Python standard library.

Protocol details and the client certificate come from the MIT-licensed
pywiim project by Michael Cumming (https://github.com/mjcumming/pywiim).
"""

from __future__ import annotations

import binascii
import concurrent.futures as cf
import html
import http.client
import json
import os
import re
import select
import socket
import ssl
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings
import xml.etree.ElementTree as ET
import zlib

APP_NAME = "Audio Pro Control"
APP_VERSION = "3.4"

# Ports to try, in order. Override for testing with APC_PROBE="https:4443,http:80"
DEFAULT_PROBES = [("https", 4443), ("http", 80), ("https", 443), ("https", 8443)]
# UPnP description ports to try when SSDP didn't tell us. Override with APC_UPNP_PORTS="49152,49153"
DEFAULT_UPNP_PORTS = [49152, 59152, 49153, 49154, 49155]

HTTP_TIMEOUT = 5.0      # a command the user is waiting for (MkII needs a TLS handshake per request)
POLL_TIMEOUT = 4.0      # background status questions
PROBE_TIMEOUT = 4.0     # "are you a speaker?"

# HTTP "mode" / UPnP "PlayMode" -> what is playing
MODE_NAMES = {
    "0": "Idle", "1": "AirPlay", "2": "DLNA", "3": "Wi-Fi", "4": "Line in", "5": "Bluetooth",
    "6": "Optical", "10": "Wi-Fi", "11": "USB", "20": "Wi-Fi", "31": "Spotify Connect",
    "32": "TIDAL Connect", "34": "Lyrion", "36": "Qobuz", "40": "Line in", "41": "Bluetooth",
    "43": "Optical", "44": "RCA", "47": "Line in 2", "49": "HDMI", "51": "USB", "60": "Line in",
    "99": "Grouped",
}

# UPnP PlayMedium / TrackSource values -> label ("" = nothing worth showing)
MEDIUM_NAMES = {
    "SPOTIFY": "Spotify Connect", "AIRPLAY": "AirPlay", "BLUETOOTH": "Bluetooth", "LINE-IN": "Line in",
    "LINEIN": "Line in", "OPTICAL": "Optical", "COAXIAL": "Coaxial", "HDMI": "HDMI", "RCA": "RCA",
    "TIDAL": "TIDAL Connect", "UDISK": "USB", "USB": "USB", "RADIO-NETWORK": "Internet radio",
    "THIRD-DLNA": "DLNA", "SONGLIST-NETWORK": "", "SONGLIST-LOCAL": "", "NONE": "", "UNKNOWN": "",
    "NETWORK": "", "CUSTOMPUSHURL": "",
}

# Generic LinkPlay client certificate + key (public, shipped in LinkPlay apps; via pywiim, MIT).
LINKPLAY_CLIENT_PEM = """-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCk/u2tH0LwCOv8
JmqLvQdjNAdkxfSCPwrdHM7STlq5xaJGQe29yd8kjP7h0wERkeO/9JO62wUHBu0P
WIsS/jwLG+G3oAU+7BNfjmBhDXyHIRQLzAWEbtxbsSTke1losfvlQXGumXrMqf9X
LdIYvbA53mp8GImQbJkaCDvwnEdUFkuJ0W5Tofr58jJqfCt6OPwHmnP4oC6LpPtJ
YDy7r1Q9sLgCYEtDEw/Mhf+mKuC0pnst52e1qceVjvCuUBoeuhk6kpnEbpSdEKbD
bdE8cPoVRmrj1//PLFMVtNB7k2aPMb3CcoJ/dHxaCXwk9b3jIBs6CyWixN92CuaO
Q98Ug/YlAgMBAAECggEAHyCpHlwjeL12J9/nge1rk1+hdXWTJ29VUVm5+xslKp8K
ek6912xaWL7w5xGzxejMGs69gCcJz8WSu65srmygT0g3UTkzRCetj/2AWU7+C1BG
Q+N9tvpjQDkvSJusxn+tkhbCp7n03N/FeGEAngJLWN+JH1hRu5mBWNPs2vvgyRAO
Cv95G7uENavCUXcyYsKPoAfz3ebD/idwwWW2RKAd0ufYeafiFC0ImTLcpEjBvCTW
UoAniBSVx1PHK4IAUb3pMdPtIv1uBlIMotHS/GdEyHU6qOsX5ijHqncHHneaytmL
+wJukPqASEBl3F2UnzryBUgGqr1wyH9vtPGjklnngQKBgQDZv3oxZWul//2LV+jo
ZipbnP6nwG3J6pOWPDD3dHoZ6Q2DRyJXN5ty40PS393GVvrSJSdRGeD9+ox5sFoj
iUMgd6kHG4ME7Fre57zUkqy1Ln1K1fkP5tBUD0hviigHBWih2/Nyl2vrdvX5Wpxx
5r42UQa9nOzrNB03DTOhDrUszQKBgQDB+xdMRNSFfCatQj+y2KehcH9kaANPvT0l
l9vgb72qks01h05GSPBZnT1qfndh/Myno9KuVPhJ0HrVwRAjZTd4T69fAH3imW+R
7HP+RgDen4SRTxj6UTJh2KZ8fdPeCby1xTwxYNjq8HqpiO6FHZpE+l4FE8FalZK+
Z3GhE7DuuQKBgDq7b+0U6xVKWAwWuSa+L9yoGvQKblKRKB/Uumx0iV6lwtRPAo89
23sAm9GsOnh+C4dVKCay8UHwK6XDEH0XT/jY7cmR/SP90IDhRsibi2QPVxIxZs2I
N1cFDEexnxxNtCw8VIzrFNvdKXmJnDsIvvONpWDNjAXg96RatjtR6UJdAoGBAIAx
HU5r1j54s16gf1QD1ZPcsnN6QWX622PynX4OmjsVVMPhLRtJrHysax/rf52j4OOQ
YfSPdp3hRqvoMHATvbqmfnC79HVBjPfUWTtaq8xzgro8mXcjHbaH5E41IUSFDs7Z
D1Raej+YuJc9RNN3orGe+29DhO4GFrn5xp/6UV0RAoGBAKUdRgryWzaN4auzWaRD
lxoMhlwQdCXzBI1YLH2QUL8elJOHMNfmja5G9iW07ZrhhvQBGNDXFbFrX4hI3c/0
JC3SPhaaedIjOe9Qd3tn5KgYxbBnWnCTt0kxgro+OM3ORgJseSWbKdRrjOkUxkab
/NDvel7IF63U4UEkrVVt1bYg
-----END PRIVATE KEY-----
-----BEGIN CERTIFICATE-----
MIIDmDCCAoACAQEwDQYJKoZIhvcNAQELBQAwgZExCzAJBgNVBAYTAkNOMREwDwYD
VQQIDAhTaGFuZ2hhaTERMA8GA1UEBwwIU2hhbmdoYWkxETAPBgNVBAoMCExpbmtw
bGF5MQwwCgYDVQQLDANpbmMxGTAXBgNVBAMMEHd3dy5saW5rcGxheS5jb20xIDAe
BgkqhkiG9w0BCQEWEW1haWxAbGlua3BsYXkuY29tMB4XDTE4MTExNTAzMzI1OVoX
DTQ2MDQwMTAzMzI1OVowgZExCzAJBgNVBAYTAkNOMREwDwYDVQQIDAhTaGFuZ2hh
aTERMA8GA1UEBwwIU2hhbmdoYWkxETAPBgNVBAoMCExpbmtwbGF5MQwwCgYDVQQL
DANpbmMxGTAXBgNVBAMMEHd3dy5saW5rcGxheS5jb20xIDAeBgkqhkiG9w0BCQEW
EW1haWxAbGlua3BsYXkuY29tMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKC
AQEApP7trR9C8Ajr/CZqi70HYzQHZMX0gj8K3RzO0k5aucWiRkHtvcnfJIz+4dMB
EZHjv/STutsFBwbtD1iLEv48Cxvht6AFPuwTX45gYQ18hyEUC8wFhG7cW7Ek5HtZ
aLH75UFxrpl6zKn/Vy3SGL2wOd5qfBiJkGyZGgg78JxHVBZLidFuU6H6+fIyanwr
ejj8B5pz+KAui6T7SWA8u69UPbC4AmBLQxMPzIX/pirgtKZ7LedntanHlY7wrlAa
HroZOpKZxG6UnRCmw23RPHD6FUZq49f/zyxTFbTQe5NmjzG9wnKCf3R8Wgl8JPW9
4yAbOgslosTfdgrmjkPfFIP2JQIDAQABMA0GCSqGSIb3DQEBCwUAA4IBAQARmy6f
esrifhW5NM9i3xsEVp945iSXhqHgrtIROgrC7F1EIAyoIiBdaOvitZVtsYc7Ivys
QtyVmEGscyjuYTdfigvwTVVj2oCeFv1Xjf+t/kSuk6X3XYzaxPPnFG4nAe2VwghE
rbZG0K5l8iXM7Lm+ZdqQaAYVWsQDBG8lbczgkB9q5ed4zbDPf6Fsrsynxji/+xa4
9ARfyHlkCDBThGNnnl+QITtfOWxm/+eReILUQjhwX+UwbY07q/nUxLlK6yrzyjnn
wi2B2GovofQ/4icVZ3ecTqYK3q9gEtJi72V+dVHM9kSA4Upy28Y0U1v56uoqeWQ6
uc2m8y8O/hXPSfKd
-----END CERTIFICATE-----
"""

# --------------------------------------------------------------------------------------
# Networking
# --------------------------------------------------------------------------------------

class SpeakerError(Exception):
    """A problem that can be shown to the user as it is."""


# Everything a dead / busy / rebooting speaker can throw at us.
NET_ERRORS = (OSError, http.client.HTTPException, ET.ParseError, ValueError)


def _config_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    path = os.path.join(base, "AudioProControl")
    os.makedirs(path, exist_ok=True)
    return path


def write_json(path: str, obj, indent=None) -> bool:
    """Write a settings file without ever leaving a half-written one behind."""
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=indent)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def read_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _build_ssl_context() -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # speakers use self-signed certificates
    for setter in (
        lambda: setattr(ctx, "minimum_version", ssl.TLSVersion.TLSv1),
        lambda: ctx.set_ciphers("ALL:@SECLEVEL=0"),
        # old speaker firmware predates secure renegotiation; OpenSSL 3 refuses it by default
        lambda: setattr(ctx, "options", ctx.options | getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)),
    ):
        try:
            setter()
        except Exception:
            pass
    fd, path = tempfile.mkstemp(suffix=".pem")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(LINKPLAY_CLIENT_PEM)
        ctx.load_cert_chain(path)
    except Exception as exc:  # still usable for speakers that don't need mTLS
        print("Could not load client certificate:", exc, file=sys.stderr)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    return ctx


with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    _SSL_CTX = _build_ssl_context()
_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),  # never route LAN traffic through a system proxy
    urllib.request.HTTPSHandler(context=_SSL_CTX),
)


def _probe_list():
    env = os.environ.get("APC_PROBE")
    if not env:
        return DEFAULT_PROBES
    out = []
    for part in env.split(","):
        scheme, port = part.strip().split(":")
        out.append((scheme, int(port)))
    return out


def _upnp_ports():
    env = os.environ.get("APC_UPNP_PORTS")
    if env:
        return [int(p) for p in env.split(",") if p.strip()]
    return DEFAULT_UPNP_PORTS


def http_command(base: str, command: str, timeout: float = HTTP_TIMEOUT) -> str:
    url = f"{base}/httpapi.asp?command={urllib.parse.quote(command, safe=':/._-=')}"
    with _OPENER.open(url, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def reply_failed(text: str) -> bool:
    """Speakers answer HTTP 200 with a plain-text complaint when they don't know a command."""
    t = (text or "").strip().lower()
    return t.startswith("unknown command") or t in ("failed", "fail", "error") or "not supported" in t


def parse_json(text: str):
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


_EMPTY_WORDS = ("unknow", "unknown", "none", "null", "un_known", "(null)", "not_implemented")


def clean_text(value) -> str:
    s = str(value or "").strip()
    return "" if s.lower() in _EMPTY_WORDS else s


def decode_text(value) -> str:
    """HTTP API text fields (title, artist, name...) arrive as hex-encoded UTF-8."""
    s = str(value or "").strip()
    if len(s) >= 2 and len(s) % 2 == 0 and re.fullmatch(r"[0-9A-Fa-f]+", s):
        try:
            d = bytes.fromhex(s).decode("utf-8")
            # A real title that merely looks like hex ("1979", "2112") decodes to control characters.
            if d and all(ch.isprintable() for ch in d):
                s = d
        except (ValueError, UnicodeDecodeError):
            pass
    return clean_text(html.unescape(s))


def api_time_to_sec(value) -> float:
    """curpos/totlen are milliseconds, except from streaming services, which use microseconds."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return 0.0
    if v <= 0:
        return 0.0
    return v / 1_000_000 if v > 36_000_000 else v / 1000  # > 10 hours as ms: must be µs


PLAY_STATES = {
    "play": "play", "playing": "play", "load": "play", "loading": "play", "buffering": "play",
    "transitioning": "play", "pause": "pause", "paused": "pause", "paused_playback": "pause",
    "stop": "stop", "stopped": "stop", "none": "stop", "idle": "stop", "no_media_present": "stop",
}


def norm_uuid(u) -> str:
    return re.sub(r"[^0-9a-f]", "", str(u or "").lower().replace("uuid:", ""))


def same_uuid(a, b) -> bool:
    a, b = norm_uuid(a), norm_uuid(b)
    if not a or not b:
        return False
    return a == b or (min(len(a), len(b)) >= 16 and (a.startswith(b) or b.startswith(a)))


def _timed_out(exc: BaseException) -> bool:
    reason = getattr(exc, "reason", exc)
    return isinstance(exc, TimeoutError) or isinstance(reason, TimeoutError) or "timed out" in str(exc).lower()


def _tcp_open(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def probe_host(host: str, preferred_base: str | None = None, timeout: float = PROBE_TIMEOUT,
               only_preferred: bool = False):
    """Find which endpoint a speaker answers on. Returns (base_url, device_info) or None."""
    candidates = []
    if preferred_base:
        candidates.append(preferred_base)
    for scheme, port in ([] if only_preferred and preferred_base else _probe_list()):
        default = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
        base = f"{scheme}://{host}" if default else f"{scheme}://{host}:{port}"
        if base not in candidates:
            candidates.append(base)
    for base in candidates:
        u = urllib.parse.urlparse(base)
        if not _tcp_open(u.hostname or host, u.port or (443 if u.scheme == "https" else 80)):
            continue
        try:
            info = parse_json(http_command(base, "getStatusEx", timeout=timeout))
        except Exception:
            continue
        if isinstance(info, dict) and (info.get("DeviceName") or info.get("uuid") or info.get("project")):
            return base, info
    return None


def _local_ipv4s() -> list[str]:
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    try:  # the interface used for the default route
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 9))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127.") and not ip.startswith("169.254."))


# ip -> UPnP description URL, filled in by SSDP
UPNP_LOCATIONS: dict[str, str] = {}


def ssdp_discover(timeout: float = 3.0) -> set[str]:
    """Return IPs of UPnP devices on the LAN, remembering their description URLs."""
    targets = ["urn:schemas-upnp-org:device:MediaRenderer:1", "upnp:rootdevice"]
    found: set[str] = set()
    local_ips = _local_ipv4s()
    socks = []
    for ip in local_ips or ["0.0.0.0"]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            if ip != "0.0.0.0":
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(ip))
            s.bind((ip, 0))
            s.setblocking(False)
            socks.append(s)
        except OSError:
            continue
    try:
        for s in socks:
            for st in targets:
                msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
                       'MAN: "ssdp:discover"\r\nMX: 2\r\nST: ' + st + "\r\n\r\n").encode()
                for _ in range(2):
                    try:
                        s.sendto(msg, ("239.255.255.250", 1900))
                    except OSError:
                        pass
        end = time.time() + timeout
        while time.time() < end and socks:
            r, _, _ = select.select(socks, [], [], 0.25)
            for s in r:
                try:
                    data, addr = s.recvfrom(65507)
                except OSError:
                    continue
                if b" 200 " not in data[:20]:
                    continue
                found.add(addr[0])
                m = re.search(rb"(?im)^location:\s*(\S+)", data)
                if m:
                    loc = m.group(1).decode(errors="ignore")
                    cur = UPNP_LOCATIONS.get(addr[0])
                    if not cur or ("description.xml" in loc and "description.xml" not in cur):
                        UPNP_LOCATIONS[addr[0]] = loc
    finally:
        for s in socks:
            s.close()
    return found - set(local_ips)


# ---- UPnP SOAP ----------------------------------------------------------------------

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def upnp_find_services(host: str, timeout: float = 3.0):
    """Return {service_type: control_url} for a speaker, or None."""
    locs = []
    if UPNP_LOCATIONS.get(host):
        locs.append(UPNP_LOCATIONS[host])
    for p in _upnp_ports():
        u = f"http://{host}:{p}/description.xml"
        if u not in locs:
            locs.append(u)
    for loc in locs:
        u = urllib.parse.urlparse(loc)
        if not _tcp_open(u.hostname or host, u.port or 80, 1.0):
            continue
        try:
            with _OPENER.open(loc, timeout=timeout) as resp:
                xml_text = resp.read()
            root = ET.fromstring(xml_text)
        except Exception:
            continue
        base = loc
        for el in root.iter():
            if _local(el.tag) == "URLBase" and (el.text or "").strip():
                base = el.text.strip()
        services = {}
        for svc in root.iter():
            if _local(svc.tag) != "service":
                continue
            fields = {_local(c.tag): (c.text or "").strip() for c in svc}
            st, ctl = fields.get("serviceType", ""), fields.get("controlURL", "")
            if st and ctl:
                services[st] = urllib.parse.urljoin(base, ctl)
        if any("AVTransport" in k for k in services):
            UPNP_LOCATIONS[host] = loc
            return services
    return None


def soap_call(control_url: str, service: str, action: str, args: dict | None = None,
              timeout: float = POLL_TIMEOUT) -> dict:
    args = args or {}
    inner = "".join(f"<{k}>{html.escape(str(v))}</{k}>" for k, v in args.items())
    body = ('<?xml version="1.0" encoding="utf-8"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
            f'<u:{action} xmlns:u="{service}">{inner}</u:{action}></s:Body></s:Envelope>')
    req = urllib.request.Request(control_url, data=body.encode("utf-8"), method="POST", headers={
        "Content-Type": 'text/xml; charset="utf-8"',
        "SOAPAction": f'"{service}#{action}"',
    })
    with _OPENER.open(req, timeout=timeout) as resp:
        text = resp.read()
    root = ET.fromstring(text)
    for el in root.iter():
        if _local(el.tag) == f"{action}Response":
            return {_local(c.tag): (c.text or "") for c in el}
    return {}


def parse_didl(didl: str) -> dict:
    """Track details from UPnP metadata. These are plain text (never hex-encoded)."""
    out = {}
    if not didl or not didl.strip() or didl.strip().upper() == "NOT_IMPLEMENTED":
        return out
    text = didl
    if "&lt;" in text[:200]:
        text = html.unescape(text)
    text = re.sub(r"&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", "&amp;", text)
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        for key, pat in (("title", r"<dc:title>(.*?)</dc:title>"),
                         ("artist", r"<upnp:artist[^>]*>(.*?)</upnp:artist>"),
                         ("album", r"<upnp:album>(.*?)</upnp:album>"),
                         ("art", r"<upnp:albumArtURI[^>]*>(.*?)</upnp:albumArtURI>")):
            m = re.search(pat, text, re.S)
            if m:
                out[key] = clean_text(html.unescape(m.group(1)))
        return {k: v for k, v in out.items() if v}
    for el in root.iter():
        name = _local(el.tag)
        val = clean_text(el.text)
        if not val:
            continue
        if name == "title" and "title" not in out:
            out["title"] = val
        elif name in ("artist", "creator") and "artist" not in out:
            out["artist"] = val
        elif name == "album" and "album" not in out:
            out["album"] = val
        elif name == "albumArtURI" and "art" not in out:
            out["art"] = val
    return out


def hms_to_sec(v) -> float:
    try:
        parts = [float(p) for p in str(v).strip().split(":")]
    except ValueError:
        return 0.0
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return sec


def sec_to_hms(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


# --------------------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------------------

# key -> (label, value for the switchmode command)
INPUTS = {
    "wifi": ("Wi-Fi", "wifi"),
    "bluetooth": ("Bluetooth", "bluetooth"),
    "line-in": ("Line in", "line-in"),
    "line-in-2": ("Line in 2", "line-in-2"),
    "optical": ("Optical", "optical"),
    "coaxial": ("Coaxial", "coaxial"),
    "rca": ("RCA", "RCA"),
    "hdmi": ("HDMI", "hdmi"),
}
INPUT_ORDER = list(INPUTS)

# plm_support bit -> input (bit 0 = line in, 1 = Bluetooth, 3 = optical, 5 = coaxial, 7 = line in 2)
PLM_BITS = {0: "line-in", 1: "bluetooth", 3: "optical", 5: "coaxial", 7: "line-in-2"}

# names speakers use in InputList -> input
INPUT_NAMES = {
    "bluetooth": "bluetooth", "bt": "bluetooth", "linein": "line-in", "aux": "line-in", "auxin": "line-in",
    "linein2": "line-in-2", "optical": "optical", "spdif": "optical", "coaxial": "coaxial", "coax": "coaxial",
    "rca": "rca", "hdmi": "hdmi",
}

# Models whose own report is known to be wrong or incomplete (confirmed by owners, via pywiim).
MODEL_INPUTS = {
    "addonc5mkiispeaker": ["bluetooth", "rca"],
    "a28speaker": ["bluetooth", "optical", "rca", "hdmi"],
    "link2wirelessmultiroomhifiplayer": ["bluetooth", "optical", "coaxial", "rca"],
}

# HTTP "mode" / UPnP "PlayMode" number -> the physical input that is active
MODE_INPUT = {"4": "line-in", "40": "line-in", "60": "line-in", "47": "line-in-2", "5": "bluetooth",
              "41": "bluetooth", "6": "optical", "43": "optical", "44": "rca", "49": "hdmi"}
MEDIUM_INPUT = {"LINE-IN": "line-in", "LINEIN": "line-in", "BLUETOOTH": "bluetooth", "OPTICAL": "optical",
                "COAXIAL": "coaxial", "RCA": "rca", "HDMI": "hdmi"}


def inputs_from_info(info: dict) -> list[str]:
    project = re.sub(r"[^a-z0-9]", "", str(info.get("project") or "").lower())
    if project in MODEL_INPUTS:
        return ["wifi"] + MODEL_INPUTS[project]
    found = set()
    plm = str(info.get("plm_support") or "").strip()
    if plm:
        try:
            bits = int(plm, 16) if "x" in plm.lower() else int(plm)
            found |= {name for bit, name in PLM_BITS.items() if bits & (1 << bit)}
        except ValueError:
            pass
    raw = info.get("InputList") or info.get("inputList") or info.get("input_list") or []
    if isinstance(raw, str):
        raw = raw.split(",")
    for item in raw if isinstance(raw, list) else []:
        name = INPUT_NAMES.get(re.sub(r"[^a-z0-9]", "", str(item).lower()))
        if name:
            found.add(name)
    if not found:
        found = {"bluetooth", "line-in"}  # every Audio Pro multiroom speaker has at least these
    return ["wifi"] + [k for k in INPUT_ORDER if k in found]


# --------------------------------------------------------------------------------------
# Speaker model
# --------------------------------------------------------------------------------------

OFFLINE_AFTER = 3          # failed polls in a row before a speaker is shown as offline
SLOW_EVERY = 4             # device info + group membership every Nth poll
REPROBE_SECONDS = 600      # how often to re-check a feature a speaker said it doesn't have


class Speaker:
    """One speaker. Works out by itself how this particular unit likes to be talked to.

    First-generation speakers report everything over the HTTP API. The MkII generation only
    answers device questions there (over HTTPS with a client certificate) and reports playback,
    track and volume over UPnP. Rather than guessing from the model name, each feature is tried
    and the answer remembered, so both generations (and firmware in between) take the right path.
    """

    def __init__(self, host: str, base: str | None = None, name: str | None = None, uuid: str = ""):
        self.host = host
        self.base = base
        self.name = name or host
        self.uuid = uuid or ""
        self.model = ""
        self.firmware = ""
        self.info: dict = {}
        # reachability
        self.online = False
        self.seen = False              # at least one poll has finished
        self.fails = 0
        self.last_error = ""
        self.poll_count = 0
        self.lock = threading.Lock()
        self.via = None                # (master, ip on the master's network) for WiFi Direct followers
        # playback
        self.state = "stop"
        self.reported_state = "stop"
        self.title = ""
        self.artist = ""
        self.album = ""
        self.art = ""
        self.track_uri = ""
        self.position = 0.0
        self.duration = 0.0
        self.volume = 0
        self.muted = False
        self.mode = ""
        self.medium = ""
        self.medium_label = ""
        self.hold_volume_until = 0.0
        self.hold_state_until = 0.0
        # features, learned at run time: None = not tried yet
        self.status_cmd: str | None = None      # HTTP status command that works ("" = none does)
        self.status_miss = 0
        self.status_checked = 0.0
        self.infoex_ok: bool | None = None       # UPnP GetInfoEx
        self.infoex_checked = 0.0
        self.cdi_ok: bool | None = None          # UPnP GetControlDeviceInfo
        self.meta_ok: bool | None = None         # HTTP getMetaInfo
        self.meta_checked = 0.0
        self.presets: list[dict] = []
        self.presets_checked = 0.0
        self.inputs = ["wifi", "bluetooth", "line-in"]
        self.linein_cmd = "line-in"
        self.linein_checked = False
        # grouping
        self.group_flag = False       # the speaker says it is following another one
        self.master_ip = ""
        self.master_uuid = ""
        self.slaves: list[dict] = []  # followers this speaker reports: {ip, uuid, name, volume, mute}
        self.pending = ""             # "joining" / "leaving" while a group change is under way
        self.pending_until = 0.0
        # upnp
        self.upnp: dict | None = None
        self.upnp_checked = 0.0
        self.upnp_fails = 0
        self._media_info: dict | None = None
        self._meta_for: tuple | None = None
        self._meta: dict = {}
        self._meta_at = 0.0
        self._neterr = False

    # -- identity --------------------------------------------------------------------
    @property
    def key(self) -> str:
        """Stable identity: the speaker's built-in UUID (survives IP address changes)."""
        return self.uuid or self.host

    @property
    def secure(self) -> bool:
        return bool(self.base) and self.base.startswith("https")

    @property
    def generation(self) -> str:
        if not self.base:
            return ""
        return "MkII generation" if self.secure else "First generation"

    @property
    def reachable(self) -> bool:
        return self.online or self.via is not None

    def to_json(self):
        return {"host": self.host, "base": self.base, "name": self.name, "uuid": self.uuid}

    def move_to(self, host: str, base: str, info: dict):
        """The speaker got a new IP address from the router."""
        self.host = host
        self.base = base
        self.upnp = None
        self.upnp_checked = 0.0
        self._apply_info(info)
        self._mark_alive()

    # -- connection ------------------------------------------------------------------
    def connect(self, quick: bool = False) -> bool:
        """Find the speaker. `quick` only knocks on the door that worked last time."""
        result = probe_host(self.host, self.base, only_preferred=quick)
        if not result:
            return False
        self.base, info = result
        self._apply_info(info)
        return True

    def _mark_alive(self):
        self.fails = 0
        self.online = True
        self.via = None
        self.last_error = ""

    def _mark_failed(self, why: str):
        self.fails += 1
        self.last_error = why
        if self.fails >= OFFLINE_AFTER or not self.seen:
            self.online = False

    def _apply_info(self, info: dict):
        self.info = info
        self.name = decode_text(info.get("DeviceName")) or self.name
        self.uuid = str(info.get("uuid") or self.uuid)
        self.model = _model_name(info)
        self.firmware = str(info.get("firmware") or "")
        self.group_flag = str(info.get("group", "0")).strip() not in ("0", "", "None")
        self.master_ip = str(info.get("master_ip") or info.get("host_ip") or "") if self.group_flag else ""
        self.master_uuid = str(info.get("master_uuid") or "") if self.group_flag else ""
        self.inputs = inputs_from_info(info)

    def cmd(self, command: str, timeout: float = HTTP_TIMEOUT) -> str:
        if not self.base and not self.connect():
            raise SpeakerError(f"{self.name} isn't responding")
        return http_command(self.base, command, timeout)

    def do(self, command: str) -> str:
        """Send a command that changes something; retry once, and notice a refusal."""
        try:
            text = self.cmd(command)
        except urllib.error.HTTPError:
            raise SpeakerError(f"{self.name} doesn't support this")
        except NET_ERRORS as exc:
            if _timed_out(exc):
                raise
            time.sleep(0.25)
            text = self.cmd(command)
        if reply_failed(text):
            raise SpeakerError(f"{self.name} doesn't support this")
        return text

    # -- upnp ------------------------------------------------------------------------
    def _services(self):
        if self.upnp is None and time.time() - self.upnp_checked > 20:
            self.upnp_checked = time.time()
            self.upnp = upnp_find_services(self.host)
            self.upnp_fails = 0
        return self.upnp

    def _svc(self, kind: str):
        svcs = self._services() or {}
        for st, url in svcs.items():
            if kind in st:
                return st, url
        return None

    def upnp_call(self, kind: str, action: str, args: dict | None = None, timeout: float = POLL_TIMEOUT) -> dict:
        svc = self._svc(kind)
        if not svc:
            raise SpeakerError("UPnP not available")
        st, url = svc
        base_args = {"InstanceID": 0}
        base_args.update(args or {})
        return soap_call(url, st, action, base_args, timeout)

    def _upnp_failed(self):
        # After a restart a speaker can move its UPnP service to another port: look for it again.
        self.upnp_fails += 1
        if self.upnp_fails >= 3:
            self.upnp = None
            self.upnp_checked = time.time() - 15
            UPNP_LOCATIONS.pop(self.host, None)

    def _upnp_transport(self) -> dict | None:
        """Playback details over UPnP; None when UPnP isn't answering."""
        now = time.time()
        info = None
        if self.infoex_ok is not False or now - self.infoex_checked > REPROBE_SECONDS:
            self.infoex_checked = now
            try:
                got = self.upnp_call("AVTransport", "GetInfoEx")
                self.infoex_ok = bool(got.get("CurrentTransportState"))
                if self.infoex_ok:
                    info = got
            except urllib.error.HTTPError:
                self.infoex_ok = False      # a SOAP fault: this speaker has no GetInfoEx
            except NET_ERRORS:
                return None
        if info is None:
            try:
                info = dict(self.upnp_call("AVTransport", "GetTransportInfo"))
            except NET_ERRORS:
                return None
            try:
                info.update(self.upnp_call("AVTransport", "GetPositionInfo"))
            except NET_ERRORS:
                pass
            try:
                if self.poll_count % 3 == 0 or self._media_info is None:
                    self._media_info = self.upnp_call("AVTransport", "GetMediaInfo")
                mi = self._media_info
                info.setdefault("PlayMedium", mi.get("PlayMedium", ""))
                if not (info.get("TrackMetaData") or "").strip():
                    info["TrackMetaData"] = mi.get("CurrentURIMetaData", "")
                if not (info.get("TrackURI") or "").strip():
                    info["TrackURI"] = mi.get("CurrentURI", "")
            except NET_ERRORS:
                self._media_info = None
        return info

    def _upnp_volume(self):
        """(volume, muted, play mode) over UPnP; any of them None when not available."""
        vol = mute = mode = None
        if not self._svc("RenderingControl"):
            return vol, mute, mode
        if self.cdi_ok is not False:
            try:
                d = self.upnp_call("RenderingControl", "GetControlDeviceInfo")
                if str(d.get("CurrentVolume", "")).strip() != "":
                    self.cdi_ok = True
                    vol = int(float(d["CurrentVolume"]))
                    mute = str(d.get("CurrentMute", "0")).strip().lower() in ("1", "true")
                    mode = str(d.get("PlayMode", "")).strip() or None
                    return vol, mute, mode
                self.cdi_ok = False
            except urllib.error.HTTPError:
                self.cdi_ok = False
            except NET_ERRORS:
                return vol, mute, mode
        try:
            v = self.upnp_call("RenderingControl", "GetVolume", {"Channel": "Master"})
            vol = int(float(v.get("CurrentVolume", "")))
        except NET_ERRORS:
            pass
        try:
            m = self.upnp_call("RenderingControl", "GetMute", {"Channel": "Master"})
            mute = str(m.get("CurrentMute", "0")).strip().lower() in ("1", "true")
        except NET_ERRORS:
            pass
        return vol, mute, mode

    # -- http status -----------------------------------------------------------------
    def _http_status(self) -> dict | None:
        """Player status over the HTTP API, or None when this speaker doesn't report one."""
        now = time.time()
        if self.status_cmd == "":
            if now - self.status_checked < REPROBE_SECONDS:
                return None
            self.status_cmd = None
        candidates = [self.status_cmd] if self.status_cmd else ["getPlayerStatusEx", "getPlayerStatus"]
        refused = 0
        for c in candidates:
            try:
                d = parse_json(self.cmd(c, POLL_TIMEOUT))
            except urllib.error.HTTPError:
                refused += 1
                continue
            except NET_ERRORS:
                self._neterr = True
                return None                     # busy or away right now: learn nothing from it
            if isinstance(d, dict) and str(d.get("status", "")).strip():
                self.status_cmd, self.status_miss = c, 0
                return d
            refused += 1
        if refused == len(candidates):
            self.status_miss += 1
            if self.status_cmd is None or self.status_miss >= 3:
                self.status_cmd, self.status_miss, self.status_checked = "", 0, now
        return None

    def _http_meta(self) -> dict:
        now = time.time()
        if self.meta_ok is False and now - self.meta_checked < REPROBE_SECONDS:
            return {}
        self.meta_checked = now
        try:
            d = parse_json(self.cmd("getMetaInfo", POLL_TIMEOUT))
        except urllib.error.HTTPError:
            self.meta_ok = False
            return {}
        except NET_ERRORS:
            return {}
        md = d.get("metaData") if isinstance(d, dict) else None
        if not isinstance(md, dict):
            self.meta_ok = False
            return {}
        self.meta_ok = True
        return md

    # -- polling ---------------------------------------------------------------------
    def refresh(self, full: bool = False):
        self.poll_count += 1
        try:
            self._refresh(full)
        except Exception as exc:        # never let one odd reply stop the polling
            self._mark_failed(str(exc))
        finally:
            self.seen = True

    def _gone(self) -> bool:
        """True when nothing is listening at the speaker's address any more (switched off, moved)."""
        u = urllib.parse.urlparse(self.base or "")
        return not _tcp_open(u.hostname or self.host, u.port or (443 if u.scheme == "https" else 80), 1.5)

    def _refresh(self, full: bool):
        self._neterr = False
        if self.fails and self.online and self._gone():
            self._mark_failed("not reachable")      # already missed a round and the door is shut
            return
        if not self.base or not self.online:
            # away for a while: mostly just knock on the usual door, now and then try them all
            if not self.connect(quick=self.fails % 4 != 0):
                self._mark_failed("not reachable")
                return
            full = True
            self.fails = 0
            self.online = True
        answered = False
        slow = full or self.poll_count % SLOW_EVERY == 0
        if slow:
            try:
                info = parse_json(self.cmd("getStatusEx", POLL_TIMEOUT))
                if isinstance(info, dict) and info:
                    self._apply_info(info)
                    answered = True
            except NET_ERRORS:
                self._neterr = True
            if answered:
                self._refresh_slaves()
                self._refresh_extras()

        st = self._http_status()
        if st is None and not answered and self._neterr and self._gone():
            self._mark_failed("not reachable")
            return
        up = self._upnp_transport() if self._svc("AVTransport") else None
        if up is None and self.upnp:
            self._upnp_failed()
        elif up is not None:
            self.upnp_fails = 0
        answered = answered or st is not None or up is not None

        if not answered:
            why = "no answer"
            if self._gone():
                why = "not reachable"
            elif not slow:                # nothing answered this round: is it still there at all?
                try:
                    self.cmd("getStatusEx", POLL_TIMEOUT)
                    answered = True
                except NET_ERRORS as exc:
                    why = str(exc) or why
            if not answered:
                self._mark_failed(why)
                return
        self._mark_alive()
        if st is not None or up is not None:
            self._merge(st, up)

    def _merge(self, st: dict | None, up: dict | None):
        """Combine what the two channels reported into one picture."""
        now = time.time()
        title = artist = album = art = ""
        state = None
        vol = mute = None
        pos = dur = None
        uri = ""
        mode = None

        if st is not None:
            state = PLAY_STATES.get(str(st.get("status", "")).strip().lower(), "stop")
            mode = str(st.get("mode", "")).strip() or None
            if str(st.get("vol", "")).strip() != "":
                try:
                    vol = int(float(st.get("vol")))
                    mute = str(st.get("mute", "0")).strip() == "1"
                except (TypeError, ValueError):
                    pass
            title, artist, album = (decode_text(st.get(k)) for k in ("Title", "Artist", "Album"))
            pos, dur = api_time_to_sec(st.get("curpos")), api_time_to_sec(st.get("totlen"))

        medium = ""
        if up is not None:
            ust = PLAY_STATES.get(str(up.get("CurrentTransportState", "")).strip().lower())
            if ust:
                state = ust               # UPnP sees play/pause/stop first and is right on both generations
            md = parse_didl(up.get("TrackMetaData", ""))
            if md.get("title"):           # the track's own description, when there is one, beats the HTTP text
                title, artist, album = md["title"], md.get("artist", "") or artist, md.get("album", "") or album
            art = md.get("art", "")
            uri = clean_text(up.get("TrackURI"))
            if "RelTime" in up and ":" in str(up.get("RelTime")):
                upos, udur = hms_to_sec(up.get("RelTime")), hms_to_sec(up.get("TrackDuration"))
                if udur > 0 or not dur:
                    pos, dur = upos, udur
            medium = (clean_text(up.get("TrackSource")) or clean_text(up.get("PlayMedium"))).upper()
            self.medium = clean_text(up.get("PlayMedium")).upper()
            # Volume: the MkII generation keeps it on UPnP (its HTTP side can lag or lack it);
            # the first generation reports it with the HTTP status.
            if self.secure or vol is None or mute is None:
                uvol, umute, umode = self._upnp_volume()
                if uvol is None and str(up.get("CurrentVolume", "")).strip() != "":
                    try:
                        uvol = int(float(up["CurrentVolume"]))
                    except (TypeError, ValueError):
                        pass
                vol = uvol if uvol is not None else vol
                mute = umute if umute is not None else mute
                if umode and (mode in (None, "0")):
                    mode = umode
        else:
            self.medium = ""

        if state in ("play", "pause") and (not title or not art) and self.meta_ok is not False:
            track = (title, artist, uri, medium)
            # once per song, not once per poll (and only now and then while there is no title at all)
            if track != self._meta_for or (not title and now - self._meta_at > 10):
                self._meta_for, self._meta, self._meta_at = track, self._http_meta(), now
            md = self._meta
            title = title or decode_text(md.get("title"))
            artist = artist or decode_text(md.get("artist"))
            album = album or decode_text(md.get("album"))
            if not art:
                art = clean_text(md.get("albumArtURI"))

        if state is not None:
            self.reported_state = state          # what the speaker itself says, never our guess
            if now > self.hold_state_until:
                self.state = state
        if now > self.hold_volume_until:
            if vol is not None:
                self.volume = max(0, min(100, vol))
            if mute is not None:
                self.muted = mute
        self.title, self.artist, self.album = title, artist, album
        self.art = art if art.lower().startswith("http") else ""
        self.track_uri = uri
        self.position = pos or 0.0
        self.duration = dur or 0.0
        if mode is not None:
            self.mode = mode
        label = MEDIUM_NAMES.get(medium, "")
        service = clean_text((up or {}).get("TrackSource"))
        if not label and service and medium not in MEDIUM_NAMES and re.fullmatch(r"[\w .+-]{2,20}", service):
            label = service               # a streaming service we have no nicer name for
        self.medium_label = label

    def _refresh_slaves(self):
        try:
            data = parse_json(self.cmd("multiroom:getSlaveList", POLL_TIMEOUT))
        except NET_ERRORS:
            return
        out = []
        lst = data.get("slave_list") if isinstance(data, dict) else None
        for item in lst if isinstance(lst, list) else []:
            if not isinstance(item, dict):
                continue
            try:
                vol = int(float(item.get("volume")))
            except (TypeError, ValueError):
                vol = None
            out.append({"ip": str(item.get("ip") or ""), "uuid": str(item.get("uuid") or ""),
                        "name": decode_text(item.get("name")), "volume": vol,
                        "mute": str(item.get("mute", "0")).strip() == "1"})
        self.slaves = out

    def _refresh_extras(self):
        """Things that rarely change: presets, and how this model wants its line input selected."""
        now = time.time()
        if now - self.presets_checked > (300 if self.presets else REPROBE_SECONDS):
            self.presets_checked = now
            presets = []
            try:
                d = parse_json(self.cmd("getPresetInfo", POLL_TIMEOUT))
                for p in (d.get("preset_list") or []) if isinstance(d, dict) else []:
                    if not isinstance(p, dict):
                        continue
                    name = clean_text(p.get("name"))
                    if not name or not str(p.get("number", "")).strip().isdigit():
                        continue
                    pic = clean_text(p.get("picurl") or p.get("pic_url"))
                    presets.append({"n": int(p["number"]), "name": name,
                                    "pic": pic if pic.lower().startswith("http") else ""})
            except NET_ERRORS:
                presets = self.presets
            self.presets = sorted(presets, key=lambda p: p["n"])
        if not self.linein_checked and "line-in" in self.inputs:
            self.linein_checked = True
            project = re.sub(r"[^a-z0-9]", "", str(self.info.get("project") or "").lower())
            if "a10" in project and "mk" in project:
                # A10 MkII ignores "line-in" and wants the name it advertises itself.
                try:
                    d = parse_json(self.cmd("getAudioInputCapbility", POLL_TIMEOUT))
                    modes = [str(i.get("mode")) for i in (d.get("audioInput") or []) if isinstance(i, dict)]
                    if "auxIn" in modes:
                        self.linein_cmd = "auxIn"
                except (NET_ERRORS, AttributeError):
                    self.linein_checked = False

    # -- actions ---------------------------------------------------------------------
    def _transport(self, http_cmd: str, upnp_action: str):
        """Playback buttons: the HTTP command first, the UPnP action if that is refused."""
        try:
            self.do(http_cmd)
        except (SpeakerError, *NET_ERRORS) as first:
            try:
                self.upnp_call("AVTransport", upnp_action, {"Speed": 1} if upnp_action == "Play" else None,
                               timeout=HTTP_TIMEOUT)
            except (SpeakerError, *NET_ERRORS):
                raise first

    def _set_state(self, state: str):
        self.state = state
        self.hold_state_until = time.time() + 2.0

    def play(self):
        if self.state == "pause":
            try:
                self._transport("setPlayerCmd:resume", "Play")
            except (SpeakerError, *NET_ERRORS):
                self._transport("setPlayerCmd:play", "Play")
        else:
            self._transport("setPlayerCmd:play", "Play")
        self._set_state("play")

    def pause(self):
        self._transport("setPlayerCmd:pause", "Pause")
        self._set_state("pause")

    def stop(self):
        self._transport("setPlayerCmd:stop", "Stop")
        self._set_state("stop")

    def play_pause(self):
        if self.state == "play":
            self.pause()
        else:
            self.play()

    def next(self):
        self._transport("setPlayerCmd:next", "Next")

    def prev(self):
        self._transport("setPlayerCmd:prev", "Previous")

    def set_volume(self, vol: int):
        vol = max(0, min(100, int(vol)))
        self.volume = vol
        self.hold_volume_until = time.time() + 2.5
        if self.via and not self.online:
            master, ip = self.via
            master.do(f"multiroom:SlaveVolume:{ip}:{vol}")
            return
        try:
            self.do(f"setPlayerCmd:vol:{vol}")
        except (SpeakerError, *NET_ERRORS) as first:
            try:
                self.upnp_call("RenderingControl", "SetVolume", {"Channel": "Master", "DesiredVolume": vol},
                               timeout=HTTP_TIMEOUT)
            except (SpeakerError, *NET_ERRORS):
                raise first

    def set_mute(self, mute: bool):
        self.muted = mute
        self.hold_volume_until = time.time() + 2.5
        if self.via and not self.online:
            master, ip = self.via
            master.do(f"multiroom:SlaveMute:{ip}:{1 if mute else 0}")
            return
        try:
            self.do(f"setPlayerCmd:mute:{1 if mute else 0}")
        except (SpeakerError, *NET_ERRORS) as first:
            try:
                self.upnp_call("RenderingControl", "SetMute", {"Channel": "Master", "DesiredMute": 1 if mute else 0},
                               timeout=HTTP_TIMEOUT)
            except (SpeakerError, *NET_ERRORS):
                raise first

    def seek(self, seconds: float):
        seconds = max(0.0, float(seconds))
        try:
            self.upnp_call("AVTransport", "Seek", {"Unit": "REL_TIME", "Target": sec_to_hms(seconds)},
                           timeout=HTTP_TIMEOUT)
        except (SpeakerError, *NET_ERRORS):
            self.do(f"setPlayerCmd:seek:{int(seconds)}")
        self.position = seconds

    def play_url(self, url: str, didl: str = "", method: str = "upnp") -> str:
        """Play a stream URL (local music). Returns which way worked: "upnp" or "http"."""
        order = ["http", "upnp"] if method == "http" else ["upnp", "http"]
        last: Exception = SpeakerError(f"{self.name} isn't responding")
        for m in order:
            try:
                if m == "upnp":
                    self.upnp_call("AVTransport", "SetAVTransportURI",
                                   {"CurrentURI": url, "CurrentURIMetaData": didl}, timeout=HTTP_TIMEOUT)
                    self.upnp_call("AVTransport", "Play", {"Speed": 1}, timeout=HTTP_TIMEOUT)
                else:
                    self.do(f"setPlayerCmd:play:{url}")
                self._set_state("play")
                self.track_uri = url
                self.position = 0.0
                return m
            except (SpeakerError, *NET_ERRORS) as exc:
                last = exc
        raise last

    def set_input(self, key: str):
        if key not in INPUTS or key not in self.inputs:
            raise SpeakerError(f"{self.name} doesn't have that input")
        value = self.linein_cmd if key == "line-in" else INPUTS[key][1]
        self.do(f"setPlayerCmd:switchmode:{value}")

    def play_preset(self, n: int):
        self.do(f"MCUKeyShortClick:{int(n)}")

    # -- grouping --------------------------------------------------------------------
    def needs_wifi_direct(self) -> bool:
        """Very old firmware groups over its own WiFi network instead of through the router."""
        if self.secure:
            return False
        wmrm = str(self.info.get("wmrm_version") or "").strip()
        if wmrm.startswith("2"):
            return True
        if wmrm.startswith("4"):
            return False
        m = re.match(r"^\D*(\d+)\.(\d+)\.(\d+)", self.firmware or "")
        if not m:
            return False
        ver = tuple(int(x) for x in m.groups())
        return ver[0] in (3, 4) and ver < (4, 2, 8020)

    def join(self, master: "Speaker") -> bool:
        """Make this speaker play whatever `master` plays. Returns True for a WiFi Direct join."""
        if master.needs_wifi_direct() or self.needs_wifi_direct():
            ssid = str(master.info.get("ssid") or "")
            ch = master.info.get("WifiChannel") or 1
            if ssid:
                ssid_hex = binascii.hexlify(ssid.encode("utf-8")).decode()
                self.do(f"ConnectMasterAp:ssid={ssid_hex}:ch={ch}:auth=OPEN:encry=NONE:pwd=:chext=0")
                return True
        self.do(f"ConnectMasterAp:JoinGroupMaster:eth{master.host}:wifi0.0.0.0")
        return False

    def slave_entry(self, sp: "Speaker") -> dict | None:
        for e in self.slaves:
            if same_uuid(e.get("uuid"), sp.uuid) or (e.get("ip") and e["ip"] == sp.host):
                return e
        return None

    def kick(self, slave: "Speaker"):
        entry = self.slave_entry(slave)
        self.do(f"multiroom:SlaveKickout:{(entry or {}).get('ip') or slave.host}")

    def ungroup(self):
        self.do("multiroom:Ungroup")

    # -- labels ----------------------------------------------------------------------
    def active_input(self) -> str:
        """Which input is selected right now."""
        key = MODE_INPUT.get(self.mode) or MEDIUM_INPUT.get(self.medium)
        return key if key in self.inputs else "wifi"

    def source_label(self) -> str:
        if self.medium_label:
            return self.medium_label
        label = MODE_NAMES.get(self.mode, "")
        return "" if label in ("Idle", "Grouped") else label


def _model_name(info: dict) -> str:
    project = str(info.get("project") or "").strip()
    if not project:
        return "Audio Pro"
    p = project.replace("_", " ").replace("-", " ")
    p = re.sub(r"(?i)^audio ?pro ?", "", p).strip()
    p = re.sub(r"(?i)\s*speaker$", "", p).strip()
    p = re.sub(r"(?i)mk ?ii", "MkII", p)
    p = re.sub(r"(?i)^addon", "Addon", p)
    return " ".join(w.upper() if re.fullmatch(r"[a-zA-Z]\d+", w) else w for w in p.split()) or project


def diagnostics(sp: Speaker) -> str:
    out = [f"== {sp.name} ({sp.host}) base={sp.base} fw={sp.firmware} model={sp.model} "
           f"[{sp.generation}] online={sp.online} fails={sp.fails} last_error={sp.last_error!r}",
           f"[learned] status_cmd={sp.status_cmd!r} infoex={sp.infoex_ok} controldeviceinfo={sp.cdi_ok} "
           f"metainfo={sp.meta_ok} inputs={sp.inputs} linein={sp.linein_cmd} wifi_direct={sp.needs_wifi_direct()}",
           f"[now] state={sp.state} mode={sp.mode!r} medium={sp.medium!r} vol={sp.volume} mute={sp.muted} "
           f"title={sp.title!r} uri={sp.track_uri!r}"]
    for c in ("getStatusEx", "getPlayerStatusEx", "getPlayerStatus", "getMetaInfo", "multiroom:getSlaveList",
              "getPresetInfo"):
        try:
            out.append(f"[{c}] {http_command(sp.base, c)[:1500]}")
        except Exception as exc:
            out.append(f"[{c}] ERROR {exc}")
    out.append(f"[upnp location] {UPNP_LOCATIONS.get(sp.host)}  services={sp.upnp}")
    for kind, action, args in (("AVTransport", "GetInfoEx", None), ("AVTransport", "GetTransportInfo", None),
                               ("AVTransport", "GetPositionInfo", None), ("AVTransport", "GetMediaInfo", None),
                               ("RenderingControl", "GetControlDeviceInfo", None),
                               ("RenderingControl", "GetVolume", {"Channel": "Master"})):
        try:
            out.append(f"[upnp {action}] {json.dumps(sp.upnp_call(kind, action, args))[:1500]}")
        except Exception as exc:
            out.append(f"[upnp {action}] ERROR {exc}")
    return "\n".join(out)

# --------------------------------------------------------------------------------------
# Local music library
# --------------------------------------------------------------------------------------

AUDIO_TYPES = {
    ".mp3": "audio/mpeg", ".flac": "audio/flac", ".m4a": "audio/mp4", ".aac": "audio/aac",
    ".wav": "audio/wav", ".ogg": "audio/ogg", ".oga": "audio/ogg", ".opus": "audio/ogg",
    ".wma": "audio/x-ms-wma",
}


def _dec(enc: int, b: bytes) -> str:
    try:
        if enc == 0:
            return b.decode("latin-1")
        if enc == 1:
            return b.decode("utf-16")
        if enc == 2:
            return b.decode("utf-16-be")
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("latin-1", errors="replace")


def _split_term(enc: int, b: bytes):
    """Split at the encoding-appropriate NUL terminator -> (head, rest)."""
    if enc in (1, 2):
        i = 0
        while i + 1 < len(b):
            if b[i] == 0 and b[i + 1] == 0:
                return b[:i], b[i + 2:]
            i += 2
        return b, b""
    i = b.find(b"\x00")
    return (b, b"") if i < 0 else (b[:i], b[i + 1:])


def _syncsafe(b: bytes) -> int:
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def read_id3(f) -> tuple[dict, int]:
    """Returns (tags, size_of_tag_block). tags may contain title/artist/album/tlen/pic=(mime, offset, length)."""
    f.seek(0)
    head = f.read(10)
    if len(head) < 10 or head[:3] != b"ID3":
        return {}, 0
    ver, flags = head[3], head[5]
    size = _syncsafe(head[6:10])
    total = 10 + size + (10 if flags & 0x10 else 0)
    data = f.read(size)
    tags: dict = {}
    pos = 0
    if flags & 0x40 and ver >= 3 and len(data) >= 4:  # extended header
        ext = _syncsafe(data[:4]) if ver == 4 else int.from_bytes(data[:4], "big") + 4
        pos = ext
    names = {"TIT2": "title", "TPE1": "artist", "TALB": "album", "TLEN": "tlen", "TPE2": "albumartist",
             "TRCK": "track", "TT2": "title", "TP1": "artist", "TAL": "album", "TLE": "tlen",
             "TP2": "albumartist", "TRK": "track"}
    while pos < len(data):
        if ver == 2:
            if pos + 6 > len(data):
                break
            fid = data[pos:pos + 3].decode("latin-1", errors="ignore")
            fsize = int.from_bytes(data[pos + 3:pos + 6], "big")
            hdr = 6
        else:
            if pos + 10 > len(data):
                break
            fid = data[pos:pos + 4].decode("latin-1", errors="ignore")
            raw = data[pos + 4:pos + 8]
            fsize = _syncsafe(raw) if ver == 4 else int.from_bytes(raw, "big")
            hdr = 10
        if not fid.strip("\x00") or fsize <= 0:
            break
        body = data[pos + hdr:pos + hdr + fsize]
        if fid in names and body:
            val = _dec(body[0], body[1:]).strip("\x00").strip()
            if val and names[fid] not in tags:
                tags[names[fid]] = val.split("\x00")[0]
        elif fid in ("APIC", "PIC") and body and "pic" not in tags and not flags & 0x80:
            enc = body[0]
            if fid == "APIC":
                mime, rest = _split_term(0, body[1:])
                mime = mime.decode("latin-1", errors="ignore") or "image/jpeg"
            else:
                fmt = body[1:4].decode("latin-1", errors="ignore").upper()
                mime, rest = ("image/png" if fmt == "PNG" else "image/jpeg"), body[4:]
            if rest:
                _desc, img = _split_term(enc, rest[1:])
                if img:
                    off = 10 + pos + hdr + (len(body) - len(img))
                    if "/" not in mime:
                        mime = "image/" + mime.lower()
                    tags["pic"] = (mime, off, len(img))
        pos += hdr + fsize
    return tags, total


_BITRATES = {
    (3, 1): [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
    (2, 1): [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
}
_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def mp3_duration(f, start: int, file_size: int) -> float:
    f.seek(start)
    buf = f.read(64 * 1024)
    i = 0
    while i + 4 <= len(buf):
        if buf[i] == 0xFF and (buf[i + 1] & 0xE0) == 0xE0:
            b1, b2, b3 = buf[i + 1], buf[i + 2], buf[i + 3]
            ver = (b1 >> 3) & 3          # 3=MPEG1 2=MPEG2 0=MPEG2.5
            layer = (b1 >> 1) & 3        # 1 = Layer III
            bri, sri = b2 >> 4, (b2 >> 2) & 3
            if ver == 1 or layer != 1 or bri in (0, 15) or sri == 3:
                i += 1
                continue
            table = _BITRATES[(3, 1)] if ver == 3 else _BITRATES[(2, 1)]
            bitrate = table[bri] * 1000
            rate = _RATES[ver][sri]
            mono = (b3 >> 6) == 3
            spf = 1152 if ver == 3 else 576
            xoff = (32 if not mono else 17) if ver == 3 else (17 if not mono else 9)
            x = buf[i + 4 + xoff:i + 4 + xoff + 12]
            if x[:4] in (b"Xing", b"Info") and len(x) >= 12 and (int.from_bytes(x[4:8], "big") & 1):
                frames = int.from_bytes(x[8:12], "big")
                return frames * spf / rate
            v = buf[i + 36:i + 36 + 18]
            if v[:4] == b"VBRI" and len(v) >= 18:
                frames = int.from_bytes(v[14:18], "big")
                return frames * spf / rate
            return max(0.0, (file_size - start - i) * 8 / bitrate) if bitrate else 0.0
        i += 1
    return 0.0


def read_flac(f) -> dict:
    f.seek(0)
    if f.read(4) != b"fLaC":
        return {}
    tags: dict = {}
    while True:
        h = f.read(4)
        if len(h) < 4:
            break
        last, btype, size = h[0] & 0x80, h[0] & 0x7F, int.from_bytes(h[1:4], "big")
        start = f.tell()
        if btype == 0:
            d = f.read(size)
            rate = (d[10] << 12) | (d[11] << 4) | (d[12] >> 4)
            total = ((d[13] & 0x0F) << 32) | int.from_bytes(d[14:18], "big")
            if rate:
                tags["duration"] = total / rate
        elif btype == 4:
            d = f.read(size)
            vlen = int.from_bytes(d[:4], "little")
            p = 4 + vlen
            n = int.from_bytes(d[p:p + 4], "little")
            p += 4
            for _ in range(n):
                ln = int.from_bytes(d[p:p + 4], "little")
                kv = d[p + 4:p + 4 + ln].decode("utf-8", errors="replace")
                p += 4 + ln
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    k = k.lower()
                    if k in ("title", "artist", "album") and k not in tags:
                        tags[k] = v
        elif btype == 6 and "pic" not in tags:
            d = f.read(size)
            p = 4
            ml = int.from_bytes(d[p:p + 4], "big")
            mime = d[p + 4:p + 4 + ml].decode("latin-1", errors="ignore")
            p += 4 + ml
            dl = int.from_bytes(d[p:p + 4], "big")
            p += 4 + dl + 16
            il = int.from_bytes(d[p:p + 4], "big")
            p += 4
            tags["pic"] = (mime or "image/jpeg", start + p, il)
        f.seek(start + size)
        if last:
            break
    return tags


def wav_duration(f, file_size: int) -> float:
    f.seek(0)
    h = f.read(64)
    if h[:4] != b"RIFF" or h[8:12] != b"WAVE":
        return 0.0
    i = h.find(b"fmt ")
    if i < 0:
        return 0.0
    byte_rate = int.from_bytes(h[i + 16:i + 20], "little")
    return (file_size - 44) / byte_rate if byte_rate else 0.0

_MP4_CONTAINERS = {b"moov", b"udta", b"ilst", b"trak", b"mdia"}
_MP4_TEXT = {b"\xa9nam": "title", b"\xa9ART": "artist", b"\xa9alb": "album", b"aART": "albumartist"}


def read_mp4(f, file_size: int) -> dict:
    """Tags, cover and length of an .m4a / .mp4 audio file."""
    tags: dict = {}

    def walk(start: int, end: int, depth: int):
        pos = start
        while pos + 8 <= end and depth < 8:
            f.seek(pos)
            head = f.read(8)
            if len(head) < 8:
                return
            size, kind = int.from_bytes(head[:4], "big"), head[4:8]
            body = pos + 8
            if size == 1:
                size = int.from_bytes(f.read(8), "big")
                body = pos + 16
            elif size == 0:
                size = end - pos
            if size < 8 or pos + size > end:
                return
            stop = pos + size
            if kind in _MP4_CONTAINERS:
                walk(body, stop, depth + 1)
            elif kind == b"meta":
                walk(body + 4, stop, depth + 1)      # version/flags come first
            elif kind == b"mvhd":
                f.seek(body)
                d = f.read(32)
                if d and d[0] == 1:
                    scale, length = int.from_bytes(d[20:24], "big"), int.from_bytes(d[24:32], "big")
                else:
                    scale, length = int.from_bytes(d[12:16], "big"), int.from_bytes(d[16:20], "big")
                if scale:
                    tags["duration"] = length / scale
            elif kind in _MP4_TEXT or kind in (b"trkn", b"covr"):
                f.seek(body)
                dh = f.read(16)                       # the nested "data" atom: size, "data", type, locale
                if len(dh) == 16 and dh[4:8] == b"data":
                    dlen = int.from_bytes(dh[:4], "big") - 16
                    dtype = int.from_bytes(dh[8:12], "big")
                    if kind == b"covr":
                        if dlen > 0 and "pic" not in tags:
                            tags["pic"] = ("image/png" if dtype == 14 else "image/jpeg", body + 16, dlen)
                    elif kind == b"trkn":
                        d = f.read(min(dlen, 8))
                        if len(d) >= 4:
                            tags["track"] = str(int.from_bytes(d[2:4], "big"))
                    elif 0 < dlen <= 2048:
                        val = f.read(dlen).decode("utf-8", errors="replace").strip("\x00").strip()
                        if val:
                            tags.setdefault(_MP4_TEXT[kind], val)
            pos = stop

    walk(0, file_size, 0)
    return tags


def read_tags(path: str) -> dict:
    ext = os.path.splitext(path)[1].lower()
    st = os.stat(path)
    tags: dict = {}
    try:
        with open(path, "rb") as f:
            if ext == ".mp3":
                tags, start = read_id3(f)
                if "tlen" in tags:
                    try:
                        tags["duration"] = int(re.sub(r"\D", "", tags["tlen"])) / 1000.0
                    except ValueError:
                        pass
                if not tags.get("duration"):
                    tags["duration"] = mp3_duration(f, start, st.st_size)
                if "title" not in tags and st.st_size > 128:
                    f.seek(-128, 2)
                    v1 = f.read(128)
                    if v1[:3] == b"TAG":
                        for k, a, b in (("title", 3, 33), ("artist", 33, 63), ("album", 63, 93)):
                            v = v1[a:b].split(b"\x00")[0].decode("latin-1").strip()
                            if v:
                                tags.setdefault(k, v)
            elif ext == ".flac":
                tags = read_flac(f)
            elif ext in (".m4a", ".mp4", ".m4b"):
                tags = read_mp4(f, st.st_size)
            elif ext == ".wav":
                tags = {"duration": wav_duration(f, st.st_size)}
    except Exception:
        pass
    tags.pop("tlen", None)
    if not tags.get("artist") and tags.get("albumartist"):
        tags["artist"] = tags["albumartist"]
    m = re.match(r"\s*(\d+)", str(tags.get("track") or ""))
    tags["track"] = int(m.group(1)) if m else 0
    if not tags["track"]:               # "07 Song name.mp3"
        m = re.match(r"^(\d{1,3})[\s.\-_]+\S", os.path.basename(path))
        tags["track"] = int(m.group(1)) if m else 0
    if not tags.get("title"):
        stem = os.path.splitext(os.path.basename(path))[0]
        m = re.match(r"^(\d{1,3})[\s.\-_]+(.*)$", stem)
        if m and m.group(2).strip():
            tags["track"] = tags["track"] or int(m.group(1))
            stem = m.group(2).strip()
        if " - " in stem and not tags.get("artist"):
            a, t = stem.split(" - ", 1)
            tags["artist"], tags["title"] = a.strip(), t.strip()
        else:
            tags["title"] = stem
    if not tags.get("album"):
        tags["album"] = os.path.basename(os.path.dirname(path))
    return tags


CACHE_FORMAT = 3     # bump when the tag reader learns something new, so files are read again


class Track:
    __slots__ = ("id", "path", "title", "artist", "albumartist", "album", "duration", "pic", "folder",
                 "mtime", "size", "track", "group")

    def __init__(self, path: str, folder: str, tags: dict, mtime: float, size: int):
        import hashlib
        self.id = hashlib.sha1(path.encode("utf-8", "surrogatepass")).hexdigest()[:16]
        self.path = path
        self.folder = folder
        self.title = tags.get("title", "")
        self.artist = tags.get("artist", "")
        self.albumartist = tags.get("albumartist", "")
        self.album = tags.get("album", "")
        self.duration = float(tags.get("duration") or 0)
        self.track = int(tags.get("track") or 0)
        self.pic = tags.get("pic")
        self.mtime, self.size = mtime, size
        # songs in one folder with one album name are one album, whoever the track artists are
        key = (os.path.dirname(path) + "\n" + self.album.lower()).encode("utf-8", "surrogatepass")
        self.group = hashlib.sha1(key).hexdigest()[:10]

    def to_ui(self):
        return {"id": self.id, "title": self.title, "artist": self.artist, "aa": self.albumartist,
                "album": self.album, "g": self.group, "n": self.track, "duration": round(self.duration),
                "art": bool(self.pic), "added": int(self.mtime)}

    def to_cache(self):
        return {"title": self.title, "artist": self.artist, "albumartist": self.albumartist,
                "album": self.album, "duration": self.duration, "track": self.track,
                "pic": list(self.pic) if self.pic else None, "mtime": self.mtime, "size": self.size}


class Library:
    def __init__(self, cfg_dir: str):
        self.cfg_dir = cfg_dir
        self.settings_path = os.path.join(cfg_dir, "library.json")
        self.cache_path = os.path.join(cfg_dir, "library_cache.json")
        self.folders: list[str] = []
        self.tracks: dict[str, Track] = {}
        self.order: list[str] = []
        self.version = 0
        self.scanning = False
        self.again = False
        self.lock = threading.Lock()
        data = read_json(self.settings_path, {})
        if isinstance(data, dict):
            self.folders = [p for p in data.get("folders", []) if isinstance(p, str)]

    def save(self):
        write_json(self.settings_path, {"folders": self.folders}, indent=2)

    def add_folder(self, path: str) -> bool:
        path = os.path.normpath(path)
        if any(os.path.normcase(path) == os.path.normcase(p) for p in self.folders):
            return False
        self.folders.append(path)
        self.save()
        return True

    def remove_folder(self, path: str):
        if path in self.folders:
            self.folders.remove(path)
            self.save()

    def scan(self, on_progress=None):
        with self.lock:
            if self.scanning:
                self.again = True       # folders changed while reading: go round once more afterwards
                return
            self.scanning = True
        try:
            while True:
                self.again = False
                self._scan_once(on_progress)
                if not self.again:
                    break
        finally:
            self.scanning = False

    def _scan_once(self, on_progress=None):
        saved = read_json(self.cache_path, {})
        cache = saved.get("files", {}) if isinstance(saved, dict) and saved.get("format") == CACHE_FORMAT else {}
        tracks: dict[str, Track] = {}
        new_cache = {}
        seen_dirs = set()
        for folder in list(self.folders):
            for dirpath, dirnames, filenames in os.walk(folder):
                real = os.path.normcase(os.path.realpath(dirpath))
                if real in seen_dirs:               # overlapping folders: count each song once
                    dirnames[:] = []
                    continue
                seen_dirs.add(real)
                dirnames.sort(key=str.lower)
                for name in sorted(filenames, key=str.lower):
                    if os.path.splitext(name)[1].lower() not in AUDIO_TYPES or name.startswith("._"):
                        continue
                    p = os.path.join(dirpath, name)
                    try:
                        st = os.stat(p)
                    except OSError:
                        continue
                    c = cache.get(p)
                    if c and c.get("mtime") == st.st_mtime and c.get("size") == st.st_size:
                        tags = dict(c)
                        if tags.get("pic"):
                            tags["pic"] = tuple(tags["pic"])
                    else:
                        tags = read_tags(p)
                    t = Track(p, folder, tags, st.st_mtime, st.st_size)
                    tracks[t.id] = t
                    new_cache[p] = t.to_cache()
                    if on_progress and len(tracks) % 200 == 0:
                        on_progress(len(tracks))
        order = sorted(tracks, key=lambda k: ((tracks[k].albumartist or tracks[k].artist).lower(),
                                              tracks[k].album.lower(), tracks[k].track, tracks[k].path.lower()))
        self.tracks, self.order = tracks, order
        self.version += 1
        write_json(self.cache_path, {"format": CACHE_FORMAT, "files": new_cache})

    def art_bytes(self, tid: str):
        t = self.tracks.get(tid)
        if not t or not t.pic:
            return None
        mime, off, ln = t.pic
        try:
            with open(t.path, "rb") as f:
                f.seek(off)
                return mime, f.read(ln)
        except OSError:
            return None


# --------------------------------------------------------------------------------------
# HTTP plumbing (media server for speakers, UI server for the app window)
# --------------------------------------------------------------------------------------

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402


class _QuietServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def handle_error(self, request, client_address):
        pass  # speakers drop connections all the time; don't spam stderr


def _send_file_range(handler: BaseHTTPRequestHandler, path: str, ctype: str, head_only: bool):
    try:
        size = os.path.getsize(path)
    except OSError:
        handler.send_error(404)
        return
    start, end = 0, size - 1
    rng = handler.headers.get("Range")
    status = 200
    if rng:
        m = re.match(r"bytes=(\d*)-(\d*)", rng)
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                if m.group(2):
                    end = min(int(m.group(2)), size - 1)
            else:
                start = max(0, size - int(m.group(2)))
            if start >= size or end < start:
                handler.send_response(416)
                handler.send_header("Content-Range", f"bytes */{size}")
                handler.send_header("Content-Length", "0")
                handler.end_headers()
                return
            status = 206
    length = end - start + 1
    handler.send_response(status)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Content-Length", str(length))
    if status == 206:
        handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    handler.send_header("transferMode.dlna.org", "Streaming")
    handler.send_header("contentFeatures.dlna.org", "DLNA.ORG_OP=01;DLNA.ORG_FLAGS=01700000000000000000000000000000")
    handler.end_headers()
    if head_only:
        return
    try:
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                handler.wfile.write(chunk)
                remaining -= len(chunk)
    except (ConnectionError, OSError):
        handler.close_connection = True


def make_media_handler(ctl: "Controller"):
    class MediaHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _route(self, head_only):
            parts = urllib.parse.urlparse(self.path).path.split("/")
            if len(parts) >= 3 and parts[1] == "m":
                t = ctl.library.tracks.get(parts[2])
                if t:
                    ctl.media_hits[t.id] = time.time()          # a speaker really did come for the file
                    ext = os.path.splitext(t.path)[1].lower()
                    _send_file_range(self, t.path, AUDIO_TYPES.get(ext, "application/octet-stream"), head_only)
                    return
            if len(parts) >= 3 and parts[1] == "art":
                art = ctl.library.art_bytes(parts[2].split(".")[0])
                if art:
                    self.send_response(200)
                    self.send_header("Content-Type", art[0])
                    self.send_header("Content-Length", str(len(art[1])))
                    self.end_headers()
                    if not head_only:
                        self.wfile.write(art[1])
                    return
            self.send_error(404)

        def do_GET(self):
            self._route(False)

        def do_HEAD(self):
            self._route(True)

    return MediaHandler


# --------------------------------------------------------------------------------------
# Controller: speakers, groups, queue, state for the UI
# --------------------------------------------------------------------------------------

class PlayQueue:
    def __init__(self, track_ids: list[str], index: int):
        self.ids = track_ids
        self.index = index
        self.url = ""
        self.method = "upnp"       # how the speaker was told to play: "upnp" or "http"
        self.started = 0.0
        self.saw_playing = False
        self.retried = False
        self.stopped_polls = 0
        self.fail_streak = 0
        self.last_pos = 0.0
        self.last_dur = 0.0
        self.active = True


def _route_ip_for(host: str) -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((host, 9))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        ips = _local_ipv4s()
        return ips[0] if ips else "127.0.0.1"


def friendly_error(exc: Exception, sp: "Speaker | None" = None) -> str:
    if isinstance(exc, SpeakerError):
        return str(exc)
    if isinstance(exc, NET_ERRORS) and not isinstance(exc, (ValueError, ET.ParseError)):
        return f"{sp.name if sp else 'The speaker'} isn't responding"
    return str(exc) or exc.__class__.__name__


class Controller:
    def __init__(self):
        self.cfg_dir = _config_dir()
        self.cfg_path = os.path.join(self.cfg_dir, "speakers.json")
        self.settings_path = os.path.join(self.cfg_dir, "settings.json")
        self.speakers: list[Speaker] = []
        self.library = Library(self.cfg_dir)
        # 3.1-3.3 had a Spotify sign-in; it was removed in 3.4, so don't leave its tokens behind
        try:
            os.remove(os.path.join(self.cfg_dir, "spotify.json"))
        except OSError:
            pass
        self.pool = cf.ThreadPoolExecutor(max_workers=16)
        self.queues: dict[int, PlayQueue] = {}
        self.media_hits: dict[str, float] = {}
        self.version = 0
        self.cond = threading.Condition()
        self.toast = ("", 0.0)
        self.scanning = False
        self.media_port = 0
        self.started_at = time.time()
        self.sleep_at = 0.0
        self.group_lock = threading.Lock()
        self.grouping = False
        self.art_cache: dict[str, tuple] = {}
        self._stop = threading.Event()
        self._last_saved = None
        self._rediscovering = False
        self._rediscovered_at = 0.0
        self._rediscoveries = 0
        self._ssdp_at = 0.0
        self._not_speakers: dict[str, float] = {}
        settings = read_json(self.settings_path, {})
        settings = settings if isinstance(settings, dict) else {}
        self.repeat = bool(settings.get("repeat"))
        self.ignored: set[str] = {str(x) for x in settings.get("ignored", []) if x}
        self._load()

    # -- persistence -----------------------------------------------------------------
    def _load(self):
        data = read_json(self.cfg_path, [])
        for d in data if isinstance(data, list) else []:
            if not (isinstance(d, dict) and d.get("host")):
                continue
            uid = str(d.get("uuid") or "")
            if (uid and self.find(uid)) or self.find(d["host"]):
                continue
            self.speakers.append(Speaker(d["host"], d.get("base"), d.get("name"), uid))

    def _save(self):
        snap = [s.to_json() for s in self.speakers]
        if snap == self._last_saved:
            return
        self._last_saved = snap
        write_json(self.cfg_path, snap, indent=2)

    def _save_settings(self):
        write_json(self.settings_path, {"repeat": self.repeat, "ignored": sorted(self.ignored)}, indent=2)

    def find(self, key: str) -> Speaker | None:
        if not key:
            return None
        return (next((s for s in self.speakers if s.uuid and s.uuid == key), None)
                or next((s for s in self.speakers if s.host == key), None))

    def _same_speaker(self, sp: Speaker) -> Speaker | None:
        """An already-known entry that is really this speaker (maybe at an old IP address)."""
        for s in self.speakers:
            if s is not sp and sp.uuid and s.uuid == sp.uuid:
                return s
        for s in self.speakers:
            if s is not sp and s.host == sp.host and (not s.uuid or s.uuid == sp.uuid):
                return s
        for s in self.speakers:
            # entries saved by older versions have no uuid: match those by name while they're offline
            if s is not sp and not s.uuid and not s.online and s.name and s.name == sp.name:
                return s
        return None

    def _merge_duplicates(self, sp: Speaker):
        """Once a speaker has reported its uuid, drop stale entries for the same box."""
        if not sp.uuid or not sp.online:
            return
        removed = False
        for s in list(self.speakers):
            if s is sp:
                continue
            same_box = s.uuid == sp.uuid
            old_entry = not s.uuid and s.name == sp.name and (not s.online or s.host == sp.host)
            if same_box or old_entry:
                self.speakers.remove(s)
                self.queues.pop(id(s), None)
                removed = True
        if removed:
            self._save()
            self.changed()

    # -- change notification ---------------------------------------------------------
    def changed(self):
        with self.cond:
            self.version += 1
            self.cond.notify_all()

    def say(self, text: str):
        self.toast = (text, time.time())
        self.changed()

    # -- lifecycle -------------------------------------------------------------------
    def start(self):
        threading.Thread(target=self._poll_loop, daemon=True).start()
        self.scan(quiet=bool(self.speakers))
        if self.library.folders:
            self.rescan_library()

    def _poll_loop(self):
        tick = 0
        while not self._stop.is_set():
            tick += 1
            try:
                self._poll_once(tick)
            except Exception:
                pass
            self._stop.wait(1.0)

    def _poll_once(self, tick: int):
        now = time.time()
        if self.sleep_at and now >= self.sleep_at:
            self.sleep_at = 0.0
            self.pool.submit(self._sleep_now)

        # A speaker that stopped answering has usually been given a new IP address by the router:
        # search the network for it — soon after it went quiet, then less and less often, because
        # a portable speaker that is simply switched off is normal.
        missing = [s for s in self.speakers if s.seen and not s.reachable]
        if not missing:
            self._rediscoveries = 0
        elif not (self.scanning or self._rediscovering):
            wait = 8 if self._rediscoveries < 2 else 60 if self._rediscoveries < 8 else 300
            if now - self._rediscovered_at > wait:
                self._rediscoveries += 1
                self.scan(quiet=True)
        # UPnP ports can move after a speaker restarts; SSDP tells us where they went.
        if (now - self._ssdp_at > 120 and not self.scanning and not self._rediscovering
                and any(s.online and s.upnp is None for s in self.speakers)):
            self._ssdp_at = now
            self.pool.submit(ssdp_discover)

        for sp in list(self.speakers):
            if sp.lock.locked():
                continue
            q = self.queues.get(id(sp))
            if not sp.online and sp.seen:
                due = tick % (6 if sp.fails < 12 else 15) == 0     # away: look in on it now and then
            elif q and q.active:
                due = True                      # playing from this PC: watch for the end of the song
            else:
                due = tick % 2 == 0
            if due:
                self.refresh(sp)

    def refresh(self, sp: Speaker, full=False):
        def task():
            if not sp.lock.acquire(timeout=8):
                return
            try:
                sp.refresh(full=full)
            finally:
                sp.lock.release()
            try:
                if sp in self.speakers:
                    self._merge_duplicates(sp)
                    self._sync_followers(sp)
                    self._check_queue(sp)
                self._save()
            finally:
                self.changed()
        try:
            self.pool.submit(task)
        except RuntimeError:
            pass

    def refresh_all(self, full=True):
        for sp in list(self.speakers):
            self.refresh(sp, full=full)

    # -- topology --------------------------------------------------------------------
    def master_of(self, sp: Speaker) -> Speaker | None:
        for m in self.speakers:
            if m is not sp and m.slave_entry(sp):
                return m
        if sp.group_flag and sp.online:
            for m in self.speakers:
                if m is sp:
                    continue
                if (sp.master_ip and m.host == sp.master_ip) or same_uuid(sp.master_uuid, m.uuid):
                    return m
        return None

    def followers_of(self, master: Speaker) -> list[Speaker]:
        return [s for s in self.speakers if s is not master and self.master_of(s) is master]

    def leader(self, sp: Speaker) -> Speaker:
        return self.master_of(sp) or sp

    def _sync_followers(self, master: Speaker):
        """Followers that left the home network to follow `master` (WiFi Direct groups, used by
        old firmware) can only be seen and controlled through it."""
        for s in self.speakers:
            if s is master:
                continue
            entry = master.slave_entry(s) if master.online else None
            if entry and not s.online and s.seen:
                s.via = (master, entry.get("ip") or s.host)
                if time.time() > s.hold_volume_until:
                    if entry.get("volume") is not None:
                        s.volume = entry["volume"]
                    s.muted = bool(entry.get("mute"))
            elif s.via and s.via[0] is master:
                s.via = None

    # -- speakers --------------------------------------------------------------------
    def add_speaker(self, sp: Speaker) -> bool:
        """Returns True if this is a speaker we didn't know before."""
        old = self._same_speaker(sp)
        if old is not None:
            if old.host != sp.host or not old.online:
                old.move_to(sp.host, sp.base, sp.info)
                self._save()
                self.refresh(old, full=True)
                self.changed()
            return False
        if self.find(sp.host):
            return False
        self.speakers.append(sp)
        self._save()
        self.refresh(sp, full=True)
        self.changed()
        return True

    def remove_speaker(self, sp: Speaker):
        if sp in self.speakers:
            self.speakers.remove(sp)
        self.queues.pop(id(sp), None)
        self.ignored.add(sp.key)        # or the next search would bring it straight back
        self._save()
        self._save_settings()
        self.changed()

    def scan(self, quiet: bool = False):
        if self.scanning or self._rediscovering:
            if not quiet and not self.scanning:
                self.scanning = True        # a background search is under way: show it and report it
                self.changed()
            return
        self.scanning = not quiet
        self._rediscovering = quiet
        self._rediscovered_at = self._ssdp_at = time.time()
        if not quiet:
            self._not_speakers.clear()
            self.changed()

        def work(quiet=quiet):
            try:
                ips = ssdp_discover()
                now = time.time()
                known = {s.host for s in self.speakers if s.online}
                todo = [ip for ip in ips if ip not in known and now - self._not_speakers.get(ip, 0) > 900]
                futs = {self.pool.submit(probe_host, ip): ip for ip in todo}
                found = []
                for f in cf.as_completed(futs):
                    res = f.result()
                    if not res:
                        self._not_speakers[futs[f]] = now     # a TV, a router...: don't keep asking
                        continue
                    sp = Speaker(futs[f], res[0])
                    sp._apply_info(res[1])
                    sp.online = sp.seen = True
                    found.append(sp)
                quiet = not self.scanning
                if quiet:
                    found = [sp for sp in found if sp.key not in self.ignored or self._same_speaker(sp)]
                elif any(sp.key in self.ignored for sp in found):
                    self.ignored -= {sp.key for sp in found}
                    self._save_settings()
                new = [sp for sp in sorted(found, key=lambda s: s.name.lower()) if self.add_speaker(sp)]
                if new:
                    names = ", ".join(sp.name for sp in new[:3]) + ("…" if len(new) > 3 else "")
                    self.say(f"Found {names}")
                elif quiet:
                    pass
                elif not self.speakers:
                    self.say("No speakers found — try adding one by IP address")
                else:
                    self.say("No new speakers found")
            except Exception as exc:
                if not quiet:
                    self.say(f"Search failed: {exc}")
            finally:
                self.scanning = False
                self._rediscovering = False
                self.changed()

        self.pool.submit(work)

    def add_ip(self, ip: str) -> str:
        host = re.sub(r"^\w+://", "", ip.strip()).split("/")[0].split(":")[0].strip()
        if not re.fullmatch(r"[A-Za-z0-9.\-]{1,253}", host or ""):
            raise SpeakerError("That doesn't look like an IP address")
        sp = Speaker(host)
        if not sp.connect():
            raise SpeakerError(f"No Audio Pro speaker answered at {host}")
        sp.online = sp.seen = True
        self.ignored.discard(sp.key)
        self._save_settings()
        self.add_speaker(sp)
        return sp.name

    # -- grouping --------------------------------------------------------------------
    def _mark_pending(self, sp: Speaker, what: str, seconds: float = 30):
        sp.pending, sp.pending_until = what, time.time() + seconds

    def apply_group(self, master: Speaker | None, wanted: list[Speaker]):
        """Make `wanted` the group led by `master`. Runs in the background; the result is announced."""
        if not self.group_lock.acquire(blocking=False):
            raise SpeakerError("Still linking speakers — one moment")
        try:
            wanted_ids = {id(s) for s in wanted}
            leave, dissolve, join = [], [], []
            for sp in self.speakers:
                m = self.master_of(sp)
                if m is None:
                    continue
                # leaving this group, or coming over from another one; other groups are left alone
                if (m is master and id(sp) not in wanted_ids) or (id(sp) in wanted_ids and m is not master):
                    leave.append((sp, m))
            if master is not None:
                for sp in wanted:
                    if sp is not master and self.followers_of(sp):
                        dissolve.append(sp)
                join = [sp for sp in wanted if sp is not master and self.master_of(sp) is not master]
                away = [sp.name for sp in join if not sp.reachable]
                if away:
                    raise SpeakerError(f"{away[0]} is offline")
                if join and not master.reachable:
                    raise SpeakerError(f"{master.name} is offline")
            if not (leave or dissolve or join):
                self.group_lock.release()
                return
            for sp, _m in leave:
                self._mark_pending(sp, "leaving")
            for sp in join:
                self._mark_pending(sp, "joining")
            self.grouping = True
            self.changed()
        except BaseException:
            self.group_lock.release()
            raise
        self.pool.submit(self._run_group_change, master, leave, dissolve, join)

    def _run_group_change(self, master, leave, dissolve, join):
        problems = []
        try:
            for sp, m in leave:
                try:
                    try:
                        m.kick(sp)
                    except (SpeakerError, *NET_ERRORS):
                        sp.ungroup()
                    m.slaves = [e for e in m.slaves if e is not m.slave_entry(sp)]
                    sp.group_flag, sp.via = False, None
                except (SpeakerError, *NET_ERRORS) as exc:
                    problems.append(f"{sp.name} couldn't leave ({friendly_error(exc, sp)})")
                self.changed()
                time.sleep(0.3)
            for sp in dissolve:
                try:
                    sp.ungroup()
                    sp.slaves = []
                except (SpeakerError, *NET_ERRORS):
                    pass
                time.sleep(0.3)
            if join and (leave or dissolve):
                time.sleep(2.0)             # a speaker that just left a group needs a moment to settle

            wifi_direct = False
            sent = []
            for sp in join:
                try:
                    wifi_direct = sp.join(master) or wifi_direct
                    sent.append(sp)
                except (SpeakerError, *NET_ERRORS) as exc:
                    problems.append(f"{sp.name} couldn't join ({friendly_error(exc, sp)})")
                    sp.pending = ""
                time.sleep(0.4)

            # Speakers say "OK" to a join even when it then fails, so look at the result.
            if sent:
                deadline = time.time() + (30 if wifi_direct else 14)
                time.sleep(6 if wifi_direct else 1.5)
                waiting = list(sent)
                while waiting and time.time() < deadline:
                    with master.lock:
                        master._refresh_slaves()
                    for sp in list(waiting):
                        if not master.slave_entry(sp) and sp.online:
                            with sp.lock:
                                sp.refresh(full=True)
                        if self.master_of(sp) is master:
                            waiting.remove(sp)
                            sp.pending = ""
                    self._sync_followers(master)
                    self.changed()
                    if waiting:
                        time.sleep(1.5)
                problems += [f"{sp.name} didn't join {master.name}" for sp in waiting]
            if problems:
                self.say(problems[0] + (f" (+{len(problems) - 1} more)" if len(problems) > 1 else ""))
            elif join:
                group = [master] + self.followers_of(master)
                self.say("Playing together: " + " + ".join(s.name for s in group[:4])
                         + ("…" if len(group) > 4 else ""))
            elif leave:
                self.say("Ungrouped" if len(leave) > 1 else f"{leave[0][0].name} left the group")
        except Exception as exc:
            self.say(f"Linking failed: {friendly_error(exc)}")
        finally:
            for sp in self.speakers:
                sp.pending = ""
            self.grouping = False
            self.group_lock.release()
            self.refresh_all()
            self.changed()

    def play_everywhere(self, prefer: Speaker | None = None):
        able = [s for s in self.speakers if s.reachable]
        if len(able) < 2:
            raise SpeakerError("Need at least two speakers that are switched on")
        leaders = [s for s in able if self.master_of(s) is None] or able
        playing = [s for s in leaders if s.state == "play"]
        chosen = self.leader(prefer) if prefer in able else None
        if chosen in playing:
            master = chosen                 # the one you're looking at is playing: spread that
        elif playing:
            master = max(playing, key=lambda s: len(self.followers_of(s)))   # never spread silence
        else:
            master = chosen or next((s for s in leaders if self.followers_of(s)), None) or leaders[0]
        self.apply_group(master, able)

    def group_of(self, sp: Speaker) -> list[Speaker]:
        lead = self.leader(sp)
        return [lead] + self.followers_of(lead)

    def set_group_volume(self, master: Speaker, v: int):
        group = [s for s in self.group_of(master) if s.reachable]
        if len(group) <= 1:
            master.set_volume(v)
            return
        current = max(sp.volume for sp in group)
        delta = v - current
        for sp in group:
            target = v if current == 0 else max(0, min(100, sp.volume + delta))
            if target != sp.volume:
                sp.volume = target
                sp.hold_volume_until = time.time() + 2.5
                self._background(sp.set_volume, target)

    def _background(self, fn, *args):
        def run():
            try:
                fn(*args)
            except Exception:
                pass
        self.pool.submit(run)

    # -- sleep timer -----------------------------------------------------------------
    def _sleep_now(self):
        paused = 0
        for sp in list(self.speakers):
            if self.master_of(sp) is None and sp.online and sp.state == "play":
                try:
                    sp.pause()
                    paused += 1
                except Exception:
                    try:
                        sp.stop()
                        paused += 1
                    except Exception:
                        pass
        self.say("Sleep timer: music paused" if paused else "Sleep timer finished")

    # -- local music -----------------------------------------------------------------
    def rescan_library(self):
        def work():
            self.changed()
            self.library.scan(on_progress=lambda n: self.changed())
            self.changed()
        self.pool.submit(work)
        threading.Timer(0.15, self.changed).start()

    def _track_url(self, sp: Speaker, t: Track) -> tuple[str, str]:
        ip = _route_ip_for(sp.host)
        ext = os.path.splitext(t.path)[1].lower()
        url = f"http://{ip}:{self.media_port}/m/{t.id}/track{ext}"   # plain name: some speakers choke on odd ones
        art = f"http://{ip}:{self.media_port}/art/{t.id}.jpg" if t.pic else ""
        return url, art

    def _didl(self, t: Track, url: str, art: str) -> str:
        e = html.escape
        ctype = AUDIO_TYPES.get(os.path.splitext(t.path)[1].lower(), "audio/mpeg")
        dur = f' duration="{sec_to_hms(t.duration)}.000"' if t.duration else ""
        return ('<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
                'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
                f'<item id="{t.id}" parentID="0" restricted="1"><dc:title>{e(t.title)}</dc:title>'
                f'<upnp:artist>{e(t.artist)}</upnp:artist><upnp:album>{e(t.album)}</upnp:album>'
                + (f'<upnp:albumArtURI>{e(art)}</upnp:albumArtURI>' if art else "")
                + '<upnp:class>object.item.audioItem.musicTrack</upnp:class>'
                f'<res protocolInfo="http-get:*:{ctype}:*"{dur}>{e(url)}</res></item></DIDL-Lite>')

    def _is_ours(self, uri: str) -> bool:
        return bool(uri) and f":{self.media_port}/m/" in uri

    def play_tracks(self, sp: Speaker, ids: list[str], index: int):
        sp = self.leader(sp)
        ids = [i for i in ids if i in self.library.tracks]
        if not ids:
            raise SpeakerError("Nothing to play")
        old = self.queues.get(id(sp))
        q = PlayQueue(ids, max(0, min(int(index), len(ids) - 1)))
        if old:
            q.method = old.method           # keep using what worked on this speaker
        self.queues[id(sp)] = q
        self._start_queue_track(sp, q)

    def add_to_queue(self, sp: Speaker, ids: list[str], play_next: bool) -> int:
        sp = self.leader(sp)
        ids = [i for i in ids if i in self.library.tracks]
        if not ids:
            raise SpeakerError("Nothing to add")
        q = self.queue_for(sp)
        if not q:
            self.play_tracks(sp, ids, 0)
            return len(ids)
        at = q.index + 1 if play_next else len(q.ids)
        q.ids[at:at] = ids
        self.changed()
        return len(ids)

    def _start_queue_track(self, sp: Speaker, q: PlayQueue, method: str | None = None):
        t = self.library.tracks.get(q.ids[q.index])
        if t is None:
            raise SpeakerError("That song is no longer in the library")
        url, art = self._track_url(sp, t)
        q.url, q.started, q.saw_playing, q.stopped_polls = url, time.time(), False, 0
        q.last_pos, q.last_dur = 0.0, t.duration
        q.active = True
        if method is None:
            q.retried = False
        sp.title, sp.artist, sp.album, sp.duration, sp.position = t.title, t.artist, t.album, t.duration, 0.0
        sp.art = ""
        try:
            q.method = sp.play_url(url, self._didl(t, url, art), method or q.method)
        except Exception:
            q.active = False
            self.changed()
            raise
        self.changed()

    def queue_for(self, sp: Speaker) -> PlayQueue | None:
        q = self.queues.get(id(sp))
        return q if q and q.active else None

    def queue_step(self, sp: Speaker, step: int) -> bool:
        sp = self.leader(sp)
        q = self.queue_for(sp)
        if not q:
            return False
        if step < 0 and sp.position > 5:
            sp.seek(0)
            return True
        nxt = q.index + step
        if nxt >= len(q.ids) and self.repeat:
            nxt = 0
        if 0 <= nxt < len(q.ids):
            q.index = nxt
            self._start_queue_track(sp, q)
        elif nxt >= len(q.ids):
            q.active = False
            try:
                sp.stop()
            except Exception:
                pass
        return True

    def queue_jump(self, sp: Speaker, index: int):
        sp = self.leader(sp)
        q = self.queue_for(sp)
        if not q or not 0 <= index < len(q.ids):
            raise SpeakerError("That song is no longer in the queue")
        q.index = index
        self._start_queue_track(sp, q)

    def _current_track(self, sp: Speaker) -> Track | None:
        """The library song this speaker is playing (or has just finished) from this PC."""
        q = self.queues.get(id(sp))
        if not q or not q.url:
            return None
        if q.active or sp.track_uri == q.url:
            return self.library.tracks.get(q.ids[q.index])
        return None

    def _check_queue(self, sp: Speaker):
        q = self.queues.get(id(sp))
        if not q or not q.active:
            return
        if self.master_of(sp) is not None:
            q.active = False                  # now following another speaker: that one decides what plays
            return
        if not sp.online:
            return
        now = time.time()
        age = now - q.started
        ours = self._is_ours(sp.track_uri)
        other_input = sp.active_input() != "wifi" or sp.source_label() in ("Spotify Connect", "AirPlay",
                                                                         "TIDAL Connect", "Bluetooth")
        if age > 8 and ((sp.track_uri and not ours) or (other_input and not ours)):
            q.active = False                  # something else (Spotify, AirPlay, an input...) took over
            return

        state = sp.reported_state
        if state == "play":
            if not (ours or age > 3):
                return                        # still the previous music; ours hasn't started yet
            q.saw_playing = True
            q.stopped_polls = 0
            q.fail_streak = 0
            q.last_pos = sp.position
            q.last_dur = sp.duration or q.last_dur
            return
        if state != "stop":
            return

        if not q.saw_playing:
            # Told to play, but nothing happened.
            if age > 7 and not q.retried:
                q.retried = True
                other = "http" if q.method == "upnp" else "upnp"
                try:
                    self._start_queue_track(sp, q, method=other)
                except Exception:
                    pass
            elif age > 9 and q.retried:
                self._queue_track_failed(sp, q)
            return

        q.stopped_polls += 1
        if q.stopped_polls < 2 or age < 4:
            return                            # a short stop between songs, or Spotify about to take over
        if q.last_dur > 0 and q.last_pos < q.last_dur - max(3.0, min(8.0, q.last_dur * 0.1)):
            return                            # stopped in the middle: someone pressed stop
        nxt = q.index + 1
        if nxt >= len(q.ids) and self.repeat and len(q.ids) > 0:
            nxt = 0
        if nxt < len(q.ids):
            q.index = nxt
            try:
                self._start_queue_track(sp, q)
            except Exception as exc:
                self.say(f"Couldn't play the next song: {friendly_error(exc, sp)}")
        else:
            q.active = False

    def _queue_track_failed(self, sp: Speaker, q: PlayQueue):
        t = self.library.tracks.get(q.ids[q.index])
        fetched = bool(t) and self.media_hits.get(t.id, 0) >= q.started - 30
        q.fail_streak += 1
        if not fetched:
            q.active = False
            self.say(f"{sp.name} couldn't reach this PC to load the song. Allow Python through "
                     "Windows Firewall on private networks.")
            return
        if q.fail_streak >= 3 or q.index + 1 >= len(q.ids):
            q.active = False
            self.say(f"{sp.name} couldn't play " + ("these files" if q.fail_streak > 1 else "this file"))
            return
        self.say(f"Skipped “{t.title}” — {sp.name} couldn't play it")
        q.index += 1
        try:
            self._start_queue_track(sp, q)
        except Exception:
            q.active = False

    # -- state for the UI ------------------------------------------------------------
    def _art_url(self, sp: Speaker) -> str:
        if not sp.art:
            return ""
        host = urllib.parse.urlparse(sp.art).hostname or ""
        if host == sp.host or host.startswith(("10.", "192.168.", "172.", "169.254.")):
            # pictures stored on the speaker itself need its certificate: fetch them for the page
            return f"/sart/{urllib.parse.quote(sp.key, safe='')}?v={zlib.crc32(sp.art.encode()) & 0xffffffff:x}"
        return sp.art

    def speaker_art(self, key: str):
        sp = self.find(key)
        if not sp or not sp.art:
            return None
        hit = self.art_cache.get(sp.key)
        if hit and hit[0] == sp.art:
            return hit[1], hit[2]
        try:
            with _OPENER.open(sp.art, timeout=6) as r:
                data = r.read(4 * 1024 * 1024)
                ctype = r.headers.get("Content-Type") or "image/jpeg"
        except Exception:
            return None
        self.art_cache[sp.key] = (sp.art, ctype, data)
        return ctype, data

    def state(self) -> dict:
        now = time.time()
        speakers = list(self.speakers)
        masters = {id(sp): self.master_of(sp) for sp in speakers}
        out = []
        for sp in speakers:
            m = masters[id(sp)]
            q = self.queue_for(sp)
            t = self._current_track(sp) if m is None else None
            local = t is not None and (self._is_ours(sp.track_uri) or (q is not None and not sp.track_uri))
            qd = None
            if q:
                nxt = q.ids[q.index + 1: q.index + 31]
                if self.repeat and len(nxt) < 30 and len(q.ids) > 1:
                    nxt = nxt + q.ids[: min(q.index, 30 - len(nxt))]
                qd = {"index": q.index, "total": len(q.ids), "current": q.ids[q.index], "next": nxt}
            if sp.pending and now > sp.pending_until:
                sp.pending = ""
            playing = sp.state in ("play", "pause")
            status = ("online" if sp.online else "linked" if sp.via else
                      "offline" if sp.seen else "connecting")
            out.append({
                "id": sp.key, "ip": sp.host, "name": sp.name, "model": sp.model, "status": status,
                "online": sp.reachable, "generation": sp.generation, "firmware": sp.firmware,
                "secure": sp.secure, "signal": str(sp.info.get("RSSI") or ""),
                "state": sp.state,
                "title": t.title if local else sp.title,
                "artist": t.artist if local else sp.artist,
                "album": t.album if local else sp.album,
                "art": (f"/art/{t.id}" if t.pic else "") if local else self._art_url(sp),
                "source": ("This PC" if local else sp.source_label()) if playing else "",
                "local": bool(local),
                "input": sp.active_input(),
                "inputs": [{"key": k, "label": INPUTS[k][0]} for k in sp.inputs],
                "presets": sp.presets,
                "volume": sp.volume, "muted": sp.muted,
                "position": round(sp.position, 1),
                "duration": round((sp.duration or (t.duration if local else 0)), 1),
                "master": m.key if m else None,
                "pending": sp.pending,
                "queue": qd,
                "error": sp.last_error if not sp.reachable else "",
            })
        msg, ts = self.toast
        return {"speakers": out, "scanning": self.scanning, "grouping": self.grouping,
                "toast": msg, "toast_ts": ts, "repeat": self.repeat,
                "sleep_at": int(self.sleep_at * 1000) if self.sleep_at else 0,
                "library": {"version": self.library.version, "scanning": self.library.scanning,
                            "count": len(self.library.tracks), "folders": self.library.folders},
                "version": APP_VERSION}

    # -- commands from the UI --------------------------------------------------------
    NEEDS_SPEAKER = {"play_pause", "next", "prev", "seek", "volume", "group_volume", "mute", "input", "preset",
                     "ungroup", "remove", "reconnect", "play_tracks", "queue_add", "queue_jump"}

    def command(self, c: dict):
        a = c.get("action")
        sp = self.find(str(c.get("id") or ""))
        if a in self.NEEDS_SPEAKER and sp is None:
            raise SpeakerError("That speaker is no longer in the list")
        lead = self.leader(sp) if sp else None
        try:
            result = self._command(a, c, sp, lead)
        except SpeakerError:
            raise
        except Exception as exc:
            raise SpeakerError(friendly_error(exc, lead or sp)) from exc
        self.changed()
        if sp and sp in self.speakers:
            threading.Timer(0.7, lambda: self.refresh(lead or sp)).start()
        return result or {}

    def _command(self, a, c, sp, lead):
        if a == "play_pause":
            q = self.queues.get(id(lead))
            if (lead.state == "stop" and q and q.url and not q.active
                    and (not lead.track_uri or lead.track_uri == q.url)):
                self._start_queue_track(lead, q)    # the queue ran out: play starts it again
            else:
                lead.play_pause()
        elif a == "next":
            if not self.queue_step(lead, 1):
                lead.next()
        elif a == "prev":
            if not self.queue_step(lead, -1):
                lead.prev()
        elif a == "seek":
            lead.seek(float(c.get("position", 0)))
        elif a == "volume":
            sp.set_volume(int(c["value"]))
        elif a == "group_volume":
            self.set_group_volume(lead, int(c["value"]))
        elif a == "mute":
            target = bool(c.get("value"))
            for s in self.group_of(lead):
                if s.reachable:
                    s.muted = target
                    s.hold_volume_until = time.time() + 2.5
                    self._background(s.set_mute, target)
        elif a == "input":
            lead.set_input(str(c.get("value")))
            q = self.queues.get(id(lead))
            if q:
                q.active = False
        elif a == "preset":
            lead.play_preset(int(c["value"]))
            q = self.queues.get(id(lead))
            if q:
                q.active = False
        elif a == "group":
            master = self.find(str(c.get("master") or ""))
            if master is None:
                raise SpeakerError("That speaker is no longer in the list")
            members = [s for s in (self.find(str(h)) for h in c.get("members", [])) if s]
            if master not in members:
                members.insert(0, master)
            self.apply_group(master, members)
        elif a == "play_everywhere":
            self.play_everywhere(sp)
        elif a == "ungroup":
            self.apply_group(lead, [lead])
        elif a == "scan":
            self.scan()
        elif a == "add_ip":
            return {"name": self.add_ip(str(c.get("ip", "")))}
        elif a == "remove":
            self.remove_speaker(sp)
        elif a == "reconnect":
            sp.online, sp.base, sp.upnp, sp.upnp_checked, sp.fails = False, None, None, 0, 0
            sp.status_cmd = sp.infoex_ok = sp.cdi_ok = sp.meta_ok = None
            self.refresh(sp, full=True)
        elif a == "diagnostics":
            rest = [x for x in self.speakers if x is not sp]
            return {"text": f"{APP_NAME} {APP_VERSION}\n\n"
                            + "\n\n".join(diagnostics(s) for s in ([sp] if sp else []) + rest)}
        elif a == "play_tracks":
            self.play_tracks(sp, list(c.get("ids", [])), int(c.get("index", 0)))
        elif a == "queue_add":
            return {"added": self.add_to_queue(sp, list(c.get("ids", [])), bool(c.get("next")))}
        elif a == "queue_jump":
            self.queue_jump(sp, int(c.get("index", -1)))
        elif a == "repeat":
            self.repeat = bool(c.get("value"))
            self._save_settings()
        elif a == "sleep":
            minutes = max(0, min(600, int(c.get("minutes", 0))))
            self.sleep_at = time.time() + minutes * 60 if minutes else 0.0
        elif a == "add_folder":
            path = c.get("path") or pick_folder()
            if not path:
                return {"path": None}
            if not os.path.isdir(path):
                raise SpeakerError("That folder doesn't exist")
            added = self.library.add_folder(path)
            self.rescan_library()
            return {"path": path, "added": added}
        elif a == "remove_folder":
            self.library.remove_folder(str(c.get("path", "")))
            self.rescan_library()
        elif a == "rescan_library":
            self.rescan_library()
        elif a == "quit":
            threading.Timer(0.3, lambda: os._exit(0)).start()
        else:
            raise SpeakerError(f"Unknown action {a}")
        return {}


_picking = threading.Lock()


def pick_folder() -> str | None:
    """Native folder picker (runs Tk briefly in this worker thread)."""
    if os.environ.get("APC_TEST_FOLDER"):
        return os.environ["APC_TEST_FOLDER"]
    if not _picking.acquire(blocking=False):
        raise SpeakerError("The folder window is already open")
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.update()
        path = filedialog.askdirectory(parent=root, title="Choose a music folder", mustexist=True)
        root.destroy()
        return os.path.normpath(path) if path else None
    except SpeakerError:
        raise
    except Exception:
        return None
    finally:
        _picking.release()


# --------------------------------------------------------------------------------------
# UI server + app window
# --------------------------------------------------------------------------------------

def _resource(name: str) -> str:
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, name)


class ClientTracker:
    def __init__(self):
        self.count = 0
        self.ever = False
        self.last_change = time.time()
        self.lock = threading.Lock()

    def inc(self):
        with self.lock:
            self.count += 1
            self.ever = True
            self.last_change = time.time()

    def dec(self):
        with self.lock:
            self.count -= 1
            self.last_change = time.time()


def make_ui_handler(ctl: Controller, clients: ClientTracker):
    class UIHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _json(self, obj, status=200):
            b = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)

        def _bytes(self, b: bytes, ctype: str, cache=False):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
            self.end_headers()
            self.wfile.write(b)

        def _local_only(self) -> bool:
            # Defend against other web pages poking this local server (DNS rebinding / CSRF).
            host = (self.headers.get("Host") or "").split(":")[0]
            if host not in ("127.0.0.1", "localhost"):
                self.send_error(403)
                return False
            return True

        def do_GET(self):
            if not self._local_only():
                return
            path = urllib.parse.urlparse(self.path).path
            if path in ("/", "/index.html"):
                try:
                    with open(_resource("ui.html"), "rb") as f:
                        self._bytes(f.read(), "text/html; charset=utf-8")
                except OSError:
                    self.send_error(500, "ui.html missing")
            elif path in ("/app.ico", "/favicon.ico"):
                try:
                    with open(_resource("app.ico"), "rb") as f:
                        self._bytes(f.read(), "image/x-icon", cache=True)
                except OSError:
                    self.send_error(404)
            elif path == "/api/ping":
                self._json({"app": APP_NAME, "ok": True, "version": APP_VERSION})
            elif path == "/api/state":
                self._json(ctl.state())
            elif path == "/api/library":
                lib = ctl.library
                self._json({"version": lib.version, "tracks": [lib.tracks[i].to_ui() for i in lib.order
                                                               if i in lib.tracks]})
            elif path.startswith("/art/"):
                art = ctl.library.art_bytes(path.split("/")[2])
                if art:
                    self._bytes(art[1], art[0], cache=True)
                else:
                    self.send_error(404)
            elif path.startswith("/sart/"):
                art = ctl.speaker_art(urllib.parse.unquote(path[6:]))
                if art:
                    self._bytes(art[1], art[0], cache=True)
                else:
                    self.send_error(404)
            elif path == "/api/events":
                self._events()
            else:
                self.send_error(404)

        def _events(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            clients.inc()
            last = -1
            last_payload = None
            last_sent = 0.0
            try:
                while True:
                    with ctl.cond:
                        if ctl.version == last:
                            ctl.cond.wait(timeout=1.0)
                        v = ctl.version
                    now = time.time()
                    if v != last:
                        last = v
                        payload = json.dumps(ctl.state())
                        if payload != last_payload:     # only bother the page when something changed
                            self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                            self.wfile.flush()
                            last_payload, last_sent = payload, now
                            continue
                    if now - last_sent > 10:
                        self.wfile.write(b": still here\n\n")
                        self.wfile.flush()
                        last_sent = now
            except (ConnectionError, OSError):
                pass
            finally:
                clients.dec()
                self.close_connection = True

        def do_POST(self):
            if not self._local_only():
                return
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                self.send_error(415)
                return
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                self._json({"ok": False, "error": "bad json"}, 400)
                return
            if urllib.parse.urlparse(self.path).path != "/api/cmd":
                self.send_error(404)
                return
            try:
                res = ctl.command(body if isinstance(body, dict) else {}) or {}
                self._json({"ok": True, **res})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc) or "Something went wrong"})

    return UIHandler


UI_PORT = 47811
MEDIA_PORT = 47812


def _find_browser() -> str | None:
    import shutil
    cands = []
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        root = os.environ.get(env)
        if root:
            cands.append(os.path.join(root, "Microsoft", "Edge", "Application", "msedge.exe"))
    for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        root = os.environ.get(env)
        if root:
            cands.append(os.path.join(root, "Google", "Chrome", "Application", "chrome.exe"))
    for c in cands:
        if os.path.exists(c):
            return c
    for name in ("msedge", "microsoft-edge", "google-chrome", "chromium", "chromium-browser"):
        p = shutil.which(name)
        if p:
            return p
    return None


def open_window(url: str):
    import subprocess
    import webbrowser
    exe = _find_browser()
    if not exe:
        webbrowser.open(url)
        return
    profile = os.path.join(os.environ.get("LOCALAPPDATA") or _config_dir(), "AudioProControl", "window")
    os.makedirs(profile, exist_ok=True)
    args = [exe, f"--app={url}", f"--user-data-dir={profile}", "--window-size=1280,800",
            "--no-first-run", "--no-default-browser-check", "--disable-background-mode",
            "--disable-session-crashed-bubble", "--hide-crash-restore-bubble",
            "--disable-features=Translate,msEdgeSidebarV2,msImplicitSignin"]
    flags = 0x00000008 if sys.platform.startswith("win") else 0  # DETACHED_PROCESS
    try:
        subprocess.Popen(args, creationflags=flags, close_fds=True)
    except OSError:
        webbrowser.open(url)


APP_USER_MODEL_ID = "AudioProControl.App"


class TaskbarIdentity:
    """Gives the Edge app window its own taskbar identity (Windows only).

    Without this, Windows treats the window as Microsoft Edge: it groups with Edge and
    pinning it gives you an Edge icon that launches Edge. Setting the window's
    AppUserModelID + relaunch properties makes it a separate app: own taskbar button,
    our icon, and a pin that starts this app.
    """

    def __init__(self):
        import ctypes
        import uuid
        from ctypes import wintypes
        self.ct, self.wt = ctypes, wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("b", ctypes.c_ubyte * 16)]

        class PROPERTYKEY(ctypes.Structure):
            _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]

        class PROPVARIANT(ctypes.Structure):
            _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort),
                        ("r3", ctypes.c_ushort), ("p", ctypes.c_void_p), ("p2", ctypes.c_void_p)]

        def guid(s):
            g = GUID()
            ctypes.memmove(ctypes.byref(g), uuid.UUID(s).bytes_le, 16)
            return g

        self.PROPVARIANT, self.PROPERTYKEY = PROPVARIANT, PROPERTYKEY
        fmt = guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3")
        self.PK_ID = PROPERTYKEY(fmt, 5)
        self.PK_CMD = PROPERTYKEY(fmt, 2)
        self.PK_ICON = PROPERTYKEY(fmt, 3)
        self.PK_NAME = PROPERTYKEY(fmt, 4)
        self.IID_PS = guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")
        self.shell32 = ctypes.windll.shell32
        self.user32 = ctypes.windll.user32
        self.ole32 = ctypes.windll.ole32
        self.shell32.SHGetPropertyStoreForWindow.argtypes = [wintypes.HWND, ctypes.POINTER(GUID),
                                                            ctypes.POINTER(ctypes.c_void_p)]
        self.shell32.SHGetPropertyStoreForWindow.restype = ctypes.c_long
        self.user32.LoadImageW.restype = wintypes.HANDLE
        self.user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                           ctypes.c_int, ctypes.c_int, wintypes.UINT]
        self.user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

        self.icon = _resource("app.ico")
        script = os.path.abspath(sys.argv[0])
        exe = sys.executable
        if getattr(sys, "frozen", False):
            self.command = f'"{exe}"'
        else:
            pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
            self.command = f'"{pyw if os.path.exists(pyw) else exe}" "{script}"'
        self.big = self.user32.LoadImageW(None, self.icon, 1, 256, 256, 0x10) if os.path.exists(self.icon) else None
        self.small = self.user32.LoadImageW(None, self.icon, 1, 32, 32, 0x10) if os.path.exists(self.icon) else None
        self.last_seen = 0.0      # when the app window was last found on screen

    def _store(self, hwnd):
        ct = self.ct
        ptr = ct.c_void_p()
        hr = self.shell32.SHGetPropertyStoreForWindow(hwnd, ct.byref(self.IID_PS), ct.byref(ptr))
        if hr < 0 or not ptr.value:
            return None
        vtbl = ct.cast(ct.cast(ptr, ct.POINTER(ct.c_void_p))[0], ct.POINTER(ct.c_void_p))
        proto_kv = ct.WINFUNCTYPE(ct.c_long, ct.c_void_p, ct.POINTER(self.PROPERTYKEY), ct.POINTER(self.PROPVARIANT))
        return (ptr,
                proto_kv(vtbl[5]),                                   # GetValue
                proto_kv(vtbl[6]),                                   # SetValue
                ct.WINFUNCTYPE(ct.c_long, ct.c_void_p)(vtbl[7]),     # Commit
                ct.WINFUNCTYPE(ct.c_ulong, ct.c_void_p)(vtbl[2]))    # Release

    def _get_id(self, store) -> str:
        ptr, get, _set, _commit, _rel = store
        pv = self.PROPVARIANT()
        try:
            get(ptr, self.ct.byref(self.PK_ID), self.ct.byref(pv))
        except OSError:
            return ""
        val = self.ct.wstring_at(pv.p) if pv.vt == 31 and pv.p else ""
        self.ole32.PropVariantClear(self.ct.byref(pv))
        return val

    def _set_str(self, store, key, text):
        ptr, _get, setv, _commit, _rel = store
        buf = self.ct.create_unicode_buffer(text)
        pv = self.PROPVARIANT()
        pv.vt = 31  # VT_LPWSTR
        pv.p = self.ct.cast(buf, self.ct.c_void_p)
        setv(ptr, self.ct.byref(key), self.ct.byref(pv))

    def apply(self, hwnd) -> bool:
        store = self._store(hwnd)
        if not store:
            return False
        try:
            if self._get_id(store) == APP_USER_MODEL_ID:
                return True
            # relaunch properties first, then the ID (as Windows expects)
            self._set_str(store, self.PK_CMD, self.command)
            self._set_str(store, self.PK_NAME, APP_NAME)
            if os.path.exists(self.icon):
                self._set_str(store, self.PK_ICON, f"{self.icon},0")
            self._set_str(store, self.PK_ID, APP_USER_MODEL_ID)
            store[3](store[0])
        except OSError:
            return False
        finally:
            store[4](store[0])
        if self.big:
            self.user32.SendMessageW(hwnd, 0x80, 1, self.big)    # WM_SETICON, ICON_BIG
        if self.small:
            self.user32.SendMessageW(hwnd, 0x80, 0, self.small)  # ICON_SMALL
        return True

    def our_windows(self) -> list:
        ct, wt = self.ct, self.wt
        found = []

        @ct.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        def cb(hwnd, _lp):
            if not self.user32.IsWindowVisible(hwnd):
                return True
            cls = ct.create_unicode_buffer(64)
            self.user32.GetClassNameW(hwnd, cls, 64)
            if not cls.value.startswith("Chrome_WidgetWin"):
                return True
            title = ct.create_unicode_buffer(256)
            self.user32.GetWindowTextW(hwnd, title, 256)
            if title.value == APP_NAME or title.value.startswith(APP_NAME + " "):
                found.append(hwnd)
            return True

        self.user32.EnumWindows(cb, 0)
        return found

    def run(self, stop: threading.Event):
        try:
            self.ole32.CoInitialize(None)
        except OSError:
            pass
        start = time.time()
        while not stop.is_set():
            windows = self.our_windows()
            if windows:
                self.last_seen = time.time()
            for hwnd in windows:
                try:
                    self.apply(hwnd)  # cheap no-op when already ours; re-applies if Edge resets it
                except Exception:
                    pass
            # watch closely while the window is appearing, then relax
            stop.wait(0.1 if time.time() - start < 20 else 2.0)


def start_taskbar_identity(stop: threading.Event):
    if not sys.platform.startswith("win"):
        return None
    try:
        ti = TaskbarIdentity()
    except Exception:
        return None
    threading.Thread(target=ti.run, args=(stop,), daemon=True).start()
    return ti


def set_process_identity():
    """Our own (rare) windows, like the folder picker, use the same identity."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except Exception:
            pass


def _running_version(port: int) -> str | None:
    """Version of a copy of this app that is already running, or None."""
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                f"http://127.0.0.1:{port}/api/ping", timeout=1.5) as r:
            d = json.loads(r.read())
            return str(d.get("version") or "old") if d.get("app") == APP_NAME else None
    except Exception:
        return None


def _retire_old_copy(port: int):
    """An older version is still running (the app was updated while open): ask it to step aside."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/cmd", data=b'{"action": "quit"}',
                                     headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=2).read()
    except Exception:
        pass
    for _ in range(20):
        time.sleep(0.25)
        if _running_version(port) is None:
            return


def main():
    no_window = "--no-window" in sys.argv
    set_process_identity()
    ui_port = int(os.environ.get("APC_UI_PORT", UI_PORT))
    running = _running_version(ui_port)
    if running == APP_VERSION:
        if not no_window:
            open_window(f"http://127.0.0.1:{ui_port}/")
        return
    if running is not None:
        _retire_old_copy(ui_port)

    ctl = Controller()
    clients = ClientTracker()

    try:
        media = _QuietServer(("0.0.0.0", int(os.environ.get("APC_MEDIA_PORT", MEDIA_PORT))), make_media_handler(ctl))
    except OSError:
        media = _QuietServer(("0.0.0.0", 0), make_media_handler(ctl))
    ctl.media_port = media.server_address[1]
    threading.Thread(target=media.serve_forever, daemon=True).start()

    try:
        ui = _QuietServer(("127.0.0.1", ui_port), make_ui_handler(ctl, clients))
    except OSError:
        ui = _QuietServer(("127.0.0.1", 0), make_ui_handler(ctl, clients))
    threading.Thread(target=ui.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{ui.server_address[1]}/"
    print(f"{APP_NAME} {APP_VERSION}: UI {url}  media port {ctl.media_port}", flush=True)

    ctl.start()
    taskbar = None
    if not no_window:
        taskbar = start_taskbar_identity(ctl._stop)
        open_window(url)

    # Quit once the app window has been closed: nothing connected for a while, and (where we can
    # check) no window on screen. A minimised window that Windows has put to sleep still counts
    # as open, so music keeps playing.
    while True:
        time.sleep(2)
        if no_window:
            continue
        idle = time.time() - clients.last_change
        window_open = taskbar is not None and time.time() - taskbar.last_seen < 12
        if clients.count <= 0 and not window_open and (
                (clients.ever and idle > 15) or (not clients.ever and idle > 120)):
            break
    os._exit(0)


if __name__ == "__main__":
    main()
