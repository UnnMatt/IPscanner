import os
import re
import csv
import json
import sys
import ipaddress
import itertools
import shutil
import threading
import textwrap
import urllib.request
import urllib.error
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional

API_URL = "http://ip-api.com/batch"
FIELDS = (
    "status,message,query,country,countryCode,regionName,city,zip,lat,lon,timezone,"
    "isp,org,as,asname,hosting,proxy,mobile"
)

# ==================================================
# Theme And Display Constants
# ==================================================

# ANSI colors
RESET = "[0m"
BOLD = "[1m"
DIM = "[2m"

RED = "[31m"
GREEN = "[32m"
YELLOW = "[33m"
BLUE = "[34m"
CYAN = "[36m"
MAGENTA = "[35m"
GRAY = "[90m"

PRIMARY = BLUE
ACCENT = CYAN
SUCCESS = GREEN
WARNING = YELLOW
DANGER = RED
MUTED = GRAY

ANSI_RE = re.compile(r"\[[0-9;]*m")


# ==================================================
# UI Helpers
# ==================================================


def color(text, c):
    return f"{c}{text}{RESET}"


def normalize_text(value):
    if not value:
        return ""
    text = str(value).lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[_/|,;(){}\[\]-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def enable_windows_terminal():
    if os.name != "nt":
        return

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        try:
            os.system("")
        except Exception:
            pass

    for stream_name in ("stdout", "stderr", "stdin"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def terminal_width():
    return min(shutil.get_terminal_size((120, 20)).columns, 132)


def strip_ansi(text):
    return ANSI_RE.sub("", text)


def visible_len(text):
    return len(strip_ansi(text))


def pad_text(text, width, align="left"):
    padding = max(0, width - visible_len(text))
    if align == "right":
        return (" " * padding) + text
    if align == "center":
        left = padding // 2
        right = padding - left
        return (" " * left) + text + (" " * right)
    return text + (" " * padding)


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def show_banner():
    clear_screen()

    banner_lines = [
        (RED, " ██████╗ ██████╗ ██████╗ ██╗████████╗ █████╗ ██╗         ██╗   ██╗███████╗ █████╗ ████████╗"),
        (YELLOW, "██╔═══██╗██╔══██╗██╔══██╗██║╚══██╔══╝██╔══██╗██║         ██║   ██║██╔════╝██╔══██╗╚══██╔══╝"),
        (GREEN, "██║   ██║██████╔╝██████╔╝██║   ██║   ███████║██║         ██║   ██║███████╗███████║   ██║   "),
        (CYAN, "██║   ██║██╔══██╗██╔══██╗██║   ██║   ██╔══██║██║         ╚██╗ ██╔╝╚════██║██╔══██║   ██║   "),
        (BLUE, "╚██████╔╝██║  ██║██████╔╝██║   ██║   ██║  ██║███████╗     ╚████╔╝ ███████║██║  ██║   ██║   "),
        (MAGENTA, " ╚═════╝ ╚═╝  ╚═╝╚═════╝ ╚═╝   ╚═╝   ╚═╝  ╚═╝╚══════╝      ╚═══╝  ╚══════╝╚═╝  ╚═╝   ╚═╝   "),
    ]

    print()
    for tone, line in banner_lines:
        print(color(line, BOLD + tone))
    print(color("  IP lookup, location info, and quick risk hints", DIM + MUTED))
    print(color("  Terminal tool with CSV and JSON export", DIM + MUTED))


def header(text, subtitle=None):
    width = terminal_width()
    label = f" {text} "
    fill = max(0, width - len(text) - 2)
    print()
    print(color(label + ("=" * fill), BOLD + PRIMARY))
    if subtitle:
        print(color(subtitle, DIM + MUTED))


def print_step(step, total, title, detail=None):
    print()
    print(color(f"[STEP {step}/{total}] {title}", BOLD + ACCENT))
    print(color("-" * terminal_width(), PRIMARY))
    if detail:
        print(color(detail, DIM + MUTED))


def print_box(title, lines, tone=ACCENT, width=None):
    full_width = min(width or terminal_width(), 92)
    full_width = max(full_width, len(title) + 8)
    top_fill = max(0, full_width - len(title) - 5)

    print(color(f"+- {title} " + ("-" * top_fill) + "+", tone))
    for line in lines:
        content = line if line is not None else ""
        padding = max(0, full_width - visible_len(content) - 4)
        print(f"{color('|', tone)} {content}{' ' * padding} {color('|', tone)}")
    print(color("+" + ("-" * (full_width - 2)) + "+", tone))


def kv_lines(pairs):
    label_width = max(len(label) for label, _, *_ in pairs) if pairs else 0
    lines = []
    for pair in pairs:
        label = pair[0]
        value = str(pair[1])
        tone = pair[2] if len(pair) > 2 else None
        rendered = color(value, tone) if tone else value
        lines.append(f"{color(label.ljust(label_width), DIM + MUTED)} : {rendered}")
    return lines


def wrap_label_value(label, value, width, value_tone=None):
    label_text = color(label.ljust(10), DIM + MUTED)
    prefix = f"{label_text} : "
    available = max(18, width - visible_len(prefix) - 4)
    wrapped = textwrap.wrap(str(value), width=available) or [""]
    lines = []

    for index, part in enumerate(wrapped):
        if index == 0:
            rendered = color(part, value_tone) if value_tone else part
            lines.append(prefix + rendered)
        else:
            lines.append((" " * visible_len(prefix)) + part)

    return lines


def build_table_border(left, middle, right, widths):
    return left + middle.join("-" * (width + 2) for width in widths) + right


def format_table_row(cells, widths, aligns):
    parts = []
    for cell, width, align in zip(cells, widths, aligns):
        parts.append(" " + pad_text(cell, width, align) + " ")
    return "|" + "|".join(parts) + "|"


def fit_column_widths(columns, max_total=None):
    widths = [column["width"] for column in columns]
    minimums = [column.get("min_width", column["width"]) for column in columns]
    max_total = max_total or terminal_width()

    def current_total():
        return sum(widths) + (3 * len(widths)) + 1

    while current_total() > max_total:
        changed = False
        for index in range(len(widths)):
            if widths[index] > minimums[index]:
                widths[index] -= 1
                changed = True
                if current_total() <= max_total:
                    break
        if not changed:
            break

    return widths


def render_table(columns, rows, tone=PRIMARY):
    widths = [column["width"] for column in columns]
    aligns = [column.get("align", "left") for column in columns]
    headers = [column["title"] for column in columns]

    print(color(build_table_border("+", "+", "+", widths), tone))
    print(color(format_table_row(headers, widths, ["center"] * len(columns)), BOLD + tone))
    print(color(build_table_border("+", "+", "+", widths), tone))
    for row in rows:
        print(format_table_row(row, widths, aligns))
    print(color(build_table_border("+", "+", "+", widths), tone))


def prompt(text):
    return input(color(text, BOLD + ACCENT)).strip()


def ask_yes_no(question, default="n"):
    suffix = "Y/n" if default.lower() == "y" else "y/N"
    while True:
        choice = prompt(f"{question} [{suffix}]: ").lower()
        if not choice:
            return default.lower() == "y"
        if choice in {"y", "yes"}:
            return True
        if choice in {"n", "no"}:
            return False
        print(color("Please answer with y or n.", WARNING))


def run_with_spinner(message, func, *args, **kwargs):
    state = {"result": None, "error": None}
    finished = threading.Event()

    def worker():
        try:
            state["result"] = func(*args, **kwargs)
        except Exception as exc:
            state["error"] = exc
        finally:
            finished.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    frames = itertools.cycle(["|", "/", "-", "\\"])
    label = f"{message} "

    while not finished.wait(0.1):
        frame = next(frames)
        sys.stdout.write("\r" + color(label + frame, BOLD + ACCENT))
        sys.stdout.flush()

    clear_width = len(label) + 1
    sys.stdout.write("\r" + (" " * clear_width) + "\r")
    sys.stdout.flush()
    thread.join()

    if state["error"] is not None:
        raise state["error"]

    print(color(f"{message} done.", DIM + MUTED))
    return state["result"]


# ==================================================
# Internal Data Models And Workflow Hooks
# ==================================================


@dataclass
class InputParseResult:
    valid_ips: list
    invalid_ips: list
    counts: Counter


@dataclass
class EnrichmentOption:
    key: str
    label: str
    description: str


@dataclass
class ScanProfile:
    key: str
    name: str
    description: str
    enabled: set = field(default_factory=set)
    prompt_for_details: bool = False

    def runtime_copy(self):
        return ScanProfile(
            key=self.key,
            name=self.name,
            description=self.description,
            enabled=set(self.enabled),
            prompt_for_details=self.prompt_for_details,
        )

    def is_enabled(self, enrichment_key):
        return enrichment_key in self.enabled


@dataclass(frozen=True)
class WorkflowPreset:
    key: str
    name: str
    description: str
    default_profile_key: str
    step_total: int = 5


@dataclass
class IPResultRecord:
    query: str = ""
    count: int = 1
    status: str = ""
    message: str = ""
    country: str = ""
    countryCode: str = ""
    regionName: str = ""
    city: str = ""
    zip: str = ""
    lat: object = ""
    lon: object = ""
    timezone: str = ""
    isp: str = ""
    org: str = ""
    asn: str = ""
    asname: str = ""
    hosting: Optional[bool] = None
    proxy: Optional[bool] = None
    mobile: Optional[bool] = None
    provider_text: str = ""
    suspicion_flag: str = "N/A"
    suspicion_score: Optional[int] = None
    reasons: list = field(default_factory=list)
    ip_type: str = ""
    raw: dict = field(default_factory=dict)

    def get(self, key, default=None):
        aliases = {
            "as": self.asn,
            "type": self.ip_type,
            "suspicion_flag": self.suspicion_flag,
            "suspicion_score": self.suspicion_score,
            "reasons": self.reasons,
            "count": self.count,
        }
        if key in aliases:
            value = aliases[key]
            return default if value is None else value
        if key in self.__dict__:
            value = getattr(self, key)
            return default if value is None else value
        if key in self.raw:
            value = self.raw[key]
            return default if value is None else value
        return default

    def to_export_dict(self):
        return {
            "status": self.status,
            "message": self.message,
            "query": self.query,
            "country": self.country,
            "countryCode": self.countryCode,
            "regionName": self.regionName,
            "city": self.city,
            "zip": self.zip,
            "lat": self.lat,
            "lon": self.lon,
            "timezone": self.timezone,
            "isp": self.isp,
            "org": self.org,
            "as": self.asn,
            "asname": self.asname,
            "hosting": self.hosting,
            "proxy": self.proxy,
            "mobile": self.mobile,
            "count": self.count,
            "type": self.ip_type,
            "suspicion_flag": self.suspicion_flag,
            "suspicion_score": self.suspicion_score,
            "reasons": list(self.reasons),
        }


# ==================================================
# Scoring Keywords And Built-In Profiles
# ==================================================


# Strong indicators
HARD_KEYWORDS = {
    "vpn": 4,
    "proxy": 4,
    "tor": 5,
    "exit node": 5,
    "anonymous": 3,
    "anonymizer": 3,
    "datacenter": 3,
    "data center": 3,
    "colo": 2,
    "colocation": 2,
    "hosting": 2,
    "hosted": 2,
    "server": 2,
    "vps": 3,
    "dedicated": 2,
    "cloud": 1,

    "amazon": 2,
    "aws": 2,
    "amazon web services": 3,
    "google cloud": 3,
    "google llc": 1,
    "gcp": 2,
    "microsoft azure": 3,
    "azure": 2,
    "oracle cloud": 3,
    "oracle corporation": 1,
    "oci": 2,
    "ibm cloud": 3,
    "alibaba cloud": 3,
    "tencent cloud": 3,
    "huawei cloud": 3,
    "akamai connected cloud": 2,
    "linode": 3,

    "digitalocean": 3,
    "ovh": 3,
    "ovhcloud": 3,
    "hetzner": 3,
    "vultr": 3,
    "choopa": 2,
    "linode llc": 3,
    "scaleway": 3,
    "online sas": 2,
    "leaseweb": 3,
    "contabo": 3,
    "worldstream": 3,
    "psychz": 3,
    "m247": 3,
    "i3d": 2,
    "path network": 2,
    "zenlayer": 3,
    "servers com": 2,
    "servers.com": 2,
    "hivelocity": 3,
    "netcup": 3,
    "interserver": 3,
    "it7 networks": 2,
    "frantech": 3,
    "buyvm": 3,
    "ramnode": 3,
    "colo cross": 2,
    "quadranet": 3,
    "reliablesite": 3,
    "kamatera": 3,
    "hostwinds": 3,
    "knownhost": 3,
    "hostinger": 2,
    "namecheap": 2,
    "dreamhost": 2,
    "bluehost": 2,
    "siteground": 2,
    "ionos": 2,
    "1and1": 2,
    "1 and 1": 2,
    "hetzner online": 3,
    "ovh hosting": 3,
    "lightnode": 3,

    "cloudflare": 2,
    "fastly": 2,
    "akamai": 2,
    "edgio": 2,
    "stackpath": 2,
    "bunny": 2,
    "cdn77": 2,
    "ddos guard": 3,
    "ddos guard s.r.o": 3,
    "ddos-guard": 3,
    "stormwall": 3,

    "mullvad": 4,
    "nordvpn": 4,
    "surfshark": 4,
    "expressvpn": 4,
    "proton": 3,
    "protonvpn": 4,
    "purevpn": 4,
    "pia": 3,
    "private internet access": 4,
    "cyberghost": 4,
    "windscribe": 4,
    "ivpn": 4,
    "hidemyass": 4,
    "hma vpn": 4,
    "perfect privacy": 4,
    "airvpn": 4,

    "datacamp": 3,
    "frantech solutions": 3,
    "sharktech": 3,
    "xtom": 3,
    "pq hosting": 3,
    "bluevps": 3,
    "aeza": 4,
    "timeweb": 2,
    "first server": 2,
    "selectel": 2,
    "reg ru": 2,
    "reg.ru": 2,
}

# Softer indicators
SOFT_KEYWORDS = {
    "virtual": 1,
    "compute": 1,
    "bare metal": 2,
    "instance": 1,
    "hypervisor": 2,
    "container": 1,
    "edge": 1,
    "cdn": 1,
    "reverse proxy": 2,
    "transit": 1,
    "backbone": 1,
    "content delivery": 1,
    "anti ddos": 2,
    "anti-ddos": 2,
    "mitigation": 2,
    "scrubbing": 2,
}

# Hints that it may be normal consumer/mobile internet
RESIDENTIAL_HINTS = {
    "telia": -2,
    "tele2": -2,
    "telenor": -2,
    "tre": -2,
    "3 sverige": -2,
    "comhem": -2,
    "bahnhof": -2,
    "bredband2": -2,
    "ownit": -2,
    "sappa": -2,
    "allente": -2,
    "vodafone": -2,
    "orange": -2,
    "telefonica": -2,
    "o2": -2,
    "ee": -2,
    "bt": -1,
    "virgin media": -2,
    "deutsche telekom": -2,
    "telekom": -1,
    "att": -2,
    "at&t": -2,
    "verizon": -2,
    "comcast": -2,
    "xfinity": -2,
    "charter": -2,
    "spectrum": -2,
    "cox": -2,
    "frontier": -2,
    "centurylink": -2,
    "lumen": -1,
    "rogers": -2,
    "bell canada": -2,
    "shaw": -2,
    "telus": -2,
    "residential": -3,
    "broadband": -2,
    "fiber": -1,
    "fibre": -1,
    "mobile": -2,
    "cellular": -2,
    "wireless": -1,
}

OPTIONAL_ENRICHMENTS = [
    EnrichmentOption(
        key="type_summary",
        label="Type summary",
        description="Classification rollup by unique IPs and total hits.",
    ),
    EnrichmentOption(
        key="duplicates",
        label="Duplicate summary",
        description="Repeated IP counts so reuse stands out quickly.",
    ),
    EnrichmentOption(
        key="country_grouping",
        label="Country grouping",
        description="Country buckets for quick location review.",
    ),
    EnrichmentOption(
        key="asn_summary",
        label="ASN summary",
        description="Top networks by unique IP count and total hits.",
    ),
    EnrichmentOption(
        key="subnet_summary",
        label="Subnet summary",
        description="Top /24 ranges by unique IP count and total hits.",
    ),
    EnrichmentOption(
        key="detailed_results",
        label="Detailed results",
        description="Expanded per-IP geolocation and provider view.",
    ),
]

SCAN_PROFILES = {
    "quick": ScanProfile(
        key="quick",
        name="Quick scan",
        description="Fastest view with the core results plus the most useful rollups.",
        enabled={"type_summary", "duplicates"},
        prompt_for_details=False,
    ),
    "standard": ScanProfile(
        key="standard",
        name="Standard scan",
        description="Recommended default with the best balance of speed and enrichment.",
        enabled={"type_summary", "duplicates", "country_grouping", "asn_summary", "subnet_summary"},
        prompt_for_details=True,
    ),
    "deep": ScanProfile(
        key="deep",
        name="Deep scan",
        description="Full review mode with every summary and detailed per-IP output enabled.",
        enabled={item.key for item in OPTIONAL_ENRICHMENTS},
        prompt_for_details=False,
    ),
}

DEFAULT_WORKFLOW_PRESET_KEY = "classic"
WORKFLOW_PRESETS = {
    DEFAULT_WORKFLOW_PRESET_KEY: WorkflowPreset(
        key=DEFAULT_WORKFLOW_PRESET_KEY,
        name="Classic terminal flow",
        description="The current familiar prompt -> lookup -> review -> export workflow.",
        default_profile_key="standard",
        step_total=5,
    ),
}


def get_scan_profile(profile_key):
    return SCAN_PROFILES[profile_key].runtime_copy()


def get_workflow_preset(preset_key=DEFAULT_WORKFLOW_PRESET_KEY):
    return WORKFLOW_PRESETS[preset_key]


def suspicion_color(label):
    if label == "VERY HIGH":
        return RED
    if label == "HIGH":
        return YELLOW
    if label == "MEDIUM":
        return MAGENTA
    if label == "LOW":
        return CYAN
    return GREEN


# ==================================================
# Input Parsing
# ==================================================


def is_valid_ipv4(ip):
    pattern = re.compile(
        r"^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\."
        r"(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\."
        r"(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\."
        r"(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)$"
    )
    return bool(pattern.match(ip))


def parse_input_text(text):
    raw_items = re.split(r"[\s,;]+", text.strip())
    raw_items = [item.strip() for item in raw_items if item.strip()]

    valid = []
    invalid = []

    for item in raw_items:
        if is_valid_ipv4(item):
            valid.append(item)
        else:
            invalid.append(item)

    counts = Counter(valid)
    unique_valid = list(dict.fromkeys(valid))
    invalid_unique = list(dict.fromkeys(invalid))

    return InputParseResult(
        valid_ips=unique_valid,
        invalid_ips=invalid_unique,
        counts=counts,
    )


def extract_ips(text):
    parsed = parse_input_text(text)
    return parsed.valid_ips, parsed.invalid_ips, parsed.counts


def chunk_list(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


# ==================================================
# Lookup Logic
# ==================================================


def lookup_batch(ips):
    payload = [{"query": ip, "fields": FIELDS} for ip in ips]
    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def lookup_ips(ips):
    all_results = []
    for batch in chunk_list(ips, 100):
        all_results.extend(lookup_batch(batch))
    return all_results


# ==================================================
# Scoring, Classification, And Record Hydration
# ==================================================


def collect_provider_text(item):
    parts = [
        item.get("isp", ""),
        item.get("org", ""),
        item.get("as", ""),
        item.get("asname", ""),
    ]
    return normalize_text(" ".join(str(p) for p in parts if p))


def keyword_hits(text, mapping):
    hits = []
    score = 0

    for keyword, value in mapping.items():
        if keyword in text:
            hits.append((keyword, value))
            score += value

    return score, hits


def compute_suspicion_score(item):
    score = 0
    reasons = []

    provider_text = collect_provider_text(item)

    if item.get("hosting") is True:
        score += 5
        reasons.append("hosting=true")

    if item.get("proxy") is True:
        score += 5
        reasons.append("proxy=true")

    if item.get("mobile") is True:
        score -= 2
        reasons.append("mobile=true")

    hard_score, hard_hits = keyword_hits(provider_text, HARD_KEYWORDS)
    soft_score, soft_hits = keyword_hits(provider_text, SOFT_KEYWORDS)
    res_score, res_hits = keyword_hits(provider_text, RESIDENTIAL_HINTS)

    score += hard_score + soft_score + res_score

    for keyword, value in hard_hits:
        reasons.append(f"{keyword}({value:+})")

    for keyword, value in soft_hits:
        if value != 0:
            reasons.append(f"{keyword}({value:+})")

    for keyword, value in res_hits:
        if value != 0:
            reasons.append(f"{keyword}({value:+})")

    as_field = normalize_text(item.get("as", ""))
    asname_field = normalize_text(item.get("asname", ""))

    if as_field.startswith("as"):
        score += 1
        reasons.append("asn_present(+1)")

    isp = normalize_text(item.get("isp", ""))
    org = normalize_text(item.get("org", ""))
    if isp and org and isp == org and any(k in isp for k in HARD_KEYWORDS):
        score += 2
        reasons.append("isp_org_same_vendor(+2)")

    hostingish_words = [
        "hosting", "cloud", "server", "datacenter", "data center",
        "vps", "colo", "colocation", "proxy", "vpn"
    ]
    if any(word in asname_field for word in hostingish_words):
        score += 2
        reasons.append("asname_hosting_like(+2)")

    if score >= 9:
        label = "VERY HIGH"
    elif score >= 6:
        label = "HIGH"
    elif score >= 3:
        label = "MEDIUM"
    elif score >= 1:
        label = "LOW"
    else:
        label = "NONE"

    reasons = list(dict.fromkeys(reasons))
    return label, reasons, score


def classify_ip_type(item, flag, score):
    if item.get("mobile") is True and item.get("hosting") is not True and item.get("proxy") is not True:
        return "Likely Mobile"

    if score <= 0 and item.get("hosting") is not True and item.get("proxy") is not True:
        return "Likely Residential"

    if flag in ("VERY HIGH", "HIGH"):
        return "Likely Datacenter/VPN"

    if flag == "MEDIUM":
        return "Manual Review"

    return "Low Suspicion"


def suspicion_score(item):
    if isinstance(item, IPResultRecord) and item.suspicion_score is not None:
        return item.suspicion_flag, list(item.reasons), item.suspicion_score
    return compute_suspicion_score(item)


def likely_type(item):
    if isinstance(item, IPResultRecord) and item.ip_type:
        return item.ip_type
    flag, _, score = suspicion_score(item)
    return classify_ip_type(item, flag, score)


def build_result_record(item, counts):
    query = item.get("query", "")
    record = IPResultRecord(
        query=query,
        count=counts.get(query, 1),
        status=item.get("status", ""),
        message=item.get("message", ""),
        country=item.get("country", ""),
        countryCode=item.get("countryCode", ""),
        regionName=item.get("regionName", ""),
        city=item.get("city", ""),
        zip=item.get("zip", ""),
        lat=item.get("lat", ""),
        lon=item.get("lon", ""),
        timezone=item.get("timezone", ""),
        isp=item.get("isp", ""),
        org=item.get("org", ""),
        asn=item.get("as", ""),
        asname=item.get("asname", ""),
        hosting=item.get("hosting"),
        proxy=item.get("proxy"),
        mobile=item.get("mobile"),
        raw=dict(item),
    )
    record.provider_text = collect_provider_text(record)

    if record.status == "success":
        flag, reasons, score = compute_suspicion_score(record)
        record.suspicion_flag = flag
        record.reasons = reasons
        record.suspicion_score = score
        record.ip_type = classify_ip_type(record, flag, score)
    else:
        record.suspicion_flag = "N/A"
        record.reasons = []
        record.suspicion_score = None
        record.ip_type = "Lookup Failed"

    return record


def hydrate_result_records(raw_results, counts):
    return [build_result_record(item, counts) for item in raw_results]


# ==================================================
# Formatting Helpers
# ==================================================


def safe(value, max_len=None):
    text = str(value) if value is not None else "N/A"
    if max_len and len(text) > max_len:
        return text[:max_len - 3] + "..."
    return text


def format_location(item):
    country = item.get("country", "N/A")
    city = item.get("city", "N/A")
    if country and city and country != "N/A" and city != "N/A":
        return f"{country} / {city}"
    return country or city or "N/A"


def format_provider(item):
    isp = item.get("isp", "N/A")
    org = item.get("org", "N/A")
    if isp and org and isp not in {"", "N/A"} and org not in {"", "N/A"} and isp != org:
        return f"{isp} / {org}"
    return isp if isp not in {"", None} else (org or "N/A")


def format_signals(item):
    labels = []
    if item.get("hosting"):
        labels.append("Hosting")
    if item.get("proxy"):
        labels.append("Proxy")
    if item.get("mobile"):
        labels.append("Mobile")

    if not labels:
        return "Clean"
    return "+".join(labels)


def signal_tone(item):
    if item.get("proxy"):
        return DANGER
    if item.get("hosting"):
        return WARNING
    if item.get("mobile"):
        return BLUE
    return SUCCESS


def format_score(score):
    return color(str(score), BOLD + suspicion_color(
        "VERY HIGH" if score >= 9 else
        "HIGH" if score >= 6 else
        "MEDIUM" if score >= 3 else
        "LOW" if score >= 1 else
        "NONE"
    ))


def type_tone(ip_type):
    mapping = {
        "Likely Datacenter/VPN": DANGER,
        "Manual Review": MAGENTA,
        "Low Suspicion": ACCENT,
        "Likely Residential": SUCCESS,
        "Likely Mobile": BLUE,
        "Lookup Failed": DANGER,
    }
    return mapping.get(ip_type, ACCENT)


# ==================================================
# Rendering
# ==================================================


def print_input_summary(valid_ips, invalid_ips, counts):
    header("INPUT SUMMARY", "Clean overview before the lookup starts.")
    print_box(
        "Parsed Input",
        kv_lines([
            ("Unique valid IPs", len(valid_ips), SUCCESS),
            ("Total valid hits", sum(counts.values()), ACCENT),
            ("Invalid entries", len(invalid_ips), WARNING if invalid_ips else SUCCESS),
        ]),
        tone=ACCENT,
    )


def print_result_overview(results, counts):
    successful = [item for item in results if item.get("status") == "success"]
    failed = [item for item in results if item.get("status") != "success"]
    high_risk = 0
    hosting = 0
    proxy = 0
    countries = set()

    for item in successful:
        flag, _, _ = suspicion_score(item)
        if flag in ("VERY HIGH", "HIGH"):
            high_risk += 1
        if item.get("hosting"):
            hosting += 1
        if item.get("proxy"):
            proxy += 1
        if item.get("country"):
            countries.add(item.get("country"))

    header("RESULT OVERVIEW", "Quick summary of the lookup output.")
    print_box(
        "Lookup Snapshot",
        kv_lines([
            ("Successful lookups", len(successful), SUCCESS),
            ("Lookup failures", len(failed), WARNING if failed else SUCCESS),
            ("High-risk results", high_risk, DANGER if high_risk else SUCCESS),
            ("Hosting flagged", hosting, WARNING if hosting else SUCCESS),
            ("Proxy flagged", proxy, DANGER if proxy else SUCCESS),
            ("Countries seen", len(countries), ACCENT),
            ("Total IP hits", sum(counts.values()), ACCENT),
        ]),
        tone=ACCENT,
    )


def print_results_table(results, counts):
    header(
        "LOOKUP RESULTS",
        "Sorted by suspicion first. Signals combine hosting, proxy, and mobile indicators.",
    )

    columns = [
        {"title": "IP", "width": 15, "min_width": 15},
        {"title": "Hits", "width": 4, "min_width": 4, "align": "right"},
        {"title": "Location", "width": 20, "min_width": 14},
        {"title": "Provider", "width": 24, "min_width": 16},
        {"title": "Signals", "width": 12, "min_width": 9},
        {"title": "Score", "width": 5, "min_width": 5, "align": "right"},
        {"title": "Risk", "width": 11, "min_width": 8},
        {"title": "Type", "width": 18, "min_width": 14},
    ]
    fitted = fit_column_widths(columns)
    for column, width in zip(columns, fitted):
        column["width"] = width

    rows = []

    for item in results:
        ip = item.get("query", "N/A")
        hits = str(counts.get(ip, 1))

        if item.get("status") != "success":
            rows.append([
                color(safe(ip, columns[0]["width"]), BOLD + DANGER),
                hits,
                color("Lookup failed", DANGER),
                safe(item.get("message", "Unknown error"), columns[3]["width"]),
                color("-", DIM + MUTED),
                color("-", DIM + MUTED),
                color("FAILED", BOLD + DANGER),
                color("Lookup Failed", DANGER),
            ])
            continue

        flag, _, score = suspicion_score(item)
        ip_type = likely_type(item)
        ip_tone = BOLD + suspicion_color(flag) if flag in ("VERY HIGH", "HIGH") else BOLD
        signal_text = safe(format_signals(item), columns[4]["width"])
        risk_text = safe(flag, columns[6]["width"])
        type_text = safe(ip_type, columns[7]["width"])

        rows.append([
            color(safe(ip, columns[0]["width"]), ip_tone),
            hits,
            safe(format_location(item), columns[2]["width"]),
            safe(format_provider(item), columns[3]["width"]),
            color(signal_text, signal_tone(item)),
            format_score(score),
            color(risk_text, BOLD + suspicion_color(flag)),
            color(type_text, type_tone(ip_type)),
        ])

    render_table(columns, rows, tone=PRIMARY)


def print_detailed_results(results, counts):
    header("DETAILED RESULTS", "Expanded view for full geolocation and provider context.")
    width = min(terminal_width(), 104)

    for item in results:
        ip = item.get("query", "N/A")
        seen = counts.get(ip, 1)

        if item.get("status") != "success":
            print_box(
                f"{ip}  |  seen {seen}x",
                wrap_label_value("Status", f"Lookup failed: {item.get('message', 'Unknown error')}", width, DANGER),
                tone=DANGER,
                width=width,
            )
            continue

        flag, reasons, score = suspicion_score(item)
        lines = []
        lines.extend(wrap_label_value("Location", f"{item.get('country', 'N/A')} / {item.get('regionName', 'N/A')} / {item.get('city', 'N/A')}", width))
        lines.extend(wrap_label_value("ZIP", item.get("zip", "N/A"), width))
        lines.extend(wrap_label_value("Timezone", item.get("timezone", "N/A"), width))
        lines.extend(wrap_label_value("Coords", f"{item.get('lat', 'N/A')}, {item.get('lon', 'N/A')}", width))
        lines.extend(wrap_label_value("ISP", item.get("isp", "N/A"), width))
        lines.extend(wrap_label_value("Org", item.get("org", "N/A"), width))
        lines.extend(wrap_label_value("ASN", item.get("as", "N/A"), width))
        lines.extend(wrap_label_value("AS Name", item.get("asname", "N/A"), width))
        lines.extend(wrap_label_value(
            "Signals",
            f"Hosting {('Yes' if item.get('hosting') else 'No')} | "
            f"Proxy {('Yes' if item.get('proxy') else 'No')} | "
            f"Mobile {('Yes' if item.get('mobile') else 'No')}",
            width,
        ))
        lines.extend(wrap_label_value("Type", likely_type(item), width))
        lines.extend(wrap_label_value("Risk", f"{flag}  |  score {score}", width, suspicion_color(flag)))
        lines.extend(wrap_label_value("Reasons", ", ".join(reasons) if reasons else "None", width))

        print_box(f"{ip}  |  seen {seen}x", lines, tone=suspicion_color(flag), width=width)


def print_country_grouping(results, counts):
    country_map = defaultdict(list)

    for item in results:
        if item.get("status") == "success":
            country = item.get("country", "Unknown") or "Unknown"
            country_map[country].append(item)

    header("GROUPED BY COUNTRY", "Country buckets keep related results together for quick review.")

    if not country_map:
        print_box("Grouped By Country", [color("No successful results to group.", WARNING)], tone=WARNING)
        return

    for country in sorted(country_map.keys()):
        items = country_map[country]
        total_hits = sum(counts.get(item.get("query", ""), 1) for item in items)
        print_box(
            country,
            [
                f"{color('Unique IPs', DIM + MUTED)} : {len(items)}",
                f"{color('Total Hits', DIM + MUTED)} : {total_hits}",
            ],
            tone=ACCENT,
            width=min(terminal_width(), 72),
        )

        columns = [
            {"title": "IP", "width": 15, "min_width": 15},
            {"title": "City", "width": 18, "min_width": 12},
            {"title": "Provider", "width": 26, "min_width": 16},
            {"title": "Risk", "width": 10, "min_width": 8},
            {"title": "Type", "width": 18, "min_width": 14},
        ]
        fitted = fit_column_widths(columns)
        for column, width in zip(columns, fitted):
            column["width"] = width

        rows = []
        for item in items:
            flag, _, _ = suspicion_score(item)
            type_text = safe(likely_type(item), columns[4]["width"])
            rows.append([
                safe(item.get("query", "N/A"), columns[0]["width"]),
                safe(item.get("city", "N/A"), columns[1]["width"]),
                safe(format_provider(item), columns[2]["width"]),
                color(safe(flag, columns[3]["width"]), BOLD + suspicion_color(flag)),
                color(type_text, type_tone(likely_type(item))),
            ])

        render_table(columns, rows, tone=ACCENT)


def print_duplicates(counts):
    header("DUPLICATE SUMMARY", "Repeated IPs are shown first so reuse stands out immediately.")

    duplicates = [(ip, count) for ip, count in counts.items() if count > 1]

    if not duplicates:
        print_box("Duplicate Summary", [color("No duplicate IPs found.", SUCCESS)], tone=SUCCESS)
        return

    duplicates.sort(key=lambda x: x[1], reverse=True)
    columns = [
        {"title": "IP", "width": 15, "min_width": 15},
        {"title": "Seen", "width": 5, "min_width": 5, "align": "right"},
    ]
    rows = [[ip, color(str(count), BOLD + ACCENT)] for ip, count in duplicates]
    render_table(columns, rows, tone=ACCENT)


def print_invalid(invalid):
    if not invalid:
        return

    header("INVALID / SKIPPED", "Entries below were ignored because they were not valid IPv4 addresses.")
    wrapped = textwrap.wrap(", ".join(invalid), width=max(30, min(terminal_width(), 100) - 8))
    print_box("Skipped Entries", [color(line, WARNING) for line in wrapped], tone=WARNING, width=min(terminal_width(), 100))


def print_type_summary(results, counts):
    header("TYPE SUMMARY", "Unique IPs and total hits by classification.")

    summary = Counter()
    total_hits_by_type = Counter()

    for item in results:
        if item.get("status") != "success":
            summary["Lookup Failed"] += 1
            total_hits_by_type["Lookup Failed"] += counts.get(item.get("query", ""), 1)
            continue

        ip_type = likely_type(item)
        summary[ip_type] += 1
        total_hits_by_type[ip_type] += counts.get(item.get("query", ""), 1)

    columns = [
        {"title": "Type", "width": 22, "min_width": 16},
        {"title": "Unique", "width": 6, "min_width": 6, "align": "right"},
        {"title": "Hits", "width": 6, "min_width": 6, "align": "right"},
    ]
    rows = []
    for label, unique_count in summary.most_common():
        rows.append([
            color(safe(label, columns[0]["width"]), type_tone(label)),
            color(str(unique_count), BOLD + ACCENT),
            color(str(total_hits_by_type[label]), BOLD + ACCENT),
        ])
    render_table(columns, rows, tone=ACCENT)


def print_asn_summary(results, counts, limit=10):
    summary = defaultdict(lambda: {"unique": 0, "hits": 0})

    for item in results:
        if item.get("status") != "success":
            continue

        asn = item.get("as", "Unknown") or "Unknown"
        asname = item.get("asname", "Unknown") or "Unknown"
        label = f"{asn} | {asname}"
        summary[label]["unique"] += 1
        summary[label]["hits"] += counts.get(item.get("query", ""), 1)

    header("ASN SUMMARY", "Top networks by unique IP count and total hits.")

    if not summary:
        print_box("ASN Summary", [color("No successful ASN data available.", WARNING)], tone=WARNING)
        return

    ranked = sorted(summary.items(), key=lambda entry: (entry[1]["hits"], entry[1]["unique"]), reverse=True)
    columns = [
        {"title": "ASN / Name", "width": 44, "min_width": 24},
        {"title": "Unique", "width": 6, "min_width": 6, "align": "right"},
        {"title": "Hits", "width": 6, "min_width": 6, "align": "right"},
    ]
    fitted = fit_column_widths(columns)
    for column, width in zip(columns, fitted):
        column["width"] = width

    rows = []
    for label, data in ranked[:limit]:
        rows.append([
            safe(label, columns[0]["width"]),
            color(str(data["unique"]), BOLD + ACCENT),
            color(str(data["hits"]), BOLD + ACCENT),
        ])

    render_table(columns, rows, tone=ACCENT)
    if len(ranked) > limit:
        print(color(f"Showing top {limit} of {len(ranked)} ASN entries.", DIM + MUTED))


def print_subnet_summary(results, counts, limit=10):
    summary = defaultdict(lambda: {"unique": 0, "hits": 0})

    for item in results:
        query = item.get("query", "")
        if not is_valid_ipv4(query):
            continue

        subnet = str(ipaddress.ip_network(f"{query}/24", strict=False))
        summary[subnet]["unique"] += 1
        summary[subnet]["hits"] += counts.get(query, 1)

    header("SUBNET SUMMARY", "Top /24 ranges by unique IP count and total hits.")

    if not summary:
        print_box("Subnet Summary", [color("No subnet data available.", WARNING)], tone=WARNING)
        return

    ranked = sorted(summary.items(), key=lambda entry: (entry[1]["hits"], entry[1]["unique"]), reverse=True)
    columns = [
        {"title": "/24 Subnet", "width": 18, "min_width": 18},
        {"title": "Unique", "width": 6, "min_width": 6, "align": "right"},
        {"title": "Hits", "width": 6, "min_width": 6, "align": "right"},
    ]
    rows = []
    for subnet, data in ranked[:limit]:
        rows.append([
            subnet,
            color(str(data["unique"]), BOLD + ACCENT),
            color(str(data["hits"]), BOLD + ACCENT),
        ])

    render_table(columns, rows, tone=ACCENT)
    if len(ranked) > limit:
        print(color(f"Showing top {limit} of {len(ranked)} subnets.", DIM + MUTED))


# ==================================================
# Enrichment Routing
# ==================================================


ENRICHMENT_RENDERERS = {
    "type_summary": print_type_summary,
    "duplicates": lambda results, counts: print_duplicates(counts),
    "country_grouping": print_country_grouping,
    "asn_summary": print_asn_summary,
    "subnet_summary": print_subnet_summary,
    "detailed_results": print_detailed_results,
}


def render_enabled_enrichments(results, counts, profile):
    for option in OPTIONAL_ENRICHMENTS:
        if option.key == "detailed_results":
            continue
        if profile.is_enabled(option.key):
            renderer = ENRICHMENT_RENDERERS.get(option.key)
            if renderer:
                renderer(results, counts)


def render_detailed_results_if_enabled(results, counts, profile):
    if profile.prompt_for_details:
        if ask_yes_no("Show detailed results too?", default="n"):
            print_detailed_results(results, counts)
    elif profile.is_enabled("detailed_results"):
        print_detailed_results(results, counts)


# ==================================================
# Export
# ==================================================


def save_to_csv(results, counts, filename="ip_results.csv"):
    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            "IP",
            "Count",
            "Status",
            "Country",
            "CountryCode",
            "Region",
            "City",
            "ZIP",
            "Latitude",
            "Longitude",
            "Timezone",
            "ISP",
            "Org",
            "ASN",
            "ASName",
            "Hosting",
            "Proxy",
            "Mobile",
            "Type",
            "SuspicionFlag",
            "Score",
            "Reasons",
            "Message",
        ])

        for item in results:
            ip = item.get("query", "")
            if item.get("status") == "success":
                flag, reasons, score = suspicion_score(item)
                ip_type = likely_type(item)
                reasons_text = ", ".join(reasons)
            else:
                flag = "N/A"
                reasons_text = ""
                score = ""
                ip_type = "Lookup Failed"

            writer.writerow([
                ip,
                item.get("count", counts.get(ip, 1)),
                item.get("status", ""),
                item.get("country", ""),
                item.get("countryCode", ""),
                item.get("regionName", ""),
                item.get("city", ""),
                item.get("zip", ""),
                item.get("lat", ""),
                item.get("lon", ""),
                item.get("timezone", ""),
                item.get("isp", ""),
                item.get("org", ""),
                item.get("as", ""),
                item.get("asname", ""),
                item.get("hosting", ""),
                item.get("proxy", ""),
                item.get("mobile", ""),
                ip_type,
                flag,
                score,
                reasons_text,
                item.get("message", ""),
            ])


def save_to_json(results, counts, filename="ip_results.json"):
    output = []

    for item in results:
        if isinstance(item, IPResultRecord):
            enriched = item.to_export_dict()
        else:
            ip = item.get("query", "")
            enriched = dict(item)
            enriched["count"] = counts.get(ip, 1)

            if item.get("status") == "success":
                flag, reasons, score = suspicion_score(item)
                enriched["type"] = likely_type(item)
                enriched["suspicion_flag"] = flag
                enriched["suspicion_score"] = score
                enriched["reasons"] = reasons
            else:
                enriched["type"] = "Lookup Failed"
                enriched["suspicion_flag"] = "N/A"
                enriched["suspicion_score"] = None
                enriched["reasons"] = []

        output.append(enriched)

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)


