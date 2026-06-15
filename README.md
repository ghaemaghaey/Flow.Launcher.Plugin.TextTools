# Text Tools

A [Flow Launcher](https://www.flowlauncher.com/) Python plugin for quick text transformations on clipboard content.

Type `tt` in Flow Launcher to see available tools. Each action reads the current clipboard text, applies the transformation, and copies the result back to the clipboard.

## Tools

| Tool | Description |
|------|-------------|
| Arabic to Persian | Replaces Arabic characters `ك` → `ک` and `ي` → `ی` |
| Add comma to each line | Appends `,` to the end of every line |
| UPPERCASE | Converts text to uppercase |
| lowercase | Converts text to lowercase |
| Remove empty lines | Deletes all blank lines |
| Trim each line | Removes leading and trailing spaces from each line |
| Remove all spaces | Removes regular spaces, half-spaces (ZWNJ), zero-width characters, and other Unicode whitespace |

## Usage

1. Copy the text you want to transform to the clipboard.
2. Open Flow Launcher and type `tt` followed by the tool name (e.g. `tt upper`).
3. Select the desired tool and press Enter.
4. The transformed text is copied to the clipboard.

## Installation

### From Flow Launcher Plugin Store

```
pm install Text Tools
```

### Manual

1. Clone or copy this folder into your Flow Launcher plugins directory.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Restart Flow Launcher.

## Requirements

- Python 3
- [flowlauncher](https://pypi.org/project/flowlauncher/)
- [pyperclip](https://pypi.org/project/pyperclip/)

## Author

Ghaem
