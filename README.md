IP Scanner

This is a small terminal tool for checking a list of IPv4 addresses.

It looks up location and provider details, checks a few common hosting and proxy signals, then gives a simple suspicion score to help sort the results.

The script is meant to stay practical. It is not trying to replace proper threat intel or deep network analysis. It is just a fast way to take a list of IPs and turn it into something easier to read.
What It Does

    Accepts IPs from pasted input or from a text file
    Validates IPv4 addresses and skips invalid entries
    Looks up geolocation data
    Shows ISP, organization, ASN, and AS name details
    Highlights hosting, proxy, and mobile flags
    Builds a suspicion score from the returned data
    Sorts results so the most suspicious entries show first
    Shows summaries for duplicates, countries, ASN groups, and subnets
    Exports results to CSV and JSON

Features

    Paste mode for quick checks
    File input for larger lists
    Clean terminal output with color and sectioned summaries
    Lookup summary table
    Detailed per IP view
    Duplicate summary
    Grouping by country
    ASN summary
    Subnet summary
    CSV export
    JSON export

Requirements

    Python 3
    Internet access

The script uses the ip-api.com batch endpoint for lookups.
How To Run

    Open a terminal in the project folder
    Run:

python ipscanner.py

Input Options

When the script starts, you can choose one of these:

    Paste IPs manually
    Load IPs from a file
    Exit

Paste Mode

Paste mode is meant for quick use.

    Paste one or more IPv4 addresses
    When you are ready, type /start
    If you want to clear what you pasted, type /clear
    If you want to go back to the main menu, type /cancel

Example:

1.1.1.1
8.8.8.8
/start

File Input

You can also load IPs from a text file.

The script will read the file contents and extract valid IPv4 addresses from it.
Output

The script prints a few sections in order so it is easier to follow.

    Input summary
    Result overview
    Main results table
    Type summary
    Duplicate summary
    Grouped by country
    ASN summary
    Subnet summary
    Optional detailed results

Exports

At the end of a run, the script can save:

    CSV output
    JSON output

Default names:

    ip_results.csv
    ip_results.json

Notes About The Score

The suspicion score is only a rough indicator.

It looks at:

    Hosting flag
    Proxy flag
    Mobile flag
    Certain provider and network keywords
    ASN related hints

That means a result marked as suspicious is not automatically bad, and a low score is not a guarantee that an address is harmless.

It is best used as a sorting and review aid.
Limits

This tool depends on the data returned by the remote lookup service.

That means:

    Missing or incorrect provider data can affect the result
    Some residential or mobile networks may still look suspicious
    Some hosting or VPN related addresses may look ordinary
    The score should always be read as a hint, not a final answer

Example Use Cases

    Reviewing login IPs
    Checking repeated addresses in logs
    Sorting mixed address lists before manual review
    Getting a quick location and ASN overview

Public Project Note

This project is simple on purpose.

It focuses on readable terminal output and quick review, not on collecting every possible signal from every source.

If you want to change the scoring logic, add providers, or adjust how the summaries look, the script is kept in one file so it is easy to edit.
