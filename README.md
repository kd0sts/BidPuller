# BidPuller

A lightweight Python monitor that displays and auto-updates cash bids for:

- **Cargill - Blair**
- **Central Valley Ag - East Hub**

The monitor currently targets **Corn** and **Soybeans** and refreshes on a timer.

It fetches from the shared cash bids page: `https://www.cvacoop.com/cash-bids`, then filters results for the two configured destinations.

## Run

```bash
python3 cash_bids_monitor.py
```

### Useful options

- `--interval 120` refresh every 120 seconds.
- `--once` fetch one time and exit.
- `--timeout 30` set request timeout.
- `--no-clear` keep terminal scrollback instead of clearing every refresh.

Example:

```bash
python3 cash_bids_monitor.py --interval 60
```

## Notes

- Uses only Python standard library modules.
- If a site changes layout or blocks requests, the monitor will show an error in the status column.
- The shared source URL and location aliases are configured in `DEFAULT_SOURCES` near the top of `cash_bids_monitor.py`.


## Build a Windows `.exe`

### Option 1: Build locally on Windows

From Command Prompt in this repo:

```bat
build_windows_exe.bat
```

The executable will be created at:

- `dist\bidpuller.exe`

### Option 2: Build from GitHub Actions

A workflow is included at `.github/workflows/build-windows-exe.yml`.

- Trigger **Build Windows EXE** from the Actions tab (or push changes to `cash_bids_monitor.py`).
- Download the artifact named **bidpuller-windows-exe**.
- Inside it, use `bidpuller.exe`.
