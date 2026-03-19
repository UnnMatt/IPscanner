import os
import re
import csv
import json
import sys
import ipaddress
import itertools
import socket
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
TOR_EXIT_LIST_URL = "https://check.torproject.org/torbulkexitlist"

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
    print(color("  Type /help at prompts for a quick guide", DIM + MUTED))


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


def help_score_lines():
    return [
        f"{color('Base idea', DIM + MUTED)} : Quick review aid, not a final verdict.",
        f"{color('Points', DIM + MUTED)} : Hosting +5 | Proxy +5 | Tor exit +6 | Mobile -2",
        f"{color('Provider text', DIM + MUTED)} : ISP, Org, ASN, and AS Name are checked for infrastructure keywords.",
        f"{color('Extra clues', DIM + MUTED)} : ASN present +1 | known infra ISP/org match +2 | hosting-like AS name +2",
        f"{color('Risk bands', DIM + MUTED)} : 9+ VERY HIGH | 6-8 HIGH | 3-5 MEDIUM | 1-2 LOW | 0 or less NONE",
        f"{color('Type labels', DIM + MUTED)} : High evidence -> Likely Datacenter/VPN | Medium -> Manual Review | Low/None -> Lower suspicion",
    ]


def help_workflow_lines():
    return [
        "Core Lookup: normal/default scan path.",
        "Threat Signals: same core flow, but pushes you toward deeper review.",
        "Ownership Intel: later-phase shell that currently routes through the core flow.",
        "Full Investigation: broadest current shell, still built on the core flow.",
    ]


def help_profile_lines():
    return [
        "Quick scan: fastest pass, fewer summaries.",
        "Standard scan: recommended balance for normal use.",
        "Deep scan: all available summaries and detailed records.",
        "Custom options: choose each optional summary manually.",
    ]


def help_usage_lines():
    return [
        "Paste mode accepts IPv4, IPv6, or mixed input.",
        "Use /start to begin, /clear to reset pasted input, /cancel to go back.",
        "Use /help at prompts to reopen this guide.",
        "Main table is the fast overview. Detailed results are for follow-up review.",
    ]


def show_help():
    width = min(terminal_width(), 100)
    header("HELP", "Quick guide to the scan flow, risk points, and settings.")
    print_box("How It Works", help_usage_lines(), tone=ACCENT, width=width)
    print_box("Risk Points", help_score_lines(), tone=PRIMARY, width=width)
    print_box("Workflows", help_workflow_lines(), tone=ACCENT, width=width)
    print_box("Scan Profiles", help_profile_lines(), tone=PRIMARY, width=width)


def prompt(text):
    while True:
        value = input(color(text, BOLD + ACCENT)).strip()
        if value.lower() == "/help":
            show_help()
            continue
        return value


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
    step_total: int = 6
    availability_note: str = ""


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
    tor_exit: Optional[bool] = None
    tor_status: str = "not_checked"
    reverse_dns: str = ""
    reverse_dns_status: str = "not_checked"
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
            "tor_exit": self.tor_exit,
            "tor_status": self.tor_status,
            "reverse_dns": self.reverse_dns,
            "reverse_dns_status": self.reverse_dns_status,
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
        description="Top IPv4 /24 and IPv6 /64 ranges by unique IP count and total hits.",
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
        description="Fastest first pass.",
        enabled={"type_summary", "duplicates"},
        prompt_for_details=False,
    ),
    "standard": ScanProfile(
        key="standard",
        name="Standard scan",
        description="Best default balance.",
        enabled={"type_summary", "duplicates", "country_grouping", "asn_summary", "subnet_summary"},
        prompt_for_details=True,
    ),
    "deep": ScanProfile(
        key="deep",
        name="Deep scan",
        description="All available summaries and details.",
        enabled={item.key for item in OPTIONAL_ENRICHMENTS},
        prompt_for_details=False,
    ),
}

WORKFLOW_MENU_ORDER = [
    "core_lookup",
    "threat_signals",
    "ownership_intel",
    "full_investigation",
]