def run_export_flow(results, counts):
    if ask_yes_no("Save results to CSV?", default="n"):
        filename = prompt("Enter filename [ip_results.csv]: ")
        if not filename:
            filename = "ip_results.csv"
        save_to_csv(results, counts, filename)
        print(color(f"Saved CSV to {filename}", SUCCESS))

    if ask_yes_no("Save results to JSON too?", default="n"):
        filename = prompt("Enter filename [ip_results.json]: ")
        if not filename:
            filename = "ip_results.json"
        save_to_json(results, counts, filename)
        print(color(f"Saved JSON to {filename}", SUCCESS))


# ==================================================
# Input Sources
# ==================================================


def read_from_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def read_from_paste():
    print_box(
        "Paste Mode",
        [
            "Paste your IPs below.",
            "Type /start on a new line when you want to begin the lookup.",
            "Type /clear to reset your pasted input or /cancel to go back.",
        ],
        tone=ACCENT,
        width=min(terminal_width(), 82),
    )
    lines = []

    while True:
        try:
            line = input()
        except EOFError:
            break

        command = line.strip().lower()

        if command == "/start":
            if any(entry.strip() for entry in lines):
                return "\n".join(lines)
            print(color("Nothing pasted yet.", WARNING))
            continue

        if command == "/clear":
            lines.clear()
            print(color("Pasted input cleared.", WARNING))
            continue

        if command == "/cancel":
            print(color("Paste mode cancelled.", WARNING))
            return None

        lines.append(line)

    return "\n".join(lines)


