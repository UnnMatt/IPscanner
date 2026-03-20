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
INTEL_DATA_FILE = "ipscanner_intel.json"
DEFAULT_INTEL_UPDATE_URL = "https://raw.githubusercontent.com/UnnMatt/IPscanner/main/ipscanner_intel.json"
INTEL_UPDATE_URL_ENV = "IPSCANNER_INTEL_URL"

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


def ui_width(limit=112, minimum=48):
    return max(minimum, min(terminal_width(), limit))


def tone_color(tone):
    return tone or ACCENT


def badge(text, tone=ACCENT):
    label = str(text).strip().upper()
    return color(f"[{label}]", BOLD + tone_color(tone))


def muted(text):
    return color(text, DIM + MUTED)


def print_notice(text, tone=ACCENT):
    print(color(f"> {text}", tone))


def print_rule(char="-", tone=MUTED, width=None):
    print(color(char * (width or ui_width()), DIM + tone))


def card_block(title, value, note="", tone=ACCENT, width=24):
    title_text = safe(str(title).upper(), width - 4)
    value_text = safe(str(value), width - 4)
    note_text = safe(str(note), width - 4) if note else ""
    top = color("." + ("-" * (width - 2)) + ".", tone)
    bottom = color("'" + ("-" * (width - 2)) + "'", tone)
    lines = [
        top,
        f"{color('|', tone)} {pad_text(color(title_text, DIM + MUTED), width - 4)} {color('|', tone)}",
        f"{color('|', tone)} {pad_text(color(value_text, BOLD + tone), width - 4)} {color('|', tone)}",
        f"{color('|', tone)} {pad_text(note_text, width - 4)} {color('|', tone)}",
        bottom,
    ]
    return lines


def print_stat_cards(cards, preferred_width=24, gap=2):
    if not cards:
        return

    available = ui_width()
    per_row = max(1, available // (preferred_width + gap))
    per_row = min(per_row, 4)

    for start in range(0, len(cards), per_row):
        chunk = cards[start:start + per_row]
        rendered = [card_block(*card, width=preferred_width) for card in chunk]
        for row in zip(*rendered):
            print((" " * gap).join(row))
        print()


def print_option_panel(index, title, badge_text, summary, detail="", note="", tone=PRIMARY, width=None):
    lines = [
        f"{badge(str(index), tone)} {color(title, BOLD + tone)}  {badge(badge_text, tone)}",
        summary,
    ]
    if detail:
        lines.append(muted(detail))
    if note:
        lines.append(color(note, DIM + WARNING))
    print_box(title, lines, tone=tone, width=width or min(ui_width(), 96))


def panel_header(title, kicker="", tone=PRIMARY, width=None):
    width = min(width or ui_width(), 112)
    kicker_text = f"{kicker} / " if kicker else ""
    label = f"[ {kicker_text}{title} ]"
    fill = max(0, width - len(label) - 2)
    print()
    print(color(label + ("=" * fill), BOLD + tone))


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
    print(color(f"  Intel bundle: {get_active_intel_version()}", DIM + MUTED))
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
        "Core Lookup: balanced day-to-day investigation path with the recommended profile posture.",
        "Threat Signals: pushes toward clustering, suspicious infrastructure, and risk-heavy review.",
        "Ownership Intel: routes through the same engine but frames the output for provider and ownership review.",
        "Full Investigation: widest current visibility path and best entry point for Insanity mode.",
    ]


def help_profile_lines():
    return [
        "Quick: fast triage with a compact matrix and minimal noise.",
        "Standard: recommended default with balanced summaries and optional detail cards.",
        "Threat Hunter: clustering-heavy review focused on infrastructure repetition.",
        "Analyst: expanded intelligence cards for deliberate human review.",
        "Insanity: every meaningful view enabled in a staged layout.",
        "Custom: manual section control for expert workflows.",
    ]


def help_usage_lines():
    return [
        "Paste mode accepts IPv4, IPv6, or mixed input.",
        "Use /start to begin, /clear to reset pasted input, /cancel to go back.",
        "Main menu can check for newer keyword intel without editing the script.",
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


def show_banner():
    clear_screen()

    banner_lines = [
        (PRIMARY, "  ___ ____    ____                                  "),
        (ACCENT, " |_ _|  _ \\  / ___|  ___ __ _ _ __  _ __   ___ _ __ "),
        (ACCENT, "  | || |_) | \\___ \\ / __/ _` | '_ \\| '_ \\ / _ \\ '__|"),
        (CYAN, "  | ||  __/   ___) | (_| (_| | | | | | | |  __/ |   "),
        (BLUE, " |___|_|     |____/ \\___\\__,_|_| |_|_| |_|\\___|_|   "),
    ]

    width = min(ui_width(), 110)
    top = "." + ("=" * (width - 2)) + "."
    bottom = "'" + ("=" * (width - 2)) + "'"

    print()
    print(color(top, PRIMARY))
    for tone, line in banner_lines:
        print(color(pad_text(line, width - 4, "center"), BOLD + tone))
    print(color("-" * (width - 2), DIM + MUTED))
    print(color("  Analyst-grade IP investigation console", BOLD + ACCENT))
    print(color("  Geolocation, enrichment, clustering, export, and live intel review", DIM + MUTED))
    print(
        f"  {badge('LIVE INTEL', SUCCESS)} {muted(f'Bundle {get_active_intel_version()}')}"
        f"   {badge('HELP', PRIMARY)} {muted('Type /help at prompts')}"
    )
    print(color(bottom, PRIMARY))


def header(text, subtitle=None):
    width = ui_width()
    label = f"  {text.upper()}  "
    fill = max(0, width - len(label))
    print()
    print(color(label + ("=" * fill), BOLD + PRIMARY))
    if subtitle:
        print(color(subtitle, DIM + MUTED))
    print(color("-" * width, DIM + MUTED))


def print_step(step, total, title, detail=None):
    panel_header(title.upper(), kicker=f"STEP {step}/{total}", tone=ACCENT, width=ui_width())
    if detail:
        print(color(detail, DIM + MUTED))


def print_box(title, lines, tone=ACCENT, width=None):
    full_width = min(width or ui_width(), 104)
    full_width = max(full_width, len(title) + 8)
    label = f"[ {title} ]"
    top_fill = max(0, full_width - len(label) - 3)

    print(color(".-" + label + ("-" * top_fill) + ".", tone))
    for line in lines:
        content = line if line is not None else ""
        padding = max(0, full_width - visible_len(content) - 4)
        print(f"{color('|', tone)} {content}{' ' * padding} {color('|', tone)}")
    print(color("'" + ("-" * (full_width - 2)) + "'", tone))


def render_table(columns, rows, tone=PRIMARY):
    widths = [column["width"] for column in columns]
    aligns = [column.get("align", "left") for column in columns]
    headers = [column["title"] for column in columns]

    print(color(build_table_border(".", "+", ".", widths), tone))
    print(color(format_table_row(headers, widths, ["center"] * len(columns)), BOLD + tone))
    print(color(build_table_border("+", "+", "+", widths), DIM + tone))
    for row in rows:
        print(format_table_row(row, widths, aligns))
    print(color(build_table_border("'", "+", "'", widths), tone))


def show_help():
    width = min(ui_width(), 108)
    header("HELP CONSOLE", "Reference guide for workflows, profiles, scoring, input, and export behavior.")
    print_box("Workflow Guide", help_workflow_lines(), tone=PRIMARY, width=width)
    print_box("Profile Guide", help_profile_lines(), tone=ACCENT, width=width)
    print_box("Risk Score Guide", help_score_lines(), tone=PRIMARY, width=width)
    print_box(
        "Input Commands",
        [
            "Paste mode: /start begins the scan, /clear resets, /cancel returns, /help reopens this guide.",
            "File mode: point at any text file and the scanner will extract valid IPv4 and IPv6 tokens.",
        ],
        tone=ACCENT,
        width=width,
    )
    print_box(
        "Export Notes",
        [
            "CSV and JSON exports preserve the core lookup, normalized flags, Tor state, reverse DNS, and failure diagnostics.",
            "Intel updates refresh the keyword bundle only. They do not replace the Python script itself.",
        ],
        tone=PRIMARY,
        width=width,
    )
    print_box(
        "Quick Tips",
        [
            "Quick is for triage, Standard is the best default, Threat Hunter leans into clustering, Analyst leans into detailed cards, and Insanity shows the full matrix.",
            "Private, reserved, and local-only addresses are accepted as input but explained separately when public lookup services cannot resolve them.",
        ],
        tone=ACCENT,
        width=width,
    )


def prompt(text):
    while True:
        value = input(color(f"{text}  > ", BOLD + ACCENT)).strip()
        if value.lower() == "/help":
            show_help()
            continue
        return value


def ask_yes_no(question, default="n"):
    suffix = "Y/n" if default.lower() == "y" else "y/N"
    while True:
        choice = prompt(f"{question} [{suffix}]").lower()
        if not choice:
            return default.lower() == "y"
        if choice in {"y", "yes"}:
            return True
        if choice in {"n", "no"}:
            return False
        print_notice("Use y or n.", WARNING)


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

    frames = itertools.cycle(["[=    ]", "[==   ]", "[===  ]", "[ === ]", "[  ===]", "[   ==]", "[    =]"])
    label = f"{message} "

    while not finished.wait(0.1):
        frame = next(frames)
        sys.stdout.write("\r" + color(f"{frame} {label}", BOLD + ACCENT))
        sys.stdout.flush()

    clear_width = len(label) + 12
    sys.stdout.write("\r" + (" " * clear_width) + "\r")
    sys.stdout.flush()
    thread.join()

    if state["error"] is not None:
        raise state["error"]

    print(color(f"[done] {message}", DIM + MUTED))
    return state["result"]


def get_intel_file_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), INTEL_DATA_FILE)