DEFAULT_WORKFLOW_PRESET_KEY = "core_lookup"
WORKFLOW_PRESETS = {
    "core_lookup": WorkflowPreset(
        key="core_lookup",
        name="Core Lookup",
        description="Best for most checks.",
        default_profile_key="standard",
    ),
    "threat_signals": WorkflowPreset(
        key="threat_signals",
        name="Threat Signals",
        description="Stronger signal-focused review.",
        default_profile_key="deep",
    ),
    "ownership_intel": WorkflowPreset(
        key="ownership_intel",
        name="Ownership Intel",
        description="Ownership-oriented path.",
        default_profile_key="standard",
        availability_note="Later phase. Uses the core lookup flow for now.",
    ),
    "full_investigation": WorkflowPreset(
        key="full_investigation",
        name="Full Investigation",
        description="Broadest current review.",
        default_profile_key="deep",
        availability_note="Later phase. Uses the broadest current scan path for now.",
    ),
}


def get_scan_profile(profile_key):
    return SCAN_PROFILES[profile_key].runtime_copy()


def get_workflow_preset(preset_key=DEFAULT_WORKFLOW_PRESET_KEY):
    return WORKFLOW_PRESETS[preset_key]


def workflow_menu_lines():
    lines = []

    for index, preset_key in enumerate(WORKFLOW_MENU_ORDER, start=1):
        preset = WORKFLOW_PRESETS[preset_key]
        if preset.key == DEFAULT_WORKFLOW_PRESET_KEY:
            prefix = color("Recommended", BOLD + SUCCESS)
        elif preset.availability_note:
            prefix = color("Later phase", BOLD + WARNING)
        else:
            prefix = color("Available", BOLD + ACCENT)
        lines.append(f"{color(str(index), BOLD + ACCENT)}  {preset.name.ljust(18)} {prefix}  {preset.description}")

    lines.append(f"{color(str(len(WORKFLOW_MENU_ORDER) + 1), BOLD + ACCENT)}  Exit")
    return lines


def print_compact_message(text, tone=DIM + MUTED, indent=2):
    width = max(30, terminal_width() - indent - 2)
    wrapped = textwrap.wrap(text, width=width) or [""]
    for part in wrapped:
        print((" " * indent) + color(part, tone))


def print_workflow_preset_summary(workflow_preset):
    lines = [
        f"{color('Workflow', DIM + MUTED)} : {color(workflow_preset.name, BOLD + ACCENT)}",
        f"{color('Focus', DIM + MUTED)} : {workflow_preset.description}",
    ]
    if workflow_preset.availability_note:
        lines.append(f"{color('Status', DIM + MUTED)} : {workflow_preset.availability_note}")
    print_box("Workflow Selected", lines, tone=ACCENT, width=min(terminal_width(), 92))


def get_recommended_scan_profile(workflow_preset):
    return get_scan_profile(workflow_preset.default_profile_key)


def print_recommended_scan_setup(workflow_preset, profile):
    print_box(
        "Recommended Scan Setup",
        [
            f"{color('Profile', DIM + MUTED)} : {color(profile.name, BOLD + ACCENT)}",
            f"{color('Reason', DIM + MUTED)} : {profile.description}",
        ],
        tone=ACCENT,
        width=min(terminal_width(), 88),
    )


def choose_workflow_preset():
    print_step(1, WORKFLOW_PRESETS[DEFAULT_WORKFLOW_PRESET_KEY].step_total, "Choose workflow", "Core Lookup is the best starting point for most scans.")

    while True:
        print_box(
            "Main Menu",
            workflow_menu_lines(),
            tone=PRIMARY,
            width=min(terminal_width(), 92),
        )

        choice = prompt(f"Choose a workflow [1-{len(WORKFLOW_MENU_ORDER) + 1}, Enter=1]: ")
        if not choice:
            choice = "1"

        if choice.isdigit():
            choice_number = int(choice)
            if 1 <= choice_number <= len(WORKFLOW_MENU_ORDER):
                workflow_preset = get_workflow_preset(WORKFLOW_MENU_ORDER[choice_number - 1])
                print_workflow_preset_summary(workflow_preset)
                return workflow_preset
            if choice_number == len(WORKFLOW_MENU_ORDER) + 1:
                sys.exit(0)

        print(color("Invalid choice.", WARNING))


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


def parse_ip_token(value):
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def normalize_ip_token(value):
    parsed = parse_ip_token(value)
    if parsed is None:
        return None
    return str(parsed)


def detect_ip_version(value):
    parsed = parse_ip_token(value)
    if parsed is None:
        return None
    return parsed.version


def is_valid_ip(ip):
    return parse_ip_token(ip) is not None


def is_valid_ipv4(ip):
    parsed = parse_ip_token(ip)
    return parsed is not None and parsed.version == 4