def choose_input(workflow_preset):
    print_step(1, workflow_preset.step_total, "Choose input source", "Paste directly or load a text file containing IPv4 addresses.")

    while True:
        print_box(
            "Input Source",
            [
                f"{color('1', BOLD + ACCENT)}  Paste IPs manually",
                f"{color('2', BOLD + ACCENT)}  Load IPs from file",
                f"{color('3', BOLD + ACCENT)}  Exit",
            ],
            tone=PRIMARY,
            width=min(terminal_width(), 72),
        )

        choice = prompt("Choose an option [1-3]: ")

        if choice == "1":
            pasted = read_from_paste()
            if pasted is None:
                continue
            return pasted
        if choice == "2":
            path = prompt("Enter file path: ").strip().strip('"')
            try:
                return read_from_file(path)
            except FileNotFoundError:
                print(color("File not found.", DANGER))
            except Exception as e:
                print(color(f"Failed to read file: {e}", DANGER))
            continue
        if choice == "3":
            sys.exit(0)
        print(color("Invalid choice.", WARNING))


# ==================================================
# Profile Selection
# ==================================================


def enabled_enrichment_labels(profile):
    labels = []
    for item in OPTIONAL_ENRICHMENTS:
        if profile.is_enabled(item.key):
            labels.append(item.label)
    return labels


