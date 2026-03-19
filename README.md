IP Scanner

This is a terminal IP review tool for mixed IPv4 and IPv6 input.

It takes a list of IPs, looks up location and provider details, adds a few lightweight enrichments, builds a simple suspicion score, and renders the results in a readable terminal layout.

The script is meant to stay practical. It is not trying to replace proper threat intel, full attribution work, or deep network analysis. It is a fast review aid that helps sort and inspect IPs without leaving the terminal.

## What It Does

- Accepts IPv4, IPv6, or mixed input from paste mode or a text file
- Validates and normalizes IPs with Python's `ipaddress` module
- Deduplicates repeated IPs and counts total hits
- Looks up geolocation and provider data with the `ip-api.com` batch endpoint
- Adds reverse DNS where available
- Checks whether an IP is listed as a known Tor exit node
- Builds a simple suspicion score from returned flags and provider clues
- Sorts results so the riskiest-looking entries show first
- Shows compact summaries and optional detailed per-IP results
- Exports results to CSV and JSON

## Current Features

- Single-file script: `ipscanner.py`
- Terminal-based workflow with boxed menus and colored output
- Main workflow menu:
  - `Core Lookup`
  - `Threat Signals`
  - `Ownership Intel`
  - `Full Investigation`
- Scan profiles:
  - `Quick scan`
  - `Standard scan`
  - `Deep scan`
  - `Custom options`
- Paste mode and file input
- Mixed IPv4 and IPv6 support
- Reverse DNS enrichment
- Tor exit node detection
- Result overview
- Main lookup table
- Type summary
- Country grouping
- ASN summary
- Subnet summary
- Compact detailed results
- CSV export
- JSON export
- Built-in `/help` guide

## Requirements

- Python 3
- Internet access

External services used:

- `ip-api.com` batch lookup API for geolocation/provider data
- Tor Project bulk exit list for Tor exit node matching
- local DNS resolution for reverse DNS lookups

## How To Run

Open a terminal in the project folder and run:

```bash
python ipscanner.py
```

## Workflow

When the script starts, it shows a workflow menu before input selection.

- `Core Lookup`
  - Best default path for most checks
- `Threat Signals`
  - Same core flow, but aimed at deeper signal review
- `Ownership Intel`
  - Workflow shell for later ownership-focused phases
- `Full Investigation`
  - Broadest current shell, still built on the same core engine

Some later-phase workflows currently route through the existing core lookup flow while keeping the menu structure ready for future additions.

## Input Options

After the workflow selection, choose how to provide input:

- `Enter`
  - Paste IPs manually
- `F`
  - Load IPs from a file
- `Q`
  - Exit

The script accepts:

- public IPv4
- public IPv6
- private/internal IPs
- reserved/documentation ranges
- mixed IPv4 and IPv6 in the same run

Private or reserved IPs are still accepted as valid input, but they may fail later during lookup because the remote service cannot resolve public data for them.

## Paste Mode

Paste mode is meant for quick manual checks.

Commands:

- `/start`
  - begin the lookup using the pasted lines
- `/clear`
  - clear the current pasted input
- `/cancel`
  - return to the previous menu
- `/help`
  - show the built-in help guide

Example:

```text
1.1.1.1
8.8.8.8
2606:4700:4700::1111
2001:4860:4860::8888
/start
```

## File Input

You can also load IPs from a text file.

The script reads the file contents, extracts valid IP addresses, normalizes them, deduplicates them, and keeps hit counts for repeated values.

## Scan Profiles

The current scan profiles control how much review output is shown.

- `Quick scan`
  - fastest pass with fewer summaries
- `Standard scan`
  - recommended default balance
- `Deep scan`
  - all available summaries plus detailed records
- `Custom options`
  - manual selection of optional sections

## Output

A normal run can include these sections:

- Input summary
- Result overview
- Main lookup results table
- Type summary
- Duplicate summary
- Grouped by country
- ASN summary
- Subnet summary
- Detailed results
- Invalid/skipped entries

Some sections are intentionally hidden when they add no value, for example:

- duplicate summary when there are no duplicates
- grouped country view when there are no meaningful groupings
- ASN or subnet summaries when there are no repeated clusters

## Reverse DNS

Reverse DNS is handled as a separate enrichment step after the main lookup.

- Works for IPv4 and IPv6 where PTR records exist
- Failure does not stop the scan
- Missing PTR records are handled cleanly
- Detailed results show reverse DNS when there is a useful hostname
- Export includes reverse DNS fields

## Tor Exit Detection

Tor detection is handled as a separate threat signal.

- The script fetches the Tor Project bulk exit list once per run
- Each IP is checked against that list
- Tor results are normalized on the internal record
- Tor evidence is shown in detailed results when relevant
- Tor data is included in export output

## Notes About The Score

The suspicion score is a rough review signal, not a final verdict.

It currently uses a mix of:

- hosting flag
- proxy flag
- mobile flag
- Tor exit match
- provider/network keyword matches
- ASN-related hints
- a few provider-text consistency clues

Current broad scoring bands:

- `VERY HIGH`
  - 9 or more
- `HIGH`
  - 6 to 8
- `MEDIUM`
  - 3 to 5
- `LOW`
  - 1 to 2
- `NONE`
  - 0 or less

The score is meant to help sort and review results quickly. It should not be treated as proof that an IP is malicious, residential, VPN, or benign.

## Built-In Help

You can type `/help` at interactive prompts to reopen the built-in guide.

The help screen explains:

- how the scan flow works
- what the score points are based on
- what each workflow means
- what each scan profile does

## Exports

At the end of a run, the script can save:

- CSV output
- JSON output

Default filenames:

- `ip_results.csv`
- `ip_results.json`

Current export data includes the core lookup result plus normalized fields such as:

- hit count
- type classification
- suspicion flag
- suspicion score
- score reasons
- Tor state
- reverse DNS fields

## Limits

This tool depends on remote and network-derived data.

That means:

- missing or incorrect provider data can change the result
- reverse DNS may be missing, stale, generic, or misleading
- some public resolvers and CDN infrastructure may look suspicious because they are hosted infrastructure
- private and reserved IPs will often fail lookup cleanly
- Tor list membership changes over time
- the score should always be read as a hint, not a final answer

## Example Use Cases

- reviewing login IPs
- checking mixed address lists from logs
- sorting repeated addresses before manual review
- getting a quick location, ASN, and provider overview
- spotting infrastructure-heavy results faster

## Project Note

This project is intentionally kept as a single terminal script.

The goal is:

- readable output
- familiar workflow
- quick review
- clean internal structure for future additions

It is not designed to be a full forensic suite. It focuses on staying practical and easy to run with:

```bash
python ipscanner.py
```