def parse_input_text(text):
    raw_items = re.split(r"[\s,;]+", text.strip())
    raw_items = [item.strip() for item in raw_items if item.strip()]

    valid = []
    invalid = []

    for item in raw_items:
        normalized = normalize_ip_token(item)
        if normalized is not None:
            valid.append(normalized)
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
# Enrichment Logic
# ==================================================


def reverse_dns_lookup(ip, timeout=2.0):
    state = {
        "hostname": "",
        "status": "error",
    }
    finished = threading.Event()

    def worker():
        try:
            host, aliases, _ = socket.gethostbyaddr(ip)
            hostname = (host or "").strip().rstrip(".")
            if not hostname and aliases:
                hostname = aliases[0].strip().rstrip(".")

            if hostname:
                state["hostname"] = hostname
                state["status"] = "found"
            else:
                state["status"] = "not_found"
        except (socket.herror, socket.gaierror, UnicodeError):
            state["status"] = "not_found"
        except Exception:
            state["status"] = "error"
        finally:
            finished.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    if not finished.wait(timeout):
        return "", "timeout"

    return state["hostname"], state["status"]


def enrich_record_with_reverse_dns(record, timeout=2.0):
    hostname, status = reverse_dns_lookup(record.query, timeout=timeout)
    record.reverse_dns = hostname
    record.reverse_dns_status = status
    return record


def enrich_records_with_reverse_dns(records, timeout=2.0):
    for record in records:
        enrich_record_with_reverse_dns(record, timeout=timeout)
    return records


# ==================================================
# Threat-Signal Components
# ==================================================


def fetch_tor_exit_nodes(timeout=5.0):
    req = urllib.request.Request(
        TOR_EXIT_LIST_URL,
        headers={"User-Agent": "ipscanner/1.0"},
    )

    with urllib.request.urlopen(req, timeout=timeout) as response:
        content = response.read().decode("utf-8", errors="replace")

    exit_nodes = set()
    for line in content.splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        normalized = normalize_ip_token(value)
        if normalized is not None:
            exit_nodes.add(normalized)

    return exit_nodes


def enrich_records_with_tor_signal(records, timeout=5.0):
    try:
        exit_nodes = fetch_tor_exit_nodes(timeout=timeout)
    except Exception:
        for record in records:
            record.tor_exit = None
            record.tor_status = "unavailable"
        return records

    for record in records:
        record.tor_exit = record.query in exit_nodes
        record.tor_status = "listed" if record.tor_exit else "not_listed"

    return records


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

    if item.get("tor_exit") is True:
        score += 6
        reasons.append("tor_exit=true")

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
        tor_exit=None,
        tor_status="not_checked",
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


def ip_column_width():
    return 28


def ip_min_width():
    return 18


def truncate_middle(value, max_len):
    text = str(value) if value is not None else "N/A"
    if not max_len or len(text) <= max_len:
        return text
    if max_len <= 5:
        return safe(text, max_len)

    left = (max_len - 3) // 2
    right = max_len - 3 - left
    return text[:left] + "..." + text[-right:]


def format_ip_display(value, max_len):
    text = str(value) if value is not None else "N/A"
    if ":" in text:
        return truncate_middle(text, max_len)
    return safe(text, max_len)


def format_subnet_display(value, max_len):
    text = str(value) if value is not None else "N/A"
    if ":" in text:
        return truncate_middle(text, max_len)
    return safe(text, max_len)


def detailed_box_title(ip, seen, width):
    suffix = f"  |  seen {seen}x"
    available = max(12, width - len(suffix) - 6)
    return f"{format_ip_display(ip, available)}{suffix}"


def format_reverse_dns(item):
    hostname = item.get("reverse_dns", "")
    status = item.get("reverse_dns_status", "not_checked")

    if hostname:
        return hostname
    if status == "not_found":
        return "Not found"
    if status == "timeout":
        return "Timed out"
    if status == "error":
        return "Unavailable"
    return "Not checked"


def format_tor_status(item):
    if item.get("tor_exit") is True:
        return "Yes"

    status = item.get("tor_status", "not_checked")
    if status == "not_listed":
        return "No"
    if status == "unavailable":
        return "Unavailable"
    return "Not checked"


def has_positive_reverse_dns(item):
    return bool(item.get("reverse_dns", ""))


def has_interesting_tor_state(item):
    status = item.get("tor_status", "not_checked")
    return item.get("tor_exit") is True or status == "unavailable"


