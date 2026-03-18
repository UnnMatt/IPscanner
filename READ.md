# IP Scanner

This is a small terminal tool for checking a list of IPv4 addresses.

It looks up location and provider details, checks a few common hosting and proxy signals, then gives a simple suspicion score to help sort the results.

The script is meant to stay practical. It is not trying to replace proper threat intel or deep network analysis. It is just a fast way to take a list of IPs and turn it into something easier to read.

## What It Does

1. Accepts IPs from pasted input or from a text file
2. Validates IPv4 addresses and skips invalid entries
3. Looks up geolocation data
4. Shows ISP, organization, ASN, and AS name details
5. Highlights hosting, proxy, and mobile flags
6. Builds a suspicion score from the returned data
7. Sorts results so the most suspicious entries show first
8. Shows summaries for duplicates, countries, ASN groups, and subnets
9. Exports results to CSV and JSON

## Features

1. Paste mode for quick checks
2. File input for larger lists
3. Clean terminal output with color and sectioned summaries
4. Lookup summary table
5. Detailed per IP view
6. Duplicate summary
7. Grouping by country
8. ASN summary
9. Subnet summary
10. CSV export
11. JSON export

## Requirements

1. Python 3
2. Internet access

The script uses the `ip-api.com` batch endpoint for lookups.

## How To Run

1. Open a terminal in the project folder
2. Run:

```bash
python ipscanner.py
```

## Input Options

When the script starts, you can choose one of these:

1. Paste IPs manually
2. Load IPs from a file
3. Exit

### Paste Mode

Paste mode is meant for quick use.

1. Paste one or more IPv4 addresses
2. When you are ready, type `/start`
3. If you want to clear what you pasted, type `/clear`
4. If you want to go back to the main menu, type `/cancel`

Example:

```text
1.1.1.1
8.8.8.8
/start
```

### File Input

You can also load IPs from a text file.

The script will read the file contents and extract valid IPv4 addresses from it.

## Output

The script prints a few sections in order so it is easier to follow.

1. Input summary
2. Result overview
3. Main results table
4. Type summary
5. Duplicate summary
6. Grouped by country
7. ASN summary
8. Subnet summary
9. Optional detailed results

## Exports

At the end of a run, the script can save:

1. CSV output
2. JSON output

Default names:

1. `ip_results.csv`
2. `ip_results.json`

## Notes About The Score

The suspicion score is only a rough indicator.

It looks at:

1. Hosting flag
2. Proxy flag
3. Mobile flag
4. Certain provider and network keywords
5. ASN related hints

That means a result marked as suspicious is not automatically bad, and a low score is not a guarantee that an address is harmless.

It is best used as a sorting and review aid.

## Limits

This tool depends on the data returned by the remote lookup service.

That means:

1. Missing or incorrect provider data can affect the result
2. Some residential or mobile networks may still look suspicious
3. Some hosting or VPN related addresses may look ordinary
4. The score should always be read as a hint, not a final answer

## Example Use Cases

1. Reviewing login IPs
2. Checking repeated addresses in logs
3. Sorting mixed address lists before manual review
4. Getting a quick location and ASN overview

## Public Project Note

This project is simple on purpose.

It focuses on readable terminal output and quick review, not on collecting every possible signal from every source.

If you want to change the scoring logic, add providers, or adjust how the summaries look, the script is kept in one file so it is easy to edit.