def print_scan_profile_summary(profile):
    enabled_labels = enabled_enrichment_labels(profile)
    lines = [
        f"{color('Profile', DIM + MUTED)} : {color(profile.name, BOLD + ACCENT)}",
        f"{color('Mode', DIM + MUTED)} : {profile.description}",
    ]

    if enabled_labels:
        wrapped = textwrap.wrap(", ".join(enabled_labels), width=max(28, min(terminal_width(), 92) - 20)) or [""]
        lines.append(f"{color('Extras', DIM + MUTED)} : {wrapped[0]}")
        for part in wrapped[1:]:
            lines.append((" " * 11) + part)
    else:
        lines.append(f"{color('Extras', DIM + MUTED)} : None")

    if profile.prompt_for_details:
        lines.append(f"{color('Details', DIM + MUTED)} : Ask before showing detailed results")
    elif profile.is_enabled("detailed_results"):
        lines.append(f"{color('Details', DIM + MUTED)} : Show detailed results automatically")
    else:
        lines.append(f"{color('Details', DIM + MUTED)} : Skip detailed results")

    print_box("Scan Profile", lines, tone=ACCENT, width=min(terminal_width(), 92))


def build_custom_scan_profile():
    print_box(
        "Custom Options",
        [
            "Toggle optional enrichments one by one.",
            "Defaults follow Standard scan so you can trim or expand from there.",
        ],
        tone=ACCENT,
        width=min(terminal_width(), 84),
    )

    defaults = SCAN_PROFILES["standard"].enabled
    enabled = set()

    for item in OPTIONAL_ENRICHMENTS:
        default = "y" if item.key in defaults else "n"
        question = f"Enable {item.label.lower()}? {item.description}"
        if ask_yes_no(question, default=default):
            enabled.add(item.key)

    return ScanProfile(
        key="custom",
        name="Custom options",
        description="Manual enrichment selection for this run.",
        enabled=enabled,
        prompt_for_details=False,
    )