def subnet_label_for_ip(value):
    parsed = parse_ip_token(value)
    if parsed is None:
        return None

    prefix = 24 if parsed.version == 4 else 64
    return str(ipaddress.ip_network(f"{parsed}/{prefix}", strict=False))


def format_location(item):
    country = item.get("country", "N/A")
    city = item.get("city", "N/A")
    if country and city and country != "N/A" and city != "N/A":
        return f"{country} / {city}"
    return country or city or "N/A"


def format_detailed_location(item):
    country = item.get("country", "N/A") or "N/A"
    region = item.get("regionName", "N/A") or "N/A"
    city = item.get("city", "N/A") or "N/A"

    parts = [part for part in (country, region, city) if part and part != "N/A"]
    if parts:
        return " / ".join(parts)

    return country or city or "N/A"


def format_provider(item):
    isp = item.get("isp", "N/A")
    org = item.get("org", "N/A")
    if isp and org and isp not in {"", "N/A"} and org not in {"", "N/A"} and isp != org:
        return f"{isp} / {org}"
    return isp if isp not in {"", None} else (org or "N/A")


def format_network(item):
    asn = item.get("as", "") or ""
    asname = item.get("asname", "") or ""

    if asn and asname:
        return f"{asn} / {asname}"
    if asn:
        return asn
    if asname:
        return asname
    return "N/A"


def format_signal_summary(item):
    parts = []
    if item.get("tor_exit") is True:
        parts.append("Tor")
    if item.get("proxy"):
        parts.append("Proxy")
    if item.get("hosting"):
        parts.append("Hosting")
    if item.get("mobile"):
        parts.append("Mobile")
    return ", ".join(parts) if parts else "None"


def format_risk_summary(item):
    flag, _, score = suspicion_score(item)
    return f"{flag}  |  score {score}  |  {likely_type(item)}"


def summarize_duplicates(counts):
    return [(ip, count) for ip, count in counts.items() if count > 1]


def summarize_country_groups(results, counts):
    country_map = defaultdict(list)

    for item in results:
        if item.get("status") == "success":
            country = item.get("country", "Unknown") or "Unknown"
            country_map[country].append(item)

    summary = []
    for country, items in country_map.items():
        total_hits = sum(counts.get(item.get("query", ""), 1) for item in items)
        summary.append((country, items, total_hits))

    summary.sort(key=lambda entry: (entry[2], len(entry[1]), entry[0]), reverse=True)
    return [entry for entry in summary if len(entry[1]) > 1 or entry[2] > 1]


def summarize_asn_rows(results, counts):
    summary = defaultdict(lambda: {"unique": 0, "hits": 0})

    for item in results:
        if item.get("status") != "success":
            continue

        asn = item.get("as", "Unknown") or "Unknown"
        asname = item.get("asname", "Unknown") or "Unknown"
        label = f"{asn} | {asname}"
        summary[label]["unique"] += 1
        summary[label]["hits"] += counts.get(item.get("query", ""), 1)

    ranked = sorted(summary.items(), key=lambda entry: (entry[1]["hits"], entry[1]["unique"]), reverse=True)
    return [(label, data) for label, data in ranked if data["unique"] > 1 or data["hits"] > 1]


def summarize_subnet_rows(results, counts):
    summary = defaultdict(lambda: {"unique": 0, "hits": 0})

    for item in results:
        query = item.get("query", "")
        subnet = subnet_label_for_ip(query)
        if subnet is None:
            continue

        summary[subnet]["unique"] += 1
        summary[subnet]["hits"] += counts.get(query, 1)

    ranked = sorted(summary.items(), key=lambda entry: (entry[1]["hits"], entry[1]["unique"]), reverse=True)
    return [(subnet, data) for subnet, data in ranked if data["unique"] > 1 or data["hits"] > 1]