def get_intel_update_url():
    return os.getenv(INTEL_UPDATE_URL_ENV, DEFAULT_INTEL_UPDATE_URL).strip()


def get_active_intel_version():
    return INTEL_CONFIG.get("intel_version", "built-in")


def get_active_intel_updated_at():
    return INTEL_CONFIG.get("updated_at", "")


def get_active_intel_source():
    return INTEL_CONFIG.get("source", "bundled defaults")


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
    badge: str = ""
    purpose: str = ""
    enabled: set = field(default_factory=set)
    section_order: list = field(default_factory=list)
    overview_metrics: list = field(default_factory=list)
    table_mode: str = "standard"
    detail_mode: str = "prompt"
    detail_prompt_default: str = "n"
    show_high_risk_findings: bool = False
    show_failed_lookup_review: bool = False
    show_invalid_entries: bool = True
    show_profile_preamble: bool = True
    prompt_for_details: bool = False

    def runtime_copy(self):
        return ScanProfile(
            key=self.key,
            name=self.name,
            description=self.description,
            badge=self.badge,
            purpose=self.purpose,
            enabled=set(self.enabled),
            section_order=list(self.section_order),
            overview_metrics=list(self.overview_metrics),
            table_mode=self.table_mode,
            detail_mode=self.detail_mode,
            detail_prompt_default=self.detail_prompt_default,
            show_high_risk_findings=self.show_high_risk_findings,
            show_failed_lookup_review=self.show_failed_lookup_review,
            show_invalid_entries=self.show_invalid_entries,
            show_profile_preamble=self.show_profile_preamble,
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
    badge: str = ""
    step_total: int = 6
    availability_note: str = ""


@dataclass
class IntelDiff:
    added: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    changed: list = field(default_factory=list)


@dataclass
class IPResultRecord:
    query: str = ""
    count: int = 1
    status: str = ""
    message: str = ""
    failure_category: str = ""
    failure_range: str = ""
    failure_detail: str = ""
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
            "failure_category": self.failure_category,
            "failure_range": self.failure_range,
            "failure_detail": self.failure_detail,
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
DEFAULT_HARD_KEYWORDS = {
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
DEFAULT_SOFT_KEYWORDS = {
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
DEFAULT_RESIDENTIAL_HINTS = {
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

DEFAULT_HOSTING_LIKE_TERMS = [
    "hosting",
    "cloud",
    "server",
    "datacenter",
    "data center",
    "vps",
    "colo",
    "colocation",
    "proxy",
    "vpn",
]

HARD_KEYWORDS = dict(DEFAULT_HARD_KEYWORDS)
SOFT_KEYWORDS = dict(DEFAULT_SOFT_KEYWORDS)
RESIDENTIAL_HINTS = dict(DEFAULT_RESIDENTIAL_HINTS)
HOSTING_LIKE_TERMS = list(DEFAULT_HOSTING_LIKE_TERMS)
INTEL_CONFIG = {}
INTEL_LOAD_WARNING = ""


def build_default_intel_config():
    return {
        "schema_version": 1,
        "intel_version": "bundled-defaults",
        "updated_at": "",
        "source": "bundled defaults",
        "notes": "Built-in keyword data bundled with the script.",
        "hard_keywords": dict(DEFAULT_HARD_KEYWORDS),
        "soft_keywords": dict(DEFAULT_SOFT_KEYWORDS),
        "residential_hints": dict(DEFAULT_RESIDENTIAL_HINTS),
        "hosting_like_terms": list(DEFAULT_HOSTING_LIKE_TERMS),
    }


def normalize_intel_mapping(field_name, mapping):
    if mapping is None:
        return {}
    if not isinstance(mapping, dict):
        raise ValueError(f"{field_name} must be a JSON object.")

    normalized = {}
    for key, value in mapping.items():
        if not isinstance(key, str):
            raise ValueError(f"{field_name} keys must be strings.")
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{field_name} values must be integers.")

        normalized_key = normalize_text(key)
        if normalized_key:
            normalized[normalized_key] = int(value)

    return dict(sorted(normalized.items()))


def normalize_intel_terms(field_name, values):
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a JSON array.")

    normalized = []
    seen = set()
    for value in values:
        if not isinstance(value, str):
            raise ValueError(f"{field_name} entries must be strings.")
        normalized_value = normalize_text(value)
        if normalized_value and normalized_value not in seen:
            normalized.append(normalized_value)
            seen.add(normalized_value)

    return normalized


def normalize_intel_config(payload, source_label):
    if not isinstance(payload, dict):
        raise ValueError("Intel payload must be a JSON object.")

    defaults = build_default_intel_config()
    schema_version = payload.get("schema_version", defaults["schema_version"])
    if not isinstance(schema_version, int) or isinstance(schema_version, bool) or schema_version < 1:
        raise ValueError("schema_version must be a positive integer.")

    intel_version = str(payload.get("intel_version", defaults["intel_version"])).strip() or defaults["intel_version"]
    updated_at = str(payload.get("updated_at", defaults["updated_at"])).strip()
    source = str(payload.get("source", source_label)).strip() or source_label
    notes = str(payload.get("notes", defaults["notes"])).strip()

    return {
        "schema_version": schema_version,
        "intel_version": intel_version,
        "updated_at": updated_at,
        "source": source,
        "notes": notes,
        "hard_keywords": normalize_intel_mapping("hard_keywords", payload.get("hard_keywords", defaults["hard_keywords"])),
        "soft_keywords": normalize_intel_mapping("soft_keywords", payload.get("soft_keywords", defaults["soft_keywords"])),
        "residential_hints": normalize_intel_mapping("residential_hints", payload.get("residential_hints", defaults["residential_hints"])),
        "hosting_like_terms": normalize_intel_terms("hosting_like_terms", payload.get("hosting_like_terms", defaults["hosting_like_terms"])),
    }


def load_intel_config_from_file(path=None):
    path = path or get_intel_file_path()
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return normalize_intel_config(payload, path)


def fetch_json_url(url, timeout=10.0):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "IPScanner Intel Updater/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_remote_intel_config(url=None, timeout=10.0):
    url = (url or get_intel_update_url()).strip()
    if not url:
        raise ValueError(
            f"No intel update URL configured. Set {INTEL_UPDATE_URL_ENV} or update the default URL."
        )
    payload = fetch_json_url(url, timeout=timeout)
    return normalize_intel_config(payload, url)


def save_intel_config(config, path=None):
    path = path or get_intel_file_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")


def apply_runtime_intel_config(config):
    global HARD_KEYWORDS, SOFT_KEYWORDS, RESIDENTIAL_HINTS, HOSTING_LIKE_TERMS, INTEL_CONFIG

    HARD_KEYWORDS = dict(config["hard_keywords"])
    SOFT_KEYWORDS = dict(config["soft_keywords"])
    RESIDENTIAL_HINTS = dict(config["residential_hints"])
    HOSTING_LIKE_TERMS = list(config["hosting_like_terms"])
    INTEL_CONFIG = dict(config)


def initialize_runtime_intel():
    global INTEL_LOAD_WARNING

    try:
        config = load_intel_config_from_file()
        INTEL_LOAD_WARNING = ""
    except FileNotFoundError:
        config = build_default_intel_config()
        INTEL_LOAD_WARNING = f"{INTEL_DATA_FILE} not found. Using bundled defaults."
    except Exception as exc:
        config = build_default_intel_config()
        INTEL_LOAD_WARNING = f"Failed to load {INTEL_DATA_FILE}: {exc}. Using bundled defaults."

    apply_runtime_intel_config(config)


def compare_intel_mapping(local_mapping, remote_mapping):
    local_keys = set(local_mapping)
    remote_keys = set(remote_mapping)

    added = sorted(remote_keys - local_keys)
    removed = sorted(local_keys - remote_keys)
    changed = sorted(key for key in (local_keys & remote_keys) if local_mapping[key] != remote_mapping[key])
    return IntelDiff(added=added, removed=removed, changed=changed)


def compare_intel_terms(local_values, remote_values):
    local_set = set(local_values)
    remote_set = set(remote_values)
    return IntelDiff(
        added=sorted(remote_set - local_set),
        removed=sorted(local_set - remote_set),
        changed=[],
    )


def diff_count_text(diff):
    return f"+{len(diff.added)} / -{len(diff.removed)} / Δ{len(diff.changed)}"


def preview_diff_items(diff, limit=3):
    parts = []
    if diff.added:
        parts.append(f"add: {', '.join(diff.added[:limit])}")
    if diff.changed:
        parts.append(f"chg: {', '.join(diff.changed[:limit])}")
    if diff.removed:
        parts.append(f"del: {', '.join(diff.removed[:limit])}")
    return " | ".join(parts)


def configs_are_equal(local_config, remote_config):
    return local_config == remote_config


def print_intel_status_box(title, config, tone=ACCENT):
    lines = [
        f"{color('Version', DIM + MUTED)} : {color(config.get('intel_version', 'unknown'), BOLD + ACCENT)}",
        f"{color('Updated', DIM + MUTED)} : {config.get('updated_at', 'N/A') or 'N/A'}",
        f"{color('Source', DIM + MUTED)} : {config.get('source', 'unknown')}",
    ]
    if config.get("notes"):
        lines.append(f"{color('Notes', DIM + MUTED)} : {config['notes']}")
    print_box(title, lines, tone=tone, width=min(terminal_width(), 110))


def run_intel_update_check():
    header("INTEL UPDATES", "Compare local keyword intel with the remote feed and optionally apply it.")
    local_config = dict(INTEL_CONFIG) if INTEL_CONFIG else build_default_intel_config()
    remote_url = get_intel_update_url()

    print_intel_status_box("Current Intel", local_config, tone=ACCENT)
    print_box(
        "Remote Feed",
        [
            f"{color('URL', DIM + MUTED)} : {remote_url}",
            f"{color('Override', DIM + MUTED)} : Set {INTEL_UPDATE_URL_ENV} to use a different JSON feed.",
        ],
        tone=PRIMARY,
        width=min(terminal_width(), 110),
    )

    try:
        remote_config = run_with_spinner("Checking remote intel feed...", fetch_remote_intel_config, remote_url)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            print(color("Remote intel feed was not found. Push ipscanner_intel.json to the repo or set IPSCANNER_INTEL_URL.", WARNING))
            return
        print(color(f"Remote intel check failed: HTTP {exc.code} {exc.reason}", DANGER))
        return
    except urllib.error.URLError as exc:
        print(color(f"Remote intel check failed: {exc.reason}", DANGER))
        return
    except Exception as exc:
        print(color(f"Remote intel check failed: {exc}", DANGER))
        return

    print_intel_status_box("Remote Intel", remote_config, tone=SUCCESS)

    if configs_are_equal(local_config, remote_config):
        print(color("No intel changes found. Your local keyword pack is already current.", SUCCESS))
        return

    hard_diff = compare_intel_mapping(local_config["hard_keywords"], remote_config["hard_keywords"])
    soft_diff = compare_intel_mapping(local_config["soft_keywords"], remote_config["soft_keywords"])
    residential_diff = compare_intel_mapping(local_config["residential_hints"], remote_config["residential_hints"])
    hosting_diff = compare_intel_terms(local_config["hosting_like_terms"], remote_config["hosting_like_terms"])

    lines = [
        f"{color('Hard keywords', DIM + MUTED)} : {diff_count_text(hard_diff)}",
        f"{color('Soft keywords', DIM + MUTED)} : {diff_count_text(soft_diff)}",
        f"{color('Residential', DIM + MUTED)} : {diff_count_text(residential_diff)}",
        f"{color('Hosting terms', DIM + MUTED)} : {diff_count_text(hosting_diff)}",
    ]

    previews = [
        preview_diff_items(hard_diff),
        preview_diff_items(soft_diff),
        preview_diff_items(residential_diff),
        preview_diff_items(hosting_diff),
    ]
    preview_text = next((item for item in previews if item), "")
    if preview_text:
        lines.append(f"{color('Preview', DIM + MUTED)} : {preview_text}")

    print_box("Detected Changes", lines, tone=SUCCESS, width=min(terminal_width(), 110))

    if not ask_yes_no("Apply this intel update now?", default="y"):
        print(color("Intel update skipped. Local keyword data was left unchanged.", WARNING))
        return

    save_intel_config(remote_config)
    apply_runtime_intel_config(remote_config)
    print(color(f"Intel updated to {get_active_intel_version()} and saved to {INTEL_DATA_FILE}.", SUCCESS))

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
        key="provider_summary",
        label="Provider summary",
        description="Repeated provider and organization patterns.",
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
    EnrichmentOption(
        key="failed_lookup_summary",
        label="Failed lookup review",
        description="Grouped diagnostics for addresses that could not resolve public data.",
    ),
]

SCAN_PROFILES = {
    "quick": ScanProfile(
        key="quick",
        name="Quick",
        description="Fast triage pass for large pasted lists.",
        badge="FAST",
        purpose="Minimal output with compact results and just enough clustering to spot repetition.",
        enabled={"duplicates"},
        section_order=["duplicates"],
        overview_metrics=["total_unique", "total_hits", "successful", "failed", "high_risk"],
        table_mode="compact",
        detail_mode="prompt",
        detail_prompt_default="n",
    ),
    "standard": ScanProfile(
        key="standard",
        name="Standard",
        description="Best all-around review mode.",
        badge="RECOMMENDED",
        purpose="Balanced output with overview cards, the main results matrix, and the most useful summaries.",
        enabled={"type_summary", "duplicates", "country_grouping", "asn_summary"},
        section_order=["type_summary", "duplicates", "country_grouping", "asn_summary"],
        overview_metrics=["total_unique", "total_hits", "successful", "failed", "high_risk", "tor_flagged", "country_count", "top_asn"],
        table_mode="standard",
        detail_mode="prompt",
        detail_prompt_default="n",
        show_high_risk_findings=True,
    ),
    "threat_hunter": ScanProfile(
        key="threat_hunter",
        name="Threat Hunter",
        description="Signal-focused review for suspicious infrastructure and clustering.",
        badge="DEEP",
        purpose="Prioritizes repeated infrastructure, ASN concentration, subnet overlap, provider repetition, and suspicious findings.",
        enabled={"type_summary", "duplicates", "country_grouping", "provider_summary", "asn_summary", "subnet_summary", "failed_lookup_summary"},
        section_order=["provider_summary", "asn_summary", "subnet_summary", "country_grouping", "duplicates", "failed_lookup_summary", "type_summary"],
        overview_metrics=["total_unique", "high_risk", "tor_flagged", "proxy_flagged", "hosting_flagged", "country_count", "top_asn", "top_subnet"],
        table_mode="standard",
        detail_mode="suspicious",
        show_high_risk_findings=True,
        show_failed_lookup_review=True,
    ),
    "analyst": ScanProfile(
        key="analyst",
        name="Analyst",
        description="Structured deep dive for human review.",
        badge="REVIEW",
        purpose="Expanded intelligence cards with clearer narratives around risk, ownership, reverse DNS, and failed lookups.",
        enabled={"type_summary", "duplicates", "country_grouping", "provider_summary", "asn_summary", "detailed_results", "failed_lookup_summary"},
        section_order=["type_summary", "provider_summary", "asn_summary", "country_grouping", "duplicates", "failed_lookup_summary", "detailed_results"],
        overview_metrics=["total_unique", "successful", "failed", "high_risk", "tor_flagged", "proxy_flagged", "hosting_flagged", "top_asn"],
        table_mode="expanded",
        detail_mode="all",
        show_high_risk_findings=True,
        show_failed_lookup_review=True,
    ),
    "insanity": ScanProfile(
        key="insanity",
        name="Insanity",
        description="Maximum visibility mode with every meaningful section enabled.",
        badge="MAX",
        purpose="Shows the full matrix, all clustering views, all details, and all failure diagnostics in a controlled staged layout.",
        enabled={item.key for item in OPTIONAL_ENRICHMENTS},
        section_order=["type_summary", "provider_summary", "asn_summary", "country_grouping", "subnet_summary", "duplicates", "failed_lookup_summary", "detailed_results"],
        overview_metrics=["total_unique", "total_hits", "successful", "failed", "high_risk", "tor_flagged", "proxy_flagged", "hosting_flagged", "country_count", "top_asn", "top_subnet"],
        table_mode="expanded",
        detail_mode="all",
        show_high_risk_findings=True,
        show_failed_lookup_review=True,
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
        badge="RECOMMENDED",
    ),
    "threat_signals": WorkflowPreset(
        key="threat_signals",
        name="Threat Signals",
        description="Suspicious infrastructure and clustering review.",
        default_profile_key="threat_hunter",
        badge="DEEP",
    ),
    "ownership_intel": WorkflowPreset(
        key="ownership_intel",
        name="Ownership Intel",
        description="Ownership-oriented deep review.",
        default_profile_key="analyst",
        badge="ADVANCED",
        availability_note="Uses the current core engine, but presents results in a more ownership-review oriented lens.",
    ),
    "full_investigation": WorkflowPreset(
        key="full_investigation",
        name="Full Investigation",
        description="Broadest current review path.",
        default_profile_key="insanity",
        badge="MAX",
        availability_note="Built on the same engine, but drives the broadest available presentation and grouping pass.",
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
            prefix = badge("RECOMMENDED", SUCCESS)
        elif preset.availability_note:
            prefix = badge(preset.badge or "ADVANCED", WARNING)
        else:
            prefix = badge(preset.badge or "ACTIVE", ACCENT)
        lines.append(f"{color(str(index), BOLD + ACCENT)}  {preset.name.ljust(18)} {prefix}  {preset.description}")

    lines.append(
        f"{color(str(len(WORKFLOW_MENU_ORDER) + 1), BOLD + ACCENT)}  Check intel updates  "
        f"{badge('MAINT', SUCCESS)}  Refresh keyword data from the remote feed"
    )
    lines.append(f"{color(str(len(WORKFLOW_MENU_ORDER) + 2), BOLD + ACCENT)}  Exit")
    return lines


def print_compact_message(text, tone=DIM + MUTED, indent=2):
    width = max(30, terminal_width() - indent - 2)
    wrapped = textwrap.wrap(text, width=width) or [""]
    for part in wrapped:
        print((" " * indent) + color(part, tone))


def print_workflow_preset_summary(workflow_preset):
    lines = [
        f"{color('Workflow', DIM + MUTED)} : {color(workflow_preset.name, BOLD + ACCENT)}  {badge(workflow_preset.badge or 'ACTIVE', ACCENT)}",
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
            f"{color('Profile', DIM + MUTED)} : {color(profile.name, BOLD + ACCENT)}  {badge(profile.badge or 'ACTIVE', SUCCESS)}",
            f"{color('Reason', DIM + MUTED)} : {profile.description}",
            f"{color('Purpose', DIM + MUTED)} : {profile.purpose or profile.description}",
        ],
        tone=ACCENT,
        width=min(ui_width(), 96),
    )


def choose_workflow_preset():
    print_step(1, WORKFLOW_PRESETS[DEFAULT_WORKFLOW_PRESET_KEY].step_total, "Choose workflow", "Pick the investigation posture you want before selecting input.")

    while True:
        header("MAIN MENU", "Choose an investigation lane or run an intel maintenance check.")

        for index, preset_key in enumerate(WORKFLOW_MENU_ORDER, start=1):
            preset = WORKFLOW_PRESETS[preset_key]
            tone = SUCCESS if preset.key == DEFAULT_WORKFLOW_PRESET_KEY else (WARNING if preset.availability_note else PRIMARY)
            print_option_panel(
                index=index,
                title=preset.name,
                badge_text=preset.badge or "ACTIVE",
                summary=preset.description,
                detail=f"Default profile: {SCAN_PROFILES[preset.default_profile_key].name}",
                note=preset.availability_note,
                tone=tone,
                width=min(ui_width(), 100),
            )

        print_option_panel(
            index=len(WORKFLOW_MENU_ORDER) + 1,
            title="Check Intel Updates",
            badge_text="MAINT",
            summary="Compare your local keyword bundle with the remote feed and optionally apply updates.",
            detail="Useful when public infra and provider knowledge has moved on.",
            tone=ACCENT,
            width=min(ui_width(), 100),
        )
        print_option_panel(
            index=len(WORKFLOW_MENU_ORDER) + 2,
            title="Exit",
            badge_text="QUIT",
            summary="Close the console.",
            tone=MUTED,
            width=min(ui_width(), 100),
        )

        choice = prompt(f"Choose a workflow [1-{len(WORKFLOW_MENU_ORDER) + 2}, Enter=1]: ")
        if not choice:
            choice = "1"

        if choice.isdigit():
            choice_number = int(choice)
            if 1 <= choice_number <= len(WORKFLOW_MENU_ORDER):
                workflow_preset = get_workflow_preset(WORKFLOW_MENU_ORDER[choice_number - 1])
                print_workflow_preset_summary(workflow_preset)
                return workflow_preset
            if choice_number == len(WORKFLOW_MENU_ORDER) + 1:
                run_intel_update_check()
                continue
            if choice_number == len(WORKFLOW_MENU_ORDER) + 2:
                sys.exit(0)

        print_notice("Invalid choice. Enter one of the listed workflow numbers.", WARNING)


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


SPECIAL_IP_FAILURES = [
    {
        "network": ipaddress.ip_network("10.0.0.0/8"),
        "category": "RFC1918 private IPv4",
        "detail": "Internal-use IPv4 space. It is not publicly routable, so public IP lookup services usually return no result.",
    },
    {
        "network": ipaddress.ip_network("172.16.0.0/12"),
        "category": "RFC1918 private IPv4",
        "detail": "Internal-use IPv4 space. It is not publicly routable, so public IP lookup services usually return no result.",
    },
    {
        "network": ipaddress.ip_network("192.168.0.0/16"),
        "category": "RFC1918 private IPv4",
        "detail": "Internal-use IPv4 space. It is not publicly routable, so public IP lookup services usually return no result.",
    },
    {
        "network": ipaddress.ip_network("100.64.0.0/10"),
        "category": "Carrier-grade NAT space",
        "detail": "Shared address space used by ISPs between customers and the public Internet. It is not globally routable.",
    },
    {
        "network": ipaddress.ip_network("169.254.0.0/16"),
        "category": "Link-local IPv4",
        "detail": "Auto-configured local-link address. It only works on the local network segment and is not Internet-routable.",
    },
    {
        "network": ipaddress.ip_network("127.0.0.0/8"),
        "category": "Loopback IPv4",
        "detail": "Points back to the local machine itself. It never appears as a public Internet source address.",
    },
    {
        "network": ipaddress.ip_network("224.0.0.0/4"),
        "category": "Multicast IPv4",
        "detail": "Reserved for multicast delivery rather than normal host assignment, so public IP ownership lookups do not apply.",
    },
    {
        "network": ipaddress.ip_network("240.0.0.0/4"),
        "category": "Reserved IPv4",
        "detail": "Reserved or future-use IPv4 space. These addresses are not generally assigned for public Internet hosts.",
    },
    {
        "network": ipaddress.ip_network("198.18.0.0/15"),
        "category": "Benchmark/testing IPv4",
        "detail": "Reserved for network benchmark tests. It is not used as normal public Internet address space.",
    },
    {
        "network": ipaddress.ip_network("192.0.2.0/24"),
        "category": "Documentation IPv4",
        "detail": "Reserved for examples and documentation. It is not assigned to public Internet hosts.",
    },
    {
        "network": ipaddress.ip_network("198.51.100.0/24"),
        "category": "Documentation IPv4",
        "detail": "Reserved for examples and documentation. It is not assigned to public Internet hosts.",
    },
    {
        "network": ipaddress.ip_network("203.0.113.0/24"),
        "category": "Documentation IPv4",
        "detail": "Reserved for examples and documentation. It is not assigned to public Internet hosts.",
    },
    {
        "network": ipaddress.ip_network("0.0.0.0/32"),
        "category": "Unspecified IPv4",
        "detail": "Special all-zero source/default address. It is not a routable host address.",
    },
    {
        "network": ipaddress.ip_network("fc00::/7"),
        "category": "Unique local IPv6",
        "detail": "Private-use IPv6 space for internal networks. It is not publicly routable.",
    },
    {
        "network": ipaddress.ip_network("fe80::/10"),
        "category": "Link-local IPv6",
        "detail": "Local-link IPv6 space used only on the current network segment. It is not Internet-routable.",
    },
    {
        "network": ipaddress.ip_network("::1/128"),
        "category": "Loopback IPv6",
        "detail": "Points back to the local machine itself. It never appears as a public Internet source address.",
    },
    {
        "network": ipaddress.ip_network("ff00::/8"),
        "category": "Multicast IPv6",
        "detail": "Reserved for multicast delivery rather than normal host assignment, so public IP ownership lookups do not apply.",
    },
    {
        "network": ipaddress.ip_network("2001:db8::/32"),
        "category": "Documentation IPv6",
        "detail": "Reserved for examples and documentation. It is not assigned to public Internet hosts.",
    },
    {
        "network": ipaddress.ip_network("::/128"),
        "category": "Unspecified IPv6",
        "detail": "Special all-zero source/default address. It is not a routable host address.",
    },
]


def describe_lookup_failure(ip, api_message=""):
    parsed = parse_ip_token(ip)
    api_message = (api_message or "").strip()

    if parsed is None:
        return {
            "failure_category": "Invalid IP",
            "failure_range": "",
            "failure_detail": "The value could not be parsed as a valid IPv4 or IPv6 address.",
        }

    for entry in SPECIAL_IP_FAILURES:
        if parsed in entry["network"]:
            return {
                "failure_category": entry["category"],
                "failure_range": str(entry["network"]),
                "failure_detail": entry["detail"],
            }

    if parsed.is_private:
        return {
            "failure_category": "Private-use address",
            "failure_range": "",
            "failure_detail": "This address is not globally routable, so public IP lookup services usually return no result.",
        }

    if parsed.is_reserved:
        return {
            "failure_category": "Reserved address space",
            "failure_range": "",
            "failure_detail": "This address is part of reserved address space and is not normally assigned as a public Internet host.",
        }

    if parsed.is_loopback:
        return {
            "failure_category": "Loopback address",
            "failure_range": "",
            "failure_detail": "This address points back to the local machine and is never a public Internet host address.",
        }

    if parsed.is_link_local:
        return {
            "failure_category": "Link-local address",
            "failure_range": "",
            "failure_detail": "This address only works on the local network segment and is not Internet-routable.",
        }

    if parsed.is_multicast:
        return {
            "failure_category": "Multicast address",
            "failure_range": "",
            "failure_detail": "This address is reserved for multicast traffic, not normal public host assignment.",
        }

    if parsed.is_unspecified:
        return {
            "failure_category": "Unspecified address",
            "failure_range": "",
            "failure_detail": "This is a special placeholder/default address, not a usable public host address.",
        }

    failure_detail = "The remote lookup service did not return usable public network metadata for this address."
    if api_message:
        failure_detail += f" Remote reason: {api_message}."

    return {
        "failure_category": "Lookup returned no public data",
        "failure_range": "",
        "failure_detail": failure_detail,
    }


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

    if any(word in asname_field for word in HOSTING_LIKE_TERMS):
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
    status = item.get("status", "")
    if status == "success":
        failure_info = {
            "failure_category": "",
            "failure_range": "",
            "failure_detail": "",
        }
    else:
        failure_info = describe_lookup_failure(query, item.get("message", ""))
    record = IPResultRecord(
        query=query,
        count=counts.get(query, 1),
        status=status,
        message=item.get("message", ""),
        failure_category=failure_info["failure_category"],
        failure_range=failure_info["failure_range"],
        failure_detail=failure_info["failure_detail"],
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


def format_failure_summary(item):
    category = item.get("failure_category", "") or ""
    failure_range = item.get("failure_range", "") or ""

    if category and failure_range:
        return f"{category} ({failure_range})"
    if category:
        return category
    return item.get("message", "Unknown error") or "Unknown error"


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
                safe(format_failure_summary(item), columns[3]["width"]),
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
            if item.get("failure_category"):
                lines.extend(wrap_label_value("Class", item.get("failure_category"), width))
            if item.get("failure_range"):
                lines.extend(wrap_label_value("Range", item.get("failure_range"), width))
            if item.get("failure_detail"):
                lines.extend(wrap_label_value("Why", item.get("failure_detail"), width))
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


def summarize_provider_rows(results, counts):
    summary = defaultdict(lambda: {"unique": 0, "hits": 0, "top_flag": "NONE"})
    priority = {"VERY HIGH": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "NONE": 0}

    for item in results:
        if item.get("status") != "success":
            continue

        provider = format_provider(item)
        if not provider or provider == "N/A":
            continue

        flag, _, _ = suspicion_score(item)
        summary[provider]["unique"] += 1
        summary[provider]["hits"] += counts.get(item.get("query", ""), 1)
        if priority[flag] > priority[summary[provider]["top_flag"]]:
            summary[provider]["top_flag"] = flag

    ranked = sorted(summary.items(), key=lambda entry: (entry[1]["hits"], entry[1]["unique"]), reverse=True)
    return [(label, data) for label, data in ranked if data["unique"] > 1 or data["hits"] > 1]


def summarize_failed_lookup_rows(results, counts):
    summary = defaultdict(lambda: {"unique": 0, "hits": 0})

    for item in results:
        if item.get("status") == "success":
            continue

        key = (
            item.get("failure_category", "") or "Lookup failure",
            item.get("failure_range", "") or "-",
        )
        summary[key]["unique"] += 1
        summary[key]["hits"] += counts.get(item.get("query", ""), 1)

    ranked = sorted(summary.items(), key=lambda entry: (entry[1]["hits"], entry[1]["unique"]), reverse=True)
    return ranked


def collect_result_stats(results, counts, invalid_ips=None):
    successful = [item for item in results if item.get("status") == "success"]
    failed = [item for item in results if item.get("status") != "success"]
    high_risk_items = []
    tor_flagged = 0
    proxy_flagged = 0
    hosting_flagged = 0
    mobile_flagged = 0
    countries = set()

    for item in successful:
        flag, _, _ = suspicion_score(item)
        if flag in ("VERY HIGH", "HIGH"):
            high_risk_items.append(item)
        if item.get("tor_exit"):
            tor_flagged += 1
        if item.get("proxy"):
            proxy_flagged += 1
        if item.get("hosting"):
            hosting_flagged += 1
        if item.get("mobile"):
            mobile_flagged += 1
        if item.get("country"):
            countries.add(item.get("country"))

    asn_rows = summarize_asn_rows(results, counts)
    subnet_rows = summarize_subnet_rows(results, counts)
    provider_rows = summarize_provider_rows(results, counts)

    return {
        "total_unique": len(results),
        "total_hits": sum(counts.values()),
        "successful": len(successful),
        "failed": len(failed),
        "high_risk": len(high_risk_items),
        "tor_flagged": tor_flagged,
        "proxy_flagged": proxy_flagged,
        "hosting_flagged": hosting_flagged,
        "mobile_flagged": mobile_flagged,
        "country_count": len(countries),
        "invalid_count": len(invalid_ips or []),
        "top_asn": asn_rows[0][0] if asn_rows else "N/A",
        "top_subnet": subnet_rows[0][0] if subnet_rows else "N/A",
        "top_provider": provider_rows[0][0] if provider_rows else "N/A",
        "high_risk_items": high_risk_items,
        "failed_items": failed,
    }


def metric_card(metric_key, stats):
    mapping = {
        "total_unique": ("Unique IPs", stats["total_unique"], "deduplicated scan set", ACCENT),
        "total_hits": ("Total Hits", stats["total_hits"], "including repeats", ACCENT),
        "successful": ("Resolved", stats["successful"], "public lookups completed", SUCCESS),
        "failed": ("Failures", stats["failed"], "no public metadata", WARNING if stats["failed"] else SUCCESS),
        "high_risk": ("High Risk", stats["high_risk"], "very high + high", DANGER if stats["high_risk"] else SUCCESS),
        "tor_flagged": ("Tor", stats["tor_flagged"], "exit nodes matched", MAGENTA if stats["tor_flagged"] else SUCCESS),
        "proxy_flagged": ("Proxy", stats["proxy_flagged"], "proxy flag true", DANGER if stats["proxy_flagged"] else SUCCESS),
        "hosting_flagged": ("Hosting", stats["hosting_flagged"], "hosting flag true", WARNING if stats["hosting_flagged"] else SUCCESS),
        "mobile_flagged": ("Mobile", stats["mobile_flagged"], "mobile flag true", BLUE if stats["mobile_flagged"] else SUCCESS),
        "country_count": ("Countries", stats["country_count"], "distinct geo buckets", ACCENT),
        "top_asn": ("Top ASN", safe(stats["top_asn"], 24), "most repeated network", ACCENT),
        "top_subnet": ("Top Subnet", format_subnet_display(stats["top_subnet"], 22), "highest repeated prefix", ACCENT),
        "top_provider": ("Top Provider", safe(stats["top_provider"], 24), "most repeated provider", ACCENT),
        "invalid_count": ("Invalid", stats["invalid_count"], "ignored input entries", WARNING if stats["invalid_count"] else SUCCESS),
    }
    return mapping.get(metric_key)


def format_signal_tags(item, compact=False):
    tags = []
    if item.get("tor_exit"):
        tags.append(("TOR", MAGENTA))
    if item.get("proxy"):
        tags.append(("PRX", DANGER))
    if item.get("hosting"):
        tags.append(("HST", WARNING))
    if item.get("mobile"):
        tags.append(("MOB", BLUE))

    if not tags:
        return "CLEAR" if compact else color("No notable transport flags", DIM + MUTED)

    if compact:
        return "/".join(label for label, _ in tags)
    return " ".join(badge(label, tone) for label, tone in tags)


def compact_detail_text(item):
    if item.get("status") != "success":
        return format_failure_summary(item)
    return safe(format_provider(item), 26)


def build_results_table_columns(profile):
    if profile.table_mode == "compact":
        columns = [
            {"title": "IP", "width": 28, "min_width": 18},
            {"title": "Hits", "width": 4, "min_width": 4, "align": "right"},
            {"title": "Location", "width": 20, "min_width": 12},
            {"title": "Signals", "width": 11, "min_width": 8},
            {"title": "Risk", "width": 10, "min_width": 8},
            {"title": "Type", "width": 18, "min_width": 12},
        ]
    elif profile.table_mode == "expanded" and ui_width() >= 118:
        columns = [
            {"title": "IP", "width": 28, "min_width": 18},
            {"title": "Hits", "width": 4, "min_width": 4, "align": "right"},
            {"title": "Location", "width": 18, "min_width": 12},
            {"title": "Network", "width": 22, "min_width": 16},
            {"title": "Provider", "width": 22, "min_width": 16},
            {"title": "Signals", "width": 11, "min_width": 8},
            {"title": "Risk", "width": 10, "min_width": 8},
            {"title": "Type", "width": 18, "min_width": 12},
        ]
    else:
        columns = [
            {"title": "IP", "width": 28, "min_width": 18},
            {"title": "Hits", "width": 4, "min_width": 4, "align": "right"},
            {"title": "Location", "width": 20, "min_width": 12},
            {"title": "Provider", "width": 24, "min_width": 16},
            {"title": "Signals", "width": 11, "min_width": 8},
            {"title": "Score", "width": 5, "min_width": 5, "align": "right"},
            {"title": "Risk", "width": 10, "min_width": 8},
            {"title": "Type", "width": 18, "min_width": 12},
        ]

    fitted = fit_column_widths(columns, max_total=ui_width(124))
    for column, width in zip(columns, fitted):
        column["width"] = width
    return columns


def print_input_summary(valid_ips, invalid_ips, counts):
    header("VALIDATION SUMMARY", "Input was normalized, deduplicated, and prepared for enrichment.")
    cards = [
        ("Unique IPs", len(valid_ips), "validated", SUCCESS),
        ("Total Hits", sum(counts.values()), "including repeats", ACCENT),
        ("Invalid", len(invalid_ips), "ignored entries", WARNING if invalid_ips else SUCCESS),
        ("Address Mix", f"v4/v6", f"{sum(1 for ip in valid_ips if detect_ip_version(ip) == 4)}/{sum(1 for ip in valid_ips if detect_ip_version(ip) == 6)}", ACCENT),
    ]
    print_stat_cards(cards, preferred_width=25)
    print_box(
        "Prepared Input",
        [
            "The scan will use deduplicated addresses for lookup and preserve repeat counts for summaries and export.",
            "Private, reserved, and local-only ranges are accepted and explained separately if public metadata cannot be resolved.",
        ],
        tone=ACCENT,
        width=min(ui_width(), 108),
    )


def print_result_overview(results, counts, profile, invalid_ips=None):
    stats = collect_result_stats(results, counts, invalid_ips=invalid_ips)
    header("EXECUTIVE OVERVIEW", "High-signal metrics before the heavier matrices and clustering sections.")

    cards = [metric_card(key, stats) for key in profile.overview_metrics]
    cards = [card for card in cards if card is not None]
    print_stat_cards(cards, preferred_width=24)

    narrative = [
        f"{badge(profile.name, ACCENT)} {profile.description}",
        f"Top provider cluster: {safe(stats['top_provider'], 56)}",
        f"Top network cluster: {safe(stats['top_asn'], 56)}",
    ]
    print_box("Review Posture", narrative, tone=PRIMARY, width=min(ui_width(), 108))


def print_high_risk_findings(results, counts, profile, limit=None):
    risk_items = [item for item in results if item.get("status") == "success" and suspicion_score(item)[0] in ("VERY HIGH", "HIGH")]
    if not risk_items:
        return

    limit = limit or (12 if profile.key == "insanity" else 8)
    header("HIGH RISK FINDINGS", "Prioritized entries with the strongest signal combination.")
    columns = [
        {"title": "IP", "width": 28, "min_width": 18},
        {"title": "Hits", "width": 4, "min_width": 4, "align": "right"},
        {"title": "Signals", "width": 11, "min_width": 8},
        {"title": "Provider", "width": 28, "min_width": 16},
        {"title": "Risk", "width": 10, "min_width": 8},
        {"title": "Reasons", "width": 28, "min_width": 18},
    ]
    fitted = fit_column_widths(columns, max_total=ui_width(124))
    for column, width in zip(columns, fitted):
        column["width"] = width

    rows = []
    for item in risk_items[:limit]:
        flag, reasons, _ = suspicion_score(item)
        rows.append([
            color(format_ip_display(item.get("query", "N/A"), columns[0]["width"]), BOLD + suspicion_color(flag)),
            str(counts.get(item.get("query", ""), 1)),
            color(format_signal_tags(item, compact=True), signal_tone(item)),
            safe(format_provider(item), columns[3]["width"]),
            color(flag, BOLD + suspicion_color(flag)),
            safe(", ".join(reasons), columns[5]["width"]),
        ])

    render_table(columns, rows, tone=DANGER)
    if len(risk_items) > limit:
        print_notice(f"Showing top {limit} of {len(risk_items)} high-risk findings.", MUTED)


def print_results_table(results, counts, profile):
    header("FULL RESULTS MATRIX", "Sorted by suspicion first with profile-aware density and cleaner signal hierarchy.")
    columns = build_results_table_columns(profile)
    titles = [column["title"] for column in columns]
    rows = []

    for item in results:
        ip = item.get("query", "N/A")
        hits = str(counts.get(ip, 1))

        if item.get("status") != "success":
            base = {
                "IP": color(format_ip_display(ip, next(column["width"] for column in columns if column["title"] == "IP")), BOLD + DANGER),
                "Hits": hits,
                "Location": color("Lookup failed", DANGER),
                "Network": color("-", DIM + MUTED),
                "Provider": safe(format_failure_summary(item), next(column["width"] for column in columns if column["title"] in {"Provider", "Network"})),
                "Signals": color("-", DIM + MUTED),
                "Score": color("-", DIM + MUTED),
                "Risk": color("FAILED", BOLD + DANGER),
                "Type": color("Lookup Failed", DANGER),
            }
            if "Provider" not in titles and "Network" not in titles:
                base["Location"] = safe(format_failure_summary(item), next(column["width"] for column in columns if column["title"] == "Location"))
            rows.append([base[title] for title in titles])
            continue

        flag, _, score = suspicion_score(item)
        ip_type = likely_type(item)
        base = {
            "IP": color(format_ip_display(ip, next(column["width"] for column in columns if column["title"] == "IP")), BOLD + suspicion_color(flag) if flag in ("VERY HIGH", "HIGH") else BOLD),
            "Hits": hits,
            "Location": safe(format_location(item), next(column["width"] for column in columns if column["title"] == "Location")),
            "Network": safe(format_network(item), next((column["width"] for column in columns if column["title"] == "Network"), 18)),
            "Provider": safe(format_provider(item), next((column["width"] for column in columns if column["title"] == "Provider"), 24)),
            "Signals": color(format_signal_tags(item, compact=True), signal_tone(item)),
            "Score": format_score(score),
            "Risk": color(flag, BOLD + suspicion_color(flag)),
            "Type": color(safe(ip_type, next((column["width"] for column in columns if column["title"] == "Type"), 18)), type_tone(ip_type)),
        }
        rows.append([base[title] for title in titles])

    render_table(columns, rows, tone=PRIMARY)


def print_detailed_results(results, counts, profile=None):
    header("DETAILED INTELLIGENCE", "Expanded per-IP cards with a calmer layout and stronger hierarchy.")
    width = min(ui_width(110), 110)

    if profile and profile.detail_mode == "suspicious":
        filtered = [
            item for item in results
            if item.get("status") != "success" or suspicion_score(item)[0] in ("VERY HIGH", "HIGH", "MEDIUM")
        ]
    else:
        filtered = list(results)

    for item in filtered:
        ip = item.get("query", "N/A")
        seen = counts.get(ip, 1)

        if item.get("status") != "success":
            lines = [
                f"{badge('FAILED', DANGER)} {badge(item.get('failure_category', 'LOOKUP'), WARNING)}",
                "",
                f"{color('Remote', DIM + MUTED)} : {item.get('message', 'Unknown error')}",
            ]
            if item.get("failure_range"):
                lines.append(f"{color('Range', DIM + MUTED)} : {item.get('failure_range')}")
            if item.get("failure_detail"):
                lines.extend(wrap_label_value("Why", item.get("failure_detail"), width))
            print_box(detailed_box_title(ip, seen, width), lines, tone=DANGER, width=width)
            continue

        flag, reasons, score = suspicion_score(item)
        lines = [
            f"{badge(flag, suspicion_color(flag))} {badge(likely_type(item), type_tone(likely_type(item)))} {format_signal_tags(item)}",
            "",
        ]
        lines.extend(wrap_label_value("Location", format_detailed_location(item), width))
        lines.extend(wrap_label_value("Provider", format_provider(item), width))

        network_text = format_network(item)
        if network_text != "N/A":
            lines.extend(wrap_label_value("Network", network_text, width))

        if has_positive_reverse_dns(item):
            lines.extend(wrap_label_value("rDNS", format_reverse_dns(item), width))

        if has_interesting_tor_state(item):
            lines.extend(wrap_label_value("Tor", format_tor_status(item), width, MAGENTA if item.get("tor_exit") else None))

        lines.extend(wrap_label_value("Score", f"{score} points", width, suspicion_color(flag)))
        lines.extend(wrap_label_value("Reasons", ", ".join(reasons) if reasons else "None", width))

        print_box(detailed_box_title(ip, seen, width), lines, tone=suspicion_color(flag), width=width)


def print_country_grouping(results, counts):
    groups = summarize_country_groups(results, counts)
    if not groups:
        return

    header("COUNTRY AND REGION CLUSTERING", "Only repeated geographies are shown so the section stays investigative, not noisy.")

    for country, items, total_hits in groups:
        print_box(
            country,
            [
                f"{color('Unique IPs', DIM + MUTED)} : {len(items)}",
                f"{color('Total Hits', DIM + MUTED)} : {total_hits}",
            ],
            tone=ACCENT,
            width=min(ui_width(), 80),
        )

        columns = [
            {"title": "IP", "width": 28, "min_width": 18},
            {"title": "City", "width": 18, "min_width": 12},
            {"title": "Provider", "width": 26, "min_width": 16},
            {"title": "Risk", "width": 10, "min_width": 8},
            {"title": "Type", "width": 18, "min_width": 12},
        ]
        fitted = fit_column_widths(columns, max_total=ui_width(116))
        for column, width in zip(columns, fitted):
            column["width"] = width

        rows = []
        for item in items:
            flag, _, _ = suspicion_score(item)
            ip_type = likely_type(item)
            rows.append([
                format_ip_display(item.get("query", "N/A"), columns[0]["width"]),
                safe(item.get("city", "N/A"), columns[1]["width"]),
                safe(format_provider(item), columns[2]["width"]),
                color(flag, BOLD + suspicion_color(flag)),
                color(safe(ip_type, columns[4]["width"]), type_tone(ip_type)),
            ])

        render_table(columns, rows, tone=ACCENT)


def print_duplicates(counts):
    duplicates = summarize_duplicates(counts)
    if not duplicates:
        return

    header("DUPLICATE HIT REVIEW", "Repeated addresses are surfaced here so reuse is visible immediately.")
    duplicates.sort(key=lambda x: x[1], reverse=True)
    columns = [
        {"title": "IP", "width": 28, "min_width": 18},
        {"title": "Seen", "width": 6, "min_width": 6, "align": "right"},
    ]
    rows = [[format_ip_display(ip, columns[0]["width"]), color(str(count), BOLD + ACCENT)] for ip, count in duplicates]
    render_table(columns, rows, tone=ACCENT)


def print_invalid(invalid):
    if not invalid:
        return

    header("INVALID AND SKIPPED INPUT", "These values were ignored before lookup because they did not parse as valid IP addresses.")
    wrapped = textwrap.wrap(", ".join(invalid), width=max(30, min(ui_width(), 108) - 8))
    print_box("Skipped Entries", [color(line, WARNING) for line in wrapped], tone=WARNING, width=min(ui_width(), 108))


def print_type_summary(results, counts):
    header("TYPE DISTRIBUTION", "Classification rollup by unique addresses and observed hit volume.")

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
        {"title": "Type", "width": 24, "min_width": 16},
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


def print_provider_summary(results, counts, limit=10):
    ranked = summarize_provider_rows(results, counts)
    if not ranked:
        return

    header("NETWORK OWNERSHIP PATTERNS", "Provider repetition can reveal infrastructure concentration even before deep attribution.")
    columns = [
        {"title": "Provider", "width": 42, "min_width": 22},
        {"title": "Unique", "width": 6, "min_width": 6, "align": "right"},
        {"title": "Hits", "width": 6, "min_width": 6, "align": "right"},
        {"title": "Top Risk", "width": 10, "min_width": 8},
    ]
    fitted = fit_column_widths(columns, max_total=ui_width(118))
    for column, width in zip(columns, fitted):
        column["width"] = width

    rows = []
    for label, data in ranked[:limit]:
        rows.append([
            safe(label, columns[0]["width"]),
            color(str(data["unique"]), BOLD + ACCENT),
            color(str(data["hits"]), BOLD + ACCENT),
            color(data["top_flag"], BOLD + suspicion_color(data["top_flag"])),
        ])
    render_table(columns, rows, tone=ACCENT)


def print_asn_summary(results, counts, limit=10):
    ranked = summarize_asn_rows(results, counts)
    if not ranked:
        return

    header("ASN CLUSTERING", "Repeated or clustered networks are ranked by hit concentration.")
    columns = [
        {"title": "ASN / Name", "width": 44, "min_width": 24},
        {"title": "Unique", "width": 6, "min_width": 6, "align": "right"},
        {"title": "Hits", "width": 6, "min_width": 6, "align": "right"},
    ]
    fitted = fit_column_widths(columns, max_total=ui_width(118))
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


def print_subnet_summary(results, counts, limit=10):
    ranked = summarize_subnet_rows(results, counts)
    if not ranked:
        return

    header("SUBNET CLUSTERING", "Repeated IPv4 /24 and IPv6 /64 ranges often reveal operational grouping.")
    columns = [
        {"title": "Subnet", "width": 43, "min_width": 18},
        {"title": "Unique", "width": 6, "min_width": 6, "align": "right"},
        {"title": "Hits", "width": 6, "min_width": 6, "align": "right"},
    ]
    fitted = fit_column_widths(columns, max_total=ui_width(118))
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


def print_failed_lookup_summary(results, counts, limit=12):
    ranked = summarize_failed_lookup_rows(results, counts)
    if not ranked:
        return

    header("FAILED LOOKUP REVIEW", "Structured reasons for addresses that did not return public metadata.")
    columns = [
        {"title": "Class", "width": 24, "min_width": 16},
        {"title": "Range", "width": 24, "min_width": 12},
        {"title": "Unique", "width": 6, "min_width": 6, "align": "right"},
        {"title": "Hits", "width": 6, "min_width": 6, "align": "right"},
    ]
    fitted = fit_column_widths(columns, max_total=ui_width(112))
    for column, width in zip(columns, fitted):
        column["width"] = width

    rows = []
    for (failure_class, failure_range), data in ranked[:limit]:
        rows.append([
            safe(failure_class, columns[0]["width"]),
            format_subnet_display(failure_range, columns[1]["width"]),
            color(str(data["unique"]), BOLD + ACCENT),
            color(str(data["hits"]), BOLD + ACCENT),
        ])
    render_table(columns, rows, tone=WARNING)


# ==================================================
# Enrichment Routing
# ==================================================


ENRICHMENT_RENDERERS = {
    "type_summary": print_type_summary,
    "duplicates": lambda results, counts: print_duplicates(counts),
    "country_grouping": print_country_grouping,
    "provider_summary": print_provider_summary,
    "asn_summary": print_asn_summary,
    "subnet_summary": print_subnet_summary,
    "detailed_results": lambda results, counts, profile=None: print_detailed_results(results, counts, profile),
    "failed_lookup_summary": print_failed_lookup_summary,
}


def render_enabled_enrichments(results, counts, profile):
    ordered = profile.section_order or [item.key for item in OPTIONAL_ENRICHMENTS]
    for key in ordered:
        if key == "detailed_results":
            continue
        if profile.is_enabled(key):
            renderer = ENRICHMENT_RENDERERS.get(key)
            if renderer:
                renderer(results, counts)


def render_detailed_results_if_enabled(results, counts, profile):
    if profile.detail_mode == "none":
        return
    if profile.detail_mode == "prompt" or profile.prompt_for_details:
        if ask_yes_no("Open detailed intelligence cards too?", default=profile.detail_prompt_default):
            print_detailed_results(results, counts, profile)
        return
    if profile.is_enabled("detailed_results") or profile.detail_mode in {"suspicious", "all"}:
        print_detailed_results(results, counts, profile)


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
            "FailureClass",
            "FailureRange",
            "FailureWhy",
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
                item.get("failure_category", ""),
                item.get("failure_range", ""),
                item.get("failure_detail", ""),
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
    header("EXPORT STAGE", "Persist the current review to disk if you want a shareable or machine-readable artifact.")
    if ask_yes_no("Save results to CSV?", default="n"):
        filename = prompt("Enter filename [ip_results.csv]: ")
        if not filename:
            filename = "ip_results.csv"
        save_to_csv(results, counts, filename)
        print_notice(f"Saved CSV to {filename}", SUCCESS)

    if ask_yes_no("Save results to JSON too?", default="n"):
        filename = prompt("Enter filename [ip_results.json]: ")
        if not filename:
            filename = "ip_results.json"
        save_to_json(results, counts, filename)
        print_notice(f"Saved JSON to {filename}", SUCCESS)


# ==================================================
# Input Sources
# ==================================================


def read_from_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def read_from_paste():
    header("PASTE CONSOLE", "Drop IPv4 and IPv6 entries directly into the buffer, then launch the scan when ready.")
    print_box(
        "Paste Mode",
        [
            f"{badge('/START', SUCCESS)} begin lookup using the pasted buffer",
            f"{badge('/CLEAR', WARNING)} clear the current buffer",
            f"{badge('/CANCEL', WARNING)} return to input selection",
            f"{badge('/HELP', PRIMARY)} reopen the guide",
        ],
        tone=ACCENT,
        width=min(ui_width(), 92),
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
            print_notice("Nothing pasted yet.", WARNING)
            continue

        if command == "/clear":
            lines.clear()
            print_notice("Pasted input cleared.", WARNING)
            continue

        if command == "/cancel":
            print_notice("Paste mode cancelled.", WARNING)
            return None

        if command == "/help":
            show_help()
            continue

        lines.append(line)

    return "\n".join(lines)


def choose_input(workflow_preset):
    print_step(2, workflow_preset.step_total, "Choose input source", "Select the intake path for the current investigation.")

    while True:
        print_box(
            "Input Source",
            [
                f"{badge('ENTER', SUCCESS)} Paste addresses directly into a live intake buffer",
                f"{badge('F', ACCENT)} Load IPs from an existing text file",
                f"{badge('Q', WARNING)} Exit the console",
            ],
            tone=PRIMARY,
            width=min(ui_width(), 88),
        )

        choice = prompt("Input source [Enter/F/Q]").lower()

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
                print_notice("File not found.", DANGER)
            except Exception as e:
                print_notice(f"Failed to read file: {e}", DANGER)
            continue
        if choice in {"q", "quit", "exit"}:
            sys.exit(0)
        print_notice("Use Enter for paste mode, F for file input, or Q to exit.", WARNING)


# ==================================================
# Profile Selection
# ==================================================


def enabled_enrichment_labels(profile):
    labels = []
    for item in OPTIONAL_ENRICHMENTS:
        if profile.is_enabled(item.key):
            labels.append(item.label)
    return labels


PROFILE_MENU_ORDER = ["quick", "standard", "threat_hunter", "analyst", "insanity", "custom"]


def print_scan_profile_summary(profile):
    enabled_labels = ", ".join(enabled_enrichment_labels(profile)) or "None selected"
    print_box(
        "Scan Profile",
        [
            f"{color('Selected', DIM + MUTED)} : {color(profile.name, BOLD + ACCENT)}  {badge(profile.badge or 'ACTIVE', ACCENT)}",
            f"{color('Mode', DIM + MUTED)} : {profile.description}",
            f"{color('Purpose', DIM + MUTED)} : {profile.purpose or profile.description}",
            f"{color('Density', DIM + MUTED)} : {profile.table_mode} table | detail mode {profile.detail_mode}",
            f"{color('Enabled', DIM + MUTED)} : {enabled_labels}",
        ],
        tone=ACCENT,
        width=min(ui_width(), 100),
    )


def render_custom_option_list(enabled):
    lines = []
    for index, item in enumerate(OPTIONAL_ENRICHMENTS, start=1):
        marker = color("[x]", SUCCESS) if item.key in enabled else color("[ ]", DIM + MUTED)
        lines.append(f"{marker} {color(str(index), BOLD + ACCENT)}  {item.label.ljust(20)} {muted(item.description)}")
    return lines


def build_custom_scan_profile():
    header("CUSTOM PROFILE", "Toggle enrichments with a compact checklist, then confirm the final review mode.")

    defaults = set(SCAN_PROFILES["standard"].enabled)
    enabled = set(defaults)

    while True:
        print_box(
            "Custom Options",
            render_custom_option_list(enabled) + [
                "",
                f"{badge('A', ACCENT)} enable all   {badge('N', ACCENT)} clear all   {badge('D', SUCCESS)} done   {badge('Q', WARNING)} exit",
                "Enter one or more numbers separated by spaces or commas to toggle specific sections.",
            ],
            tone=ACCENT,
            width=min(ui_width(), 108),
        )

        choice = prompt("Custom selection [numbers/A/N/D/Q]").lower().replace(",", " ").split()
        if not choice:
            continue

        if choice == ["a"]:
            enabled = {item.key for item in OPTIONAL_ENRICHMENTS}
            continue
        if choice == ["n"]:
            enabled.clear()
            continue
        if choice == ["q"]:
            sys.exit(0)
        if choice == ["d"]:
            break

        changed = False
        for token in choice:
            if token.isdigit():
                index = int(token)
                if 1 <= index <= len(OPTIONAL_ENRICHMENTS):
                    key = OPTIONAL_ENRICHMENTS[index - 1].key
                    if key in enabled:
                        enabled.remove(key)
                    else:
                        enabled.add(key)
                    changed = True
        if not changed:
            print_notice("Enter valid option numbers, A, N, D, or Q.", WARNING)

    profile = ScanProfile(
        key="custom",
        name="Custom",
        description="Manual expert control over summaries and detail sections.",
        badge="CUSTOM",
        purpose="Lets you build a scan view section by section without touching the lookup pipeline.",
        enabled=enabled,
        section_order=[item.key for item in OPTIONAL_ENRICHMENTS if item.key in enabled and item.key != "detailed_results"] + (["detailed_results"] if "detailed_results" in enabled else []),
        overview_metrics=list(SCAN_PROFILES["standard"].overview_metrics),
        table_mode="standard",
        detail_mode="all" if "detailed_results" in enabled else "prompt",
        detail_prompt_default="n",
        show_high_risk_findings=True,
        show_failed_lookup_review="failed_lookup_summary" in enabled,
    )
    print_scan_profile_summary(profile)
    return profile


def print_profile_catalog(default_choice):
    header("SCAN PROFILES", "Each profile changes density, section order, and how much intelligence is surfaced.")
    for index, profile_key in enumerate(PROFILE_MENU_ORDER[:-1], start=1):
        profile = SCAN_PROFILES[profile_key]
        note = f"Default for this workflow" if str(index) == default_choice else ""
        print_option_panel(
            index=index,
            title=profile.name,
            badge_text=profile.badge or "ACTIVE",
            summary=profile.description,
            detail=profile.purpose,
            note=note,
            tone=SUCCESS if str(index) == default_choice else PRIMARY,
            width=min(ui_width(), 102),
        )

    print_option_panel(
        index=len(PROFILE_MENU_ORDER),
        title="Custom",
        badge_text="CUSTOM",
        summary="Manual expert control over individual sections.",
        detail="Toggle enrichments directly, then review the final configuration before the scan starts.",
        tone=ACCENT,
        width=min(ui_width(), 102),
    )
    print_option_panel(
        index=len(PROFILE_MENU_ORDER) + 1,
        title="Exit",
        badge_text="QUIT",
        summary="Leave the console.",
        tone=MUTED,
        width=min(ui_width(), 102),
    )


def choose_scan_profile(workflow_preset, show_step=True):
    if show_step:
        print_step(4, workflow_preset.step_total, "Choose scan profile", "Pick the review density that matches how much context you want on screen.")

    default_choices = {
        "quick": "1",
        "standard": "2",
        "threat_hunter": "3",
        "analyst": "4",
        "insanity": "5",
    }
    default_choice = default_choices.get(workflow_preset.default_profile_key, "2")

    while True:
        print_profile_catalog(default_choice)

        choice = prompt(f"Choose a profile [1-{len(PROFILE_MENU_ORDER) + 1}, Enter={default_choice}]")
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
            profile = get_scan_profile("threat_hunter")
            print_scan_profile_summary(profile)
            return profile
        if choice == "4":
            profile = get_scan_profile("analyst")
            print_scan_profile_summary(profile)
            return profile
        if choice == "5":
            profile = get_scan_profile("insanity")
            print_scan_profile_summary(profile)
            return profile
        if choice == "6":
            profile = build_custom_scan_profile()
            return profile
        if choice == "7":
            sys.exit(0)

        print_notice("Invalid choice. Enter one of the listed profile numbers.", WARNING)


def choose_scan_setup(workflow_preset):
    print_step(4, workflow_preset.step_total, "Confirm scan setup", "Use the recommended profile unless you want a different review density.")
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
    print_result_overview(results, counts, profile, invalid_ips=invalid_ips)

    if profile.key == "insanity":
        header("INSANITY MODE", "All meaningful views are enabled, but grouped into deliberate stages instead of a raw dump.")

    if profile.show_high_risk_findings:
        print_high_risk_findings(results, counts, profile)

    print_results_table(results, counts, profile)
    render_enabled_enrichments(results, counts, profile)
    render_detailed_results_if_enabled(results, counts, profile)

    if profile.show_invalid_entries:
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
        "Run live intelligence pipeline",
        (
            f"Using {profile.name} under {workflow_preset.name}. "
            f"Submitting {len(parsed_input.valid_ips)} unique IP"
            f"{'s' if len(parsed_input.valid_ips) != 1 else ''} to the batch API."
        ),
    )
    raw_results = run_with_spinner("Submitting batch geolocation lookups...", lookup_ips, parsed_input.valid_ips)
    results = hydrate_result_records(raw_results, parsed_input.counts)
    results = run_with_spinner("Resolving reverse DNS context...", enrich_records_with_reverse_dns, results)
    results = run_with_spinner("Checking Tor exit intelligence...", enrich_records_with_tor_signal, results)
    results = sort_results(results, parsed_input.counts)

    print_step(
        6,
        workflow_preset.step_total,
        "Review results and export",
        "The console will stage the output according to the selected profile, then offer export options.",
    )
    render_review_sections(results, parsed_input.counts, parsed_input.invalid_ips, profile)
    run_export_flow(results, parsed_input.counts)


# ==================================================
# Main Workflow
# ==================================================


def main():
    initialize_runtime_intel()
    enable_windows_terminal()
    show_banner()
    if INTEL_LOAD_WARNING:
        print(color(INTEL_LOAD_WARNING, WARNING))

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