def choose_scan_profile(workflow_preset):
    print_step(3, workflow_preset.step_total, "Choose scan profile", "Standard scan is the recommended default.")

    while True:
        print_box(
            "Scan Profiles",
            [
                f"{color('1', BOLD + ACCENT)}  Quick scan     Fastest core view with a few high-value summaries",
                f"{color('2', BOLD + ACCENT)}  Standard scan  Recommended default balance of speed and enrichment",
                f"{color('3', BOLD + ACCENT)}  Deep scan      All summaries plus full detailed results",
                f"{color('4', BOLD + ACCENT)}  Custom options Choose optional enrichments manually",
                f"{color('5', BOLD + ACCENT)}  Exit",
            ],
            tone=PRIMARY,
            width=min(terminal_width(), 92),
        )

        choice = prompt("Choose a profile [1-5, Enter=2]: ")
        if not choice:
            choice = "2" if workflow_preset.default_profile_key == "standard" else "1"

        if choice == "1":
            profile = get_scan_profile("quick")
            print_scan_profile_summary(profile)
            return profile
        if choice == "2":
            profile = get_scan_profile("standard")
            print_scan_profile_summary(profile)
            return profile
        if choice == "3":
            profile = get_scan_profile("deep")
            print_scan_profile_summary(profile)
            return profile
        if choice == "4":
            profile = build_custom_scan_profile()
            print_scan_profile_summary(profile)
            return profile
        if choice == "5":
            sys.exit(0)

        print(color("Invalid choice.", WARNING))


