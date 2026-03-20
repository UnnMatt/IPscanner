# IP Scanner

`IP Scanner` is a terminal-first review tool for working through batches of IPv4 and IPv6 addresses without bouncing between websites, whois tabs, and one-off commands.

It takes a list of IPs, runs a public lookup pass, adds lightweight enrichment, scores the results, and lays everything out in a way that is meant to be fast to read in a terminal. It is not trying to be a full forensic platform. The goal is simpler than that: make triage and manual review less annoying.

## What It Does

- accepts IPv4, IPv6, or mixed input
- supports paste mode and file input
- normalizes and deduplicates addresses
- keeps hit counts for repeated IPs
- batches lookups through `ip-api.com`
- adds reverse DNS when it is available
- checks the Tor bulk exit list
- scores each result using a simple signal model
- groups repeated patterns like ASN, provider, subnet, and country
- explains failed public lookups more clearly for private, reserved, link-local, documentation, and similar ranges
- exports to CSV and JSON

## Running It

Open a terminal in the project folder and run:

```bash
python ipscanner.py
```

## Requirements

- Python 3
- internet access

The script only uses the Python standard library.

## Inputs

You can feed the scanner in two ways:

- paste mode
- file input

Paste mode is the quickest option when you are working from logs or copied data. File input is useful when you already have a prepared list.

Accepted input includes:

- public IPv4
- public IPv6
- private and internal addresses
- reserved and documentation ranges
- mixed IPv4 and IPv6 in the same run

Private or reserved addresses are still accepted on purpose. They usually do not resolve through the public lookup service, but the script now calls out the reason more cleanly instead of just leaving you with a vague failure line.

### Paste Mode Commands

- `/start` starts the scan
- `/clear` clears the current buffer
- `/cancel` returns to the previous menu
- `/help` opens the built-in help screen

Example:

```text
1.1.1.1
8.8.8.8
2606:4700:4700::1111
2001:4860:4860::8888
/start
```

## Workflows

The first menu is about posture, not lookup logic. The workflows all use the same core engine underneath, but they push you toward different ways of reviewing the output.

### Core Lookup

The default path. Best for normal checks when you just want a clean review without too much noise.

### Threat Signals

Leans harder into suspicious infrastructure, repeated ownership, and clustering.

### Ownership Intel

Uses the same engine, but frames the review more around provider and ownership patterns.

### Full Investigation

The broadest current presentation path. If you want the biggest review pass, this is the one.

### Check Intel Updates

Compares your local keyword intel bundle against a remote JSON feed and lets you apply the update from inside the script.

## Scan Profiles

Profiles change how much the script shows and how it stages the review. They are not just cosmetic themes.

### Quick

Made for triage.

- compact results matrix
- duplicate review when it matters
- minimal output
- detailed cards only if you explicitly ask for them

### Standard

The best default for most people.

- executive overview cards
- main results matrix
- useful summaries without dumping everything
- optional detailed cards

### Threat Hunter

Built for signal-heavy review.

- high-risk findings section
- provider repetition
- ASN clustering
- subnet clustering
- country grouping
- suspicious-only detailed cards

### Analyst

The slow-and-careful profile.

- expanded detail cards
- clearer narrative layout
- ownership and provider summaries
- reverse DNS, Tor state, and reasons shown in a calmer structure

### Insanity

Everything turned on, but still organized.

- executive overview
- high-risk findings
- full results matrix
- provider patterns
- ASN clustering
- country grouping
- subnet clustering
- duplicate review
- failed lookup review
- detailed per-IP intelligence
- invalid or skipped input section

This is the profile for full visibility. It is intentionally loud, but it should still feel controlled.

### Custom

Manual control over the output sections.

Instead of a long series of yes/no prompts, the script gives you a checklist-style selection screen so you can toggle sections on and off before the scan starts.

## What You See In The Output

Depending on the selected profile, a run can include:

- validation summary
- executive overview cards
- high-risk findings
- full results matrix
- type distribution
- provider summary
- ASN summary
- country grouping
- subnet summary
- duplicate hit review
- failed lookup review
- detailed intelligence cards
- invalid or skipped entries

Not every section appears on every run. Empty sections stay hidden so the output does not fill up with dead space.

## Signals And Scoring

The score is a sorting aid, not a verdict.

It uses a mix of:

- `hosting`
- `proxy`
- `mobile`
- Tor exit matches
- provider and ASN keyword hits
- a few extra consistency clues from provider text

Current score bands:

- `VERY HIGH`: 9+
- `HIGH`: 6 to 8
- `MEDIUM`: 3 to 5
- `LOW`: 1 to 2
- `NONE`: 0 or below

That score helps push the more suspicious-looking entries toward the top of the screen. It should not be treated as proof that an IP is malicious, residential, or a VPN exit.

## Reverse DNS And Tor Checks

Reverse DNS is handled as a separate enrichment pass after the main lookup. It works for both IPv4 and IPv6 where PTR data exists.

Tor detection is also a separate pass. The script fetches the Tor Project bulk exit list during the run, checks each IP against it, and carries that result into the output and exports.

## Failed Lookup Diagnostics

When a public lookup fails, the script does more than repeat the remote error message.

It now tries to classify the address locally and explain what kind of range it belongs to. That includes things like:

- RFC1918 private IPv4
- unique local IPv6
- link-local IPv4 or IPv6
- loopback ranges
- documentation ranges
- benchmark and reserved ranges

That makes failed results much easier to understand when you are working with internal logs or mixed address sets.

## Intel Updates

The keyword-based scoring bundle lives in `ipscanner_intel.json`.

At startup, the script loads that file and uses it to drive parts of the scoring logic. From the main menu, `Check Intel Updates` compares the local copy with a remote JSON feed and can write the newer version back to disk.

Default remote feed:

- `https://raw.githubusercontent.com/UnnMatt/IPscanner/main/ipscanner_intel.json`

You can override that URL with:

- `IPSCANNER_INTEL_URL`

This updater is only for the intel bundle. It does not update the Python script itself.

## Exports

At the end of a run, the script can save:

- CSV
- JSON

Default filenames:

- `ip_results.csv`
- `ip_results.json`

Exports include the main lookup result plus the normalized review fields the script adds, such as:

- hit count
- type classification
- suspicion flag
- suspicion score
- score reasons
- Tor state
- reverse DNS
- failed lookup diagnostics

## External Services

The script currently relies on:

- `ip-api.com` for batch IP lookup
- the Tor Project bulk exit list
- local DNS resolution for reverse DNS

## Limits

This tool is only as clean as the data it can pull in.

Keep in mind:

- provider labels can be incomplete or misleading
- reverse DNS can be stale, generic, or missing
- hosted infrastructure can look suspicious even when it is normal
- private and reserved ranges will not behave like public IPs
- Tor membership changes over time
- keyword scoring is useful for sorting, not final attribution

## Why It Is Still One File

This project is intentionally kept simple.

It stays in a single script because the point is to have something easy to run, easy to tweak, and easy to carry around. The UI has grown quite a bit, but the tool is still meant to feel practical rather than overbuilt.