def format_signals(item):
    labels = []
    if item.get("tor_exit"):
        labels.append("Tor")
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
    if item.get("tor_exit"):
        return MAGENTA
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
        {"title": "IP", "width": ip_column_width(), "min_width": ip_min_width()},
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
                color(format_ip_display(ip, columns[0]["width"]), BOLD + DANGER),
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
            color(format_ip_display(ip, columns[0]["width"]), ip_tone),
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
    header("DETAILED RESULTS", "Condensed per-IP view focused on the most useful context.")
    width = min(terminal_width(), 104)

    for item in results:
        ip = item.get("query", "N/A")
        seen = counts.get(ip, 1)

        if item.get("status") != "success":
            lines = []
            if has_interesting_tor_state(item):
                lines.extend(wrap_label_value("Tor", format_tor_status(item), width, MAGENTA if item.get("tor_exit") else None))
            if has_positive_reverse_dns(item):
                lines.extend(wrap_label_value("rDNS", format_reverse_dns(item), width))
            lines.extend(wrap_label_value("Status", f"Lookup failed: {item.get('message', 'Unknown error')}", width, DANGER))
            print_box(
                detailed_box_title(ip, seen, width),
                lines,
                tone=DANGER,
                width=width,
            )
            continue

        flag, reasons, score = suspicion_score(item)
        lines = []
        lines.extend(wrap_label_value("Location", format_detailed_location(item), width))
        lines.extend(wrap_label_value("Provider", format_provider(item), width))

        network_text = format_network(item)
        if network_text != "N/A":
            lines.extend(wrap_label_value("Network", network_text, width))

        if has_interesting_tor_state(item):
            lines.extend(wrap_label_value("Tor", format_tor_status(item), width, MAGENTA if item.get("tor_exit") else None))

        if has_positive_reverse_dns(item):
            lines.extend(wrap_label_value("rDNS", format_reverse_dns(item), width))

        signal_summary = format_signal_summary(item)
        if signal_summary != "None":
            lines.extend(wrap_label_value("Signals", signal_summary, width))

        lines.extend(wrap_label_value("Risk", format_risk_summary(item), width, suspicion_color(flag)))
        lines.extend(wrap_label_value("Reasons", ", ".join(reasons) if reasons else "None", width))

        print_box(detailed_box_title(ip, seen, width), lines, tone=suspicion_color(flag), width=width)


def print_country_grouping(results, counts):
    groups = summarize_country_groups(results, counts)

    if not groups:
        return

    header("GROUPED BY COUNTRY", "Only countries with multiple hits are shown to keep this section focused.")

    for country, items, total_hits in groups:
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
            {"title": "IP", "width": ip_column_width(), "min_width": ip_min_width()},
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
                format_ip_display(item.get("query", "N/A"), columns[0]["width"]),
                safe(item.get("city", "N/A"), columns[1]["width"]),
                safe(format_provider(item), columns[2]["width"]),
                color(safe(flag, columns[3]["width"]), BOLD + suspicion_color(flag)),
                color(type_text, type_tone(likely_type(item))),
            ])

        render_table(columns, rows, tone=ACCENT)


def print_duplicates(counts):
    duplicates = summarize_duplicates(counts)

    if not duplicates:
        return

    header("DUPLICATE SUMMARY", "Repeated IPs are shown first so reuse stands out immediately.")

    duplicates.sort(key=lambda x: x[1], reverse=True)
    columns = [
        {"title": "IP", "width": ip_column_width(), "min_width": ip_min_width()},
        {"title": "Seen", "width": 5, "min_width": 5, "align": "right"},
    ]
    rows = [[format_ip_display(ip, columns[0]["width"]), color(str(count), BOLD + ACCENT)] for ip, count in duplicates]
    render_table(columns, rows, tone=ACCENT)