def sort_results(results, counts):
    priority = {
        "VERY HIGH": 4,
        "HIGH": 3,
        "MEDIUM": 2,
        "LOW": 1,
        "NONE": 0,
    }

    def sort_key(item):
        if item.get("status") != "success":
            return (-1, counts.get(item.get("query", ""), 1), -999)

        flag, _, score = suspicion_score(item)
        return (
            priority[flag],
            score,
            counts.get(item.get("query", ""), 1),
        )

    return sorted(results, key=sort_key, reverse=True)


def render_review_sections(results, counts, invalid_ips, profile):
    print_result_overview(results, counts)
    print_results_table(results, counts)
    render_enabled_enrichments(results, counts, profile)
    render_detailed_results_if_enabled(results, counts, profile)
    print_invalid(invalid_ips)


def run_lookup_workflow():
    workflow_preset = get_workflow_preset()
    ip_text = choose_input(workflow_preset)

    parsed_input = parse_input_text(ip_text)

    if not parsed_input.valid_ips:
        print(color("\nNo valid IPv4 addresses found.", DANGER))
        if parsed_input.invalid_ips:
            print_invalid(parsed_input.invalid_ips)
        return

    print_step(2, workflow_preset.step_total, "Parse and validate input", "Reviewing deduplicated entries before lookup.")
    print_input_summary(parsed_input.valid_ips, parsed_input.invalid_ips, parsed_input.counts)

    profile = choose_scan_profile(workflow_preset)

    print_step(
        4,
        workflow_preset.step_total,
        "Run geolocation lookup",
        (
            f"Using {profile.name}. "
            f"Submitting {len(parsed_input.valid_ips)} unique IP"
            f"{'s' if len(parsed_input.valid_ips) != 1 else ''} to the batch API."
        ),
    )
    raw_results = run_with_spinner("Looking up IPs...", lookup_ips, parsed_input.valid_ips)
    results = hydrate_result_records(raw_results, parsed_input.counts)
    results = sort_results(results, parsed_input.counts)

    print_step(
        5,
        workflow_preset.step_total,
        "Review results and export",
        "Core results come first, then profile-driven enrichments and exports.",
    )
    render_review_sections(results, parsed_input.counts, parsed_input.invalid_ips, profile)
    run_export_flow(results, parsed_input.counts)


# ==================================================
# Main Workflow
# ==================================================


def main():
    enable_windows_terminal()
    show_banner()

    try:
        run_lookup_workflow()
    except urllib.error.HTTPError as e:
        print(color(f"HTTP error: {e.code} {e.reason}", DANGER))
    except urllib.error.URLError as e:
        print(color(f"Connection error: {e.reason}", DANGER))
    except KeyboardInterrupt:
        print(color("\nStopped by user.", WARNING))
    except Exception as e:
        print(color(f"Unexpected error: {e}", DANGER))


if __name__ == "__main__":
    main()
