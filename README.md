# Text Tools

A [Flow Launcher](https://www.flowlauncher.com/) Python plugin with **200+ clipboard-first tools** ported from the Rasmio Toolbox: text and line utilities, encoders, hashes and crypto, validators, generators, JSON/YAML/XML/CSV, regex, URLs, dates and Jalali conversion, units, finance, colors, images, network diagnostics and reference sheets.

Type `tt` in Flow Launcher to search tools. Each tool reads the clipboard when you press Enter, transforms it, and copies the result back. Image/visual tools save a PNG/SVG in `%TEMP%\TextTools` and open it.

## Usage

1. Copy the text (or file/image) you want to work with.
2. Open Flow Launcher and type `tt` plus part of a tool name, e.g. `tt base64`, `tt json`, `tt iban`, `tt qr`.
3. Select the tool and press Enter.
4. The result is copied to the clipboard (or opened in your image viewer / browser).

### Multi-input tools

Tools that need more than one value use `|` in the clipboard. The tool's subtitle shows the expected order as `in: ...`.

| Tool | Clipboard example |
|------|-------------------|
| Find & Replace | `find|replace|text` |
| Regex Replace | `pattern|flags|replacement|text` |
| Text Diff | `left|right` |
| Unit Converter | `length|10|m` (also `mass`, `area`, `volume`, `speed`, `data`, `time`, `temperature`) |
| HMAC | `secret|message|SHA-256` |
| PBKDF2 | `password|salt|100000|SHA-256|32` |
| TOTP / HOTP | `JBSWY3DPEHPK3PXP|30|6|SHA-1` |
| JSONPath | `$.store.books[*].title|{...}` |
| CSV tools | `column|order|type|CSV` (sort), `query|CSV` (filter) |
| Image crop / resize | `x|y|width|height` / `width|height` |
| Timezone | `2026-01-01 12:00|Asia/Tehran|UTC` |
| QR code | `size|ec|text` (e.g. `256|M|hello`) |

Generators (UUID, ULID, NanoID, passwords, fake data, lorem ipsum, etc.) default to **one** item and accept their options directly in the Flow Launcher query:

```
tt uuid v7                 # one UUID v7
tt uuid v7 4               # four UUIDs
tt uuid v7 1|1|0           # one UUID, with dashes, lowercase
tt uuid v7 1|0|1           # one UUID, no dashes, uppercase
tt fake data 2             # two fake records
tt qr code 256|M|hello     # QR code, 256px, error correction M
```

They also accept the same options from the clipboard when the query has no arguments. Text tools still read the clipboard.

### Visual tools

Color palettes, gradients, shadows, border radii, CSS filters, QR codes, identicons, image tools, SVG→PNG, OG previews, Markdown previews and ANSI rendering save a file and open it. The generated CSS/text is copied to the clipboard where useful.

### Network tools

DNS, reverse DNS, WHOIS/RDAP, public IP, IP info and HTTP header inspection make live network requests and need internet access. DNS uses the system resolver first and falls back to DNS-over-HTTPS.

### Skipped browser-only tools

These tools from the original catalog have no meaningful launcher equivalent and are intentionally not included: `screen-info`, `feature-detector`, `user-agent`, `keycode-inspector`, `websocket-tester`, `cors-tester`, `stopwatch`, `countdown-timer`.

## Categories

Network, encoding, crypto, text, regex, data formats, code, URL, date/time, units, color, media, file, table, diagrams, generators, validators, logs, API, SEO, accessibility, geo, finance and reference.

## Installation

### Plugin manager

```
pm install Text Tools
```

### PowerShell installer (no plugin manager)

The installer downloads the latest GitHub release, backs up any existing Text Tools plugin, installs it into `%APPDATA%\FlowLauncher\Plugins`, and restarts Flow Launcher if it was running.

```powershell
irm https://raw.githubusercontent.com/ghaemaghaey/Flow.Launcher.Plugin.TextTools/main/install.ps1 | iex
```

If your execution policy blocks script files, run it explicitly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

Options:

```powershell
.\install.ps1 -Version 2.0.0      # install a specific release
.\install.ps1 -ZipPath .\TextTools-v2.0.0.zip
.\install.ps1 -NoRestart
```

### Manual

1. Copy this folder to `%APPDATA%\FlowLauncher\Plugins\` (for example `Text Tools-2.0.0`).
2. The release zip already contains all Python dependencies in `lib/` (Windows, CPython 3.11), so no separate `pip install` is needed.
3. Restart Flow Launcher.

For development, vendor the dependencies into `lib/`:

```powershell
pip install -r requirements.txt --target lib
```

Flow Launcher uses Python 3.11 by default. The release workflow runs on Windows with Python 3.11 so the native wheels (`cryptography`, `Pillow`, `lxml`, `pycairo`, `reportlab`) match Flow Launcher's embedded Python.

## Requirements

- Python 3.11
- [flowlauncher](https://pypi.org/project/flowlauncher/)
- [pyperclip](https://pypi.org/project/pyperclip/)
- requests, dnspython, PyYAML, qrcode, Pillow, cryptography, tzdata
- markdown, markdownify, beautifulsoup4
- svglib, reportlab<5, rlPyCairo (SVG→PNG)

## Development and testing

```powershell
pip install -r requirements.txt --target lib
$env:PYTHONPATH = "lib"
python tests/test_end_to_end.py      # Flow Launcher JSON-RPC + clipboard harness
python tests/test_all_tools_smoke.py # every tool runs with a sample input
```

The end-to-end test calls `main.py` with the same JSON-RPC requests Flow Launcher sends (`query` and `run_tool`) and checks real results. Set `TEXTTOOLS_CLIPBOARD_FILE` to a file path to use a test clipboard, and `TEXTTOOLS_NO_OPEN=1` to stop previews from opening during tests.

## Author

Ghaem