def print_invalid(invalid):
    if not invalid:
        return

    header("INVALID / SKIPPED", "Entries below were ignored because they were not valid IP addresses.")
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
    ranked = summarize_asn_rows(results, counts)

    if not ranked:
        return

    header("ASN SUMMARY", "Only repeated or clustered networks are shown.")

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
    ranked = summarize_subnet_rows(results, counts)

    if not ranked:
        return

    header("SUBNET SUMMARY", "Only repeated IPv4 /24 and IPv6 /64 ranges are shown.")

    columns = [
        {"title": "Subnet", "width": 43, "min_width": 18},
        {"title": "Unique", "width": 6, "min_width": 6, "align": "right"},
        {"title": "Hits", "width": 6, "min_width": 6, "align": "right"},
    ]
    fitted = fit_column_widths(columns)
    for column, width in zip(columns, fitted):
        column["width"] = width

    rows = []
    for subnet, data in ranked[:limit]:
        rows.append([
            format_subnet_display(subnet, columns[0]["width"]),
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
            "TorExit",
            "TorStatus",
            "ReverseDNS",
            "ReverseDNSStatus",
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
                item.get("tor_exit", ""),
                item.get("tor_status", ""),
                item.get("reverse_dns", ""),
                item.get("reverse_dns_status", ""),
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
            "Type /clear to reset your pasted input, /cancel to go back, or /help for the guide.",
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

        if command == "/help":
            show_help()
            continue

        lines.append(line)

    return "\n".join(lines)


def choose_input(workflow_preset):
    print_step(2, workflow_preset.step_total, "Choose input source", "Select how you want to provide the IPs.")

    while True:
        print_box(
            "Input Source",
            [
                f"{color('Enter', BOLD + ACCENT)}  Paste IPs manually",
                f"{color('F', BOLD + ACCENT)}      Load IPs from file",
                f"{color('Q', BOLD + ACCENT)}      Exit",
            ],
            tone=PRIMARY,
            width=min(terminal_width(), 72),
        )

        choice = prompt("Input source [Enter/F/Q]: ").lower()

        if not choice:
            pasted = read_from_paste()
            if pasted is None:
                continue
            return pasted
        if choice in {"f", "file"}:
            path = prompt("Enter file path: ").strip().strip('"')
            try:
                return read_from_file(path)
            except FileNotFoundError:
                print(color("File not found.", DANGER))
            except Exception as e:
                print(color(f"Failed to read file: {e}", DANGER))
            continue
        if choice in {"q", "quit", "exit"}:
            sys.exit(0)
        print(color("Use Enter for paste mode, F for file, or Q to exit.", WARNING))


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
    print_box(
        "Scan Profile",
        [
            f"{color('Selected', DIM + MUTED)} : {color(profile.name, BOLD + ACCENT)}",
            f"{color('Mode', DIM + MUTED)} : {profile.description}",
        ],
        tone=ACCENT,
        width=min(terminal_width(), 84),
    )


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


def choose_scan_profile(workflow_preset, show_step=True):
    if show_step:
        print_step(4, workflow_preset.step_total, "Choose scan profile", "Pick a different scan profile only if you want to override the recommended setup.")

    default_choices = {
        "quick": "1",
        "standard": "2",
        "deep": "3",
    }
    default_choice = default_choices.get(workflow_preset.default_profile_key, "2")

    while True:
        print_box(
            "Scan Profiles",
            [
                f"{color('1', BOLD + ACCENT)}  Quick scan     Fastest first pass",
                f"{color('2', BOLD + ACCENT)}  Standard scan  Best default balance",
                f"{color('3', BOLD + ACCENT)}  Deep scan      All available summaries and details",
                f"{color('4', BOLD + ACCENT)}  Custom options Choose enrichments manually",
                f"{color('5', BOLD + ACCENT)}  Exit",
            ],
            tone=PRIMARY,
            width=min(terminal_width(), 84),
        )

        choice = prompt(f"Choose a profile [1-5, Enter={default_choice}]: ")
        if not choice:
            choice = default_choice

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


def choose_scan_setup(workflow_preset):
    print_step(4, workflow_preset.step_total, "Confirm scan setup", "The recommended setup is the easiest path.")
    recommended_profile = get_recommended_scan_profile(workflow_preset)
    print_recommended_scan_setup(workflow_preset, recommended_profile)

    if ask_yes_no("Use the recommended scan setup?", default="y"):
        return recommended_profile

    return choose_scan_profile(workflow_preset, show_step=False)


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
    workflow_preset = choose_workflow_preset()
    ip_text = choose_input(workflow_preset)

    parsed_input = parse_input_text(ip_text)

    if not parsed_input.valid_ips:
        print(color("\nNo valid IP addresses found.", DANGER))
        if parsed_input.invalid_ips:
            print_invalid(parsed_input.invalid_ips)
        return

    print_step(3, workflow_preset.step_total, "Parse and validate input", "Reviewing deduplicated entries before lookup.")
    print_input_summary(parsed_input.valid_ips, parsed_input.invalid_ips, parsed_input.counts)

    profile = choose_scan_setup(workflow_preset)

    print_step(
        5,
        workflow_preset.step_total,
        "Run geolocation lookup",
        (
            f"Using {profile.name} under {workflow_preset.name}. "
            f"Submitting {len(parsed_input.valid_ips)} unique IP"
            f"{'s' if len(parsed_input.valid_ips) != 1 else ''} to the batch API."
        ),
    )
    raw_results = run_with_spinner("Looking up IPs...", lookup_ips, parsed_input.valid_ips)
    results = hydrate_result_records(raw_results, parsed_input.counts)
    results = run_with_spinner("Resolving reverse DNS...", enrich_records_with_reverse_dns, results)
    results = run_with_spinner("Checking Tor exit nodes...", enrich_records_with_tor_signal, results)
    results = sort_results(results, parsed_input.counts)

    print_step(
        6,
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
