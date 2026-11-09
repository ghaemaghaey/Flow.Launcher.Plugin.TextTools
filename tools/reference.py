# -*- coding: utf-8 -*-
"""Reference and cheat-sheet tools."""

from __future__ import annotations

from .common import ok, split_pipe, to_ascii_digits
from .meta import make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


# --------------------------------------------------------------------------
# ASCII table
# --------------------------------------------------------------------------

_CONTROL = {
    0: "NUL", 1: "SOH", 2: "STX", 3: "ETX", 4: "EOT", 5: "ENQ", 6: "ACK",
    7: "BEL", 8: "BS", 9: "HT", 10: "LF", 11: "VT", 12: "FF", 13: "CR",
    14: "SO", 15: "SI", 16: "DLE", 17: "DC1", 18: "DC2", 19: "DC3", 20: "DC4",
    21: "NAK", 22: "SYN", 23: "ETB", 24: "CAN", 25: "EM", 26: "SUB", 27: "ESC",
    28: "FS", 29: "GS", 30: "RS", 31: "US", 32: "SP", 127: "DEL",
}


def ascii_table(item: Input) -> Output:
    query = to_ascii_digits(item.text.strip()).lower()
    lines = ["Dec  Hex  Oct  Char  Description"]
    for code in range(128):
        char = _CONTROL.get(code, chr(code))
        description = "control character" if code in _CONTROL else f"printable '{chr(code)}'"
        row = f"{code:>3}  0x{code:02X}  {code:03o}  {char:<4}  {description}"
        if not query or query in row.lower() or query == str(code) or query == f"{code:02x}":
            lines.append(row)
    return ok("\n".join(lines), title="ASCII Table")


_register(make_tool("ascii-table", ascii_table, title="ASCII Table", hint="query (optional)"))


# --------------------------------------------------------------------------
# HTTP status codes
# --------------------------------------------------------------------------

_HTTP_STATUS = [
    (100, "Continue"), (101, "Switching Protocols"),
    (200, "OK"), (201, "Created"), (202, "Accepted"), (204, "No Content"), (206, "Partial Content"),
    (301, "Moved Permanently"), (302, "Found"), (304, "Not Modified"), (307, "Temporary Redirect"), (308, "Permanent Redirect"),
    (400, "Bad Request"), (401, "Unauthorized"), (403, "Forbidden"), (404, "Not Found"),
    (405, "Method Not Allowed"), (408, "Request Timeout"), (409, "Conflict"), (410, "Gone"),
    (413, "Payload Too Large"), (415, "Unsupported Media Type"), (422, "Unprocessable Entity"), (429, "Too Many Requests"),
    (500, "Internal Server Error"), (501, "Not Implemented"), (502, "Bad Gateway"), (503, "Service Unavailable"), (504, "Gateway Timeout"),
]


def http_status(item: Input) -> Output:
    query = item.text.strip().lower()
    rows = [
        f"{code}  {name}"
        for code, name in _HTTP_STATUS
        if not query or query in str(code) or query in name.lower()
    ]
    if not rows:
        return ok("No matching HTTP status code.", title="HTTP Status Codes")
    return ok("\n".join(rows), title="HTTP Status Codes")


_register(make_tool("http-status", http_status, title="HTTP Status Codes", hint="query (optional)"))


# --------------------------------------------------------------------------
# Cheatsheets
# --------------------------------------------------------------------------

_SHEETS = {
    "Git": [
        ("git init", "Create a repository"), ("git clone <url>", "Clone a repository"),
        ("git status", "Show working-tree status"), ("git add <file>", "Stage a file"),
        ("git add -A", "Stage everything"), ("git commit -m \"msg\"", "Commit staged changes"),
        ("git commit --amend", "Amend the last commit"), ("git log --oneline --graph", "Compact graph log"),
        ("git diff", "Show unstaged changes"), ("git branch <name>", "Create a branch"),
        ("git checkout -b <name>", "Create and switch branch"), ("git switch <name>", "Switch branch"),
        ("git merge <name>", "Merge a branch"), ("git rebase <name>", "Rebase onto a branch"),
        ("git pull", "Fetch and merge"), ("git push -u origin <name>", "Push and set upstream"),
        ("git stash", "Stash changes"), ("git reset --hard HEAD", "Discard local changes"),
    ],
    "Docker": [
        ("docker ps", "Running containers"), ("docker ps -a", "All containers"),
        ("docker images", "List images"), ("docker pull <image>", "Pull an image"),
        ("docker build -t <name> .", "Build an image"), ("docker run -d -p 80:80 <image>", "Run detached with a port"),
        ("docker run -it <image> sh", "Run an interactive shell"), ("docker exec -it <id> sh", "Shell into a container"),
        ("docker logs -f <id>", "Follow logs"), ("docker stop <id>", "Stop a container"),
        ("docker rm <id>", "Remove a container"), ("docker rmi <image>", "Remove an image"),
        ("docker compose up -d", "Start compose services"), ("docker compose down", "Stop compose services"),
        ("docker volume ls", "List volumes"), ("docker system prune -a", "Clean unused data"),
    ],
    "Kubernetes": [
        ("kubectl get pods", "List pods"), ("kubectl get svc", "List services"),
        ("kubectl get nodes", "List nodes"), ("kubectl get all -n <ns>", "All resources in a namespace"),
        ("kubectl describe pod <name>", "Pod details"), ("kubectl logs -f <pod>", "Follow pod logs"),
        ("kubectl exec -it <pod> -- sh", "Shell into a pod"), ("kubectl apply -f <file>", "Apply a manifest"),
        ("kubectl delete -f <file>", "Delete a manifest"), ("kubectl scale deploy <n> --replicas=3", "Scale a deployment"),
        ("kubectl rollout status deploy/<n>", "Rollout status"), ("kubectl rollout undo deploy/<n>", "Roll back"),
        ("kubectl port-forward <pod> 8080:80", "Port-forward a pod"), ("kubectl config get-contexts", "List contexts"),
        ("kubectl top pods", "Pod resource usage"),
    ],
    "Linux": [
        ("ls -lah", "List files with details"), ("cd -", "Go to previous directory"),
        ("find . -name '*.log'", "Find files by name"), ("grep -rn 'text' .", "Recursive search"),
        ("chmod +x <file>", "Make executable"), ("chown user:group <file>", "Change owner"),
        ("df -h", "Disk space"), ("du -sh *", "Directory sizes"),
        ("ps aux | grep <name>", "Find a process"), ("kill -9 <pid>", "Force kill"),
        ("tar -czf out.tar.gz dir/", "Create a tar.gz"), ("tar -xzf file.tar.gz", "Extract a tar.gz"),
        ("ln -s <target> <link>", "Create a symlink"), ("systemctl status <svc>", "Service status"),
        ("journalctl -u <svc> -f", "Follow service logs"), ("ss -tulpn", "Listening sockets"),
    ],
    "Bash": [
        ("for i in {1..5}; do echo $i; done", "Loop"), ("if [ -f file ]; then ...; fi", "File test"),
        ("while read line; do ...; done < f", "Read lines"), ("name() { echo hi; }", "Function"),
        ("var=${1:-default}", "Default value"), ("${var//old/new}", "Replace all"),
        ("$(command)", "Command substitution"), ("cmd1 && cmd2", "Run second on success"),
        ("cmd1 || cmd2", "Run second on failure"), ("cmd > out 2>&1", "Redirect stdout and stderr"),
        ("set -euo pipefail", "Strict mode"), ("trap 'cleanup' EXIT", "Run on exit"),
        ("arr=(a b c); echo ${arr[1]}", "Array access"), ("echo ${#var}", "String length"),
    ],
    "Cron": [
        ("* * * * *", "Every minute"), ("*/5 * * * *", "Every 5 minutes"),
        ("0 * * * *", "Every hour"), ("0 0 * * *", "Every day at midnight"),
        ("0 9 * * 1-5", "Weekdays at 09:00"), ("0 0 * * 0", "Sundays at midnight"),
        ("0 0 1 * *", "First day of month"), ("0 0 1 1 *", "January 1"),
        ("30 2 * * 6", "Saturday 02:30"), ("@reboot", "At startup"),
        ("@daily", "Same as 0 0 * * *"), ("@hourly", "Same as 0 * * * *"),
        ("min hour day month weekday", "Field order"), ("crontab -e", "Edit crontab"),
    ],
    "Markdown": [
        ("# Heading", "Heading 1"), ("## Heading", "Heading 2"), ("**bold**", "Bold"),
        ("*italic*", "Italic"), ("~~strike~~", "Strikethrough"), ("[text](https://url)", "Link"),
        ("![alt](img.png)", "Image"), ("`code`", "Inline code"), ("```lang ... ```", "Code block"),
        ("- item", "Bullet list"), ("1. item", "Numbered list"), ("> quote", "Blockquote"),
        ("| a | b |", "Table"), ("- [ ] task", "Task list"), ("---", "Horizontal rule"),
    ],
    "SQL": [
        ("SELECT * FROM t WHERE x = 1", "Select rows"), ("SELECT DISTINCT col FROM t", "Distinct"),
        ("INSERT INTO t (a,b) VALUES (1,2)", "Insert"), ("UPDATE t SET a = 1 WHERE id = 5", "Update"),
        ("DELETE FROM t WHERE id = 5", "Delete"), ("ORDER BY col DESC", "Sort"),
        ("LIMIT 10 OFFSET 20", "Paginate"), ("GROUP BY col HAVING COUNT(*) > 1", "Group and filter"),
        ("JOIN t2 ON t.id = t2.tid", "Inner join"), ("LEFT JOIN t2 ON ...", "Left join"),
        ("COUNT(*), SUM(x), AVG(x)", "Aggregates"), ("CREATE TABLE t (id INT PRIMARY KEY)", "Create table"),
        ("ALTER TABLE t ADD col TEXT", "Add column"), ("CREATE INDEX idx ON t (col)", "Create index"),
        ("LIKE '%text%'", "Pattern match"),
    ],
}


def cheatsheets(item: Input) -> Output:
    topic, query = split_pipe(item.text, 2, from_right=False, strip=True)
    topic = (topic or "Git").strip()
    sheet = _SHEETS.get(topic) or _SHEETS.get(topic.title())
    if not sheet:
        available = ", ".join(_SHEETS)
        raise ToolError(f"Unknown topic: {topic}. Available: {available}")
    query = query.lower()
    lines = [f"{topic}:"]
    for command, description in sheet:
        if not query or query in command.lower() or query in description.lower():
            lines.append(f"  {command:<42} {description}")
    return ok("\n".join(lines), title=f"Cheatsheet: {topic}")


_register(make_tool("cheatsheets", cheatsheets, title="Cheatsheets", hint="topic|query"))


# --------------------------------------------------------------------------
# Emoji picker
# --------------------------------------------------------------------------

_EMOJI = [
    ("😀", "grinning"), ("😃", "smiley"), ("😄", "laughing"), ("😁", "beaming"),
    ("😆", "sweat smile"), ("😅", "grin sweat"), ("😂", "joy"), ("🤣", "rofl"),
    ("😊", "blush"), ("😇", "angel"), ("🙂", "slight smile"), ("🙃", "upside down"),
    ("😉", "wink"), ("😌", "relieved"), ("😍", "heart eyes"), ("🥰", "smiling hearts"),
    ("😘", "kiss"), ("😎", "cool"), ("🤓", "nerd"), ("🧐", "monocle"),
    ("🤔", "thinking"), ("🤨", "raised eyebrow"), ("😐", "neutral"), ("😑", "expressionless"),
    ("😶", "no mouth"), ("🙄", "eye roll"), ("😏", "smirk"), ("😴", "sleeping"),
    ("😷", "mask"), ("🤒", "sick"), ("🤯", "mind blown"), ("🥳", "partying"),
    ("😭", "loudly crying"), ("😤", "triumph"), ("😡", "angry"), ("🤬", "cursing"),
    ("👍", "thumbs up"), ("👎", "thumbs down"), ("👌", "ok"), ("✌️", "victory"),
    ("🤞", "crossed fingers"), ("🤟", "love you"), ("🤘", "rock"), ("👏", "clap"),
    ("🙌", "raised hands"), ("🙏", "pray"), ("👋", "wave"), ("💪", "muscle"),
    ("❤️", "red heart"), ("🧡", "orange heart"), ("💛", "yellow heart"), ("💚", "green heart"),
    ("💙", "blue heart"), ("💜", "purple heart"), ("🖤", "black heart"), ("💔", "broken heart"),
    ("🔥", "fire"), ("✨", "sparkles"), ("⭐", "star"), ("🌟", "glowing star"),
    ("💯", "hundred"), ("💥", "collision"), ("🎉", "party"), ("🎁", "gift"),
    ("🐶", "dog"), ("🐱", "cat"), ("🦊", "fox"), ("🐻", "bear"),
    ("🐼", "panda"), ("🦁", "lion"), ("🐯", "tiger"), ("🐵", "monkey"),
    ("🐧", "penguin"), ("🦄", "unicorn"), ("🐝", "bee"), ("🦋", "butterfly"),
    ("🌵", "cactus"), ("🌳", "tree"), ("🌹", "rose"), ("🌻", "sunflower"),
    ("🍎", "apple"), ("🍌", "banana"), ("🍇", "grapes"), ("🍓", "strawberry"),
    ("🍉", "watermelon"), ("🍕", "pizza"), ("🍔", "burger"), ("🍟", "fries"),
    ("🍣", "sushi"), ("🍩", "donut"), ("🍪", "cookie"), ("🎂", "cake"),
    ("☕", "coffee"), ("🍵", "tea"), ("🍺", "beer"), ("🍷", "wine"),
    ("💻", "laptop"), ("🖥️", "desktop"), ("⌨️", "keyboard"), ("🖱️", "mouse"),
    ("📱", "phone"), ("🔋", "battery"), ("💡", "bulb"), ("🔌", "plug"),
    ("📷", "camera"), ("🎬", "movie"), ("🎧", "headphone"), ("🎮", "game"),
    ("📦", "package"), ("📁", "folder"), ("📄", "document"), ("🔑", "key"),
    ("🔒", "lock"), ("🔔", "bell"), ("⏳", "hourglass"), ("💰", "money"),
    ("💳", "card"), ("🚀", "rocket"), ("✈️", "plane"), ("🚗", "car"),
    ("🏠", "house"), ("✅", "check"), ("❌", "cross"), ("⚠️", "warning"),
    ("❓", "question"), ("❗", "exclamation"), ("➡️", "arrow"), ("🔗", "link"),
    ("🔍", "search"),
]


def emoji_picker(item: Input) -> Output:
    query = item.text.strip().lower()
    rows = [f"{emoji}  {name}" for emoji, name in _EMOJI if not query or query in name or query == emoji]
    if not rows:
        return ok("No matching emoji.", title="Emoji Picker")
    return ok("\n".join(rows), title="Emoji Picker")


_register(make_tool("emoji-picker", emoji_picker, title="Emoji Picker", hint="query (optional)"))


# --------------------------------------------------------------------------
# HTML entities / symbols
# --------------------------------------------------------------------------

_ENTITIES = [
    ("&amp;", "&", "ampersand"), ("&lt;", "<", "less than"), ("&gt;", ">", "greater than"),
    ("&quot;", '"', "double quote"), ("&apos;", "'", "apostrophe"), ("&nbsp;", "\u00a0", "non-breaking space"),
    ("&copy;", "©", "copyright"), ("&reg;", "®", "registered"), ("&trade;", "™", "trademark"),
    ("&euro;", "€", "euro"), ("&pound;", "£", "pound"), ("&yen;", "¥", "yen"),
    ("&cent;", "¢", "cent"), ("&deg;", "°", "degree"), ("&plusmn;", "±", "plus-minus"),
    ("&times;", "×", "multiplication"), ("&divide;", "÷", "division"), ("&frac12;", "½", "one half"),
    ("&frac14;", "¼", "one quarter"), ("&frac34;", "¾", "three quarters"), ("&sup2;", "²", "squared"),
    ("&sup3;", "³", "cubed"), ("&micro;", "µ", "micro"), ("&para;", "¶", "paragraph"),
    ("&sect;", "§", "section"), ("&middot;", "·", "middle dot"), ("&bull;", "•", "bullet"),
    ("&hellip;", "…", "ellipsis"), ("&ndash;", "–", "en dash"), ("&mdash;", "—", "em dash"),
    ("&lsquo;", "‘", "left single quote"), ("&rsquo;", "’", "right single quote"),
    ("&ldquo;", "“", "left double quote"), ("&rdquo;", "”", "right double quote"),
    ("&laquo;", "«", "left angle quote"), ("&raquo;", "»", "right angle quote"),
    ("&larr;", "←", "left arrow"), ("&uarr;", "↑", "up arrow"), ("&rarr;", "→", "right arrow"),
    ("&darr;", "↓", "down arrow"), ("&harr;", "↔", "left-right arrow"),
    ("&spades;", "♠", "spade"), ("&clubs;", "♣", "club"), ("&hearts;", "♥", "heart"),
    ("&diams;", "♦", "diamond"), ("&infin;", "∞", "infinity"), ("&ne;", "≠", "not equal"),
    ("&le;", "≤", "less or equal"), ("&ge;", "≥", "greater or equal"), ("&radic;", "√", "square root"),
    ("&sum;", "∑", "sum"), ("&pi;", "π", "pi"), ("&alpha;", "α", "alpha"), ("&beta;", "β", "beta"),
    ("&zwnj;", "\u200c", "zero-width non-joiner"),
]


def html_entities_reference(item: Input) -> Output:
    query = item.text.strip().lower()
    rows = []
    for name, char, description in _ENTITIES:
        if not query or query in name.lower() or query in description or query == char:
            rows.append(f"{char}  {name:<10}  &#x{ord(char):X};  {description}")
    if not rows:
        return ok("No matching entity.", title="HTML Entities")
    return ok("\n".join(rows), title="HTML Entities")


_register(make_tool("html-entities-reference", html_entities_reference, title="HTML Entities Reference", hint="query (optional)"))


_SYMBOLS = [
    ("←", "&larr;"), ("↑", "&uarr;"), ("→", "&rarr;"), ("↓", "&darr;"), ("↔", "&harr;"),
    ("⇒", "&rArr;"), ("⇐", "&lArr;"), ("⇔", "&hArr;"), ("±", "&plusmn;"), ("×", "&times;"),
    ("÷", "&divide;"), ("≠", "&ne;"), ("≤", "&le;"), ("≥", "&ge;"), ("≈", "&asymp;"),
    ("≡", "&equiv;"), ("∞", "&infin;"), ("√", "&radic;"), ("∑", "&sum;"), ("∏", "&prod;"),
    ("∫", "&int;"), ("∂", "&part;"), ("Δ", "&Delta;"), ("π", "&pi;"), ("µ", "&micro;"),
    ("°", "&deg;"), ("∈", "&isin;"), ("∉", "&notin;"), ("∩", "&cap;"), ("∪", "&cup;"),
    ("∅", "&empty;"), ("∀", "&forall;"), ("$", "&#36;"), ("€", "&euro;"), ("£", "&pound;"),
    ("¥", "&yen;"), ("¢", "&cent;"), ("•", "&bull;"), ("…", "&hellip;"), ("–", "&ndash;"),
    ("—", "&mdash;"), ("“", "&ldquo;"), ("”", "&rdquo;"), ("‘", "&lsquo;"), ("’", "&rsquo;"),
    ("«", "&laquo;"), ("»", "&raquo;"), ("†", "&dagger;"), ("‡", "&Dagger;"), ("§", "&sect;"),
    ("¶", "&para;"), ("©", "&copy;"), ("®", "&reg;"), ("™", "&trade;"), ("‰", "&permil;"),
    ("·", "&middot;"), ("¿", "&iquest;"), ("¡", "&iexcl;"), ("♠", "&spades;"), ("♣", "&clubs;"),
    ("♥", "&hearts;"), ("♦", "&diams;"), ("✓", "&check;"), ("✗", "&#x2717;"), ("★", "&#x2605;"),
]


def html_symbols(item: Input) -> Output:
    query = item.text.strip().lower()
    rows = [f"{char}  {entity}" for char, entity in _SYMBOLS if not query or query in entity.lower() or query == char]
    if not rows:
        return ok("No matching symbol.", title="HTML Symbols")
    return ok("\n".join(rows), title="HTML Symbols")


_register(make_tool("html-symbols", html_symbols, title="HTML Symbols", hint="query (optional)"))


# --------------------------------------------------------------------------
# MIME / ports
# --------------------------------------------------------------------------

_MIMES = [
    ("text/html", ".html", "HTML document"), ("text/css", ".css", "Stylesheet"),
    ("text/javascript", ".js", "JavaScript"), ("text/plain", ".txt", "Plain text"),
    ("text/csv", ".csv", "CSV"), ("text/markdown", ".md", "Markdown"),
    ("text/calendar", ".ics", "iCalendar"), ("application/json", ".json", "JSON"),
    ("application/ld+json", ".jsonld", "JSON-LD"), ("application/xml", ".xml", "XML"),
    ("application/yaml", ".yaml", "YAML"), ("application/pdf", ".pdf", "PDF"),
    ("application/zip", ".zip", "ZIP archive"), ("application/gzip", ".gz", "Gzip"),
    ("application/x-tar", ".tar", "TAR archive"), ("application/x-7z-compressed", ".7z", "7-Zip archive"),
    ("application/octet-stream", ".bin", "Binary"), ("application/wasm", ".wasm", "WebAssembly"),
    ("application/msword", ".doc", "Word document"),
    ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx", "Word document"),
    ("application/vnd.ms-excel", ".xls", "Excel spreadsheet"),
    ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx", "Excel spreadsheet"),
    ("application/vnd.ms-powerpoint", ".ppt", "PowerPoint"),
    ("application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx", "PowerPoint"),
    ("application/epub+zip", ".epub", "EPUB"), ("image/png", ".png", "PNG image"),
    ("image/jpeg", ".jpg", "JPEG image"), ("image/gif", ".gif", "GIF image"),
    ("image/webp", ".webp", "WebP image"), ("image/avif", ".avif", "AVIF image"),
    ("image/svg+xml", ".svg", "SVG image"), ("image/x-icon", ".ico", "Icon"),
    ("image/tiff", ".tiff", "TIFF image"), ("audio/mpeg", ".mp3", "MP3 audio"),
    ("audio/wav", ".wav", "WAV audio"), ("audio/ogg", ".ogg", "Ogg audio"),
    ("audio/webm", ".weba", "WebM audio"), ("video/mp4", ".mp4", "MP4 video"),
    ("video/webm", ".webm", "WebM video"), ("video/quicktime", ".mov", "QuickTime video"),
    ("video/x-matroska", ".mkv", "Matroska video"), ("font/woff", ".woff", "WOFF font"),
    ("font/woff2", ".woff2", "WOFF2 font"), ("font/ttf", ".ttf", "TrueType font"),
]


def mime_reference(item: Input) -> Output:
    query = item.text.strip().lower().lstrip(".")
    rows = [
        f"{extension:<8} {mime:<60} {note}"
        for mime, extension, note in _MIMES
        if not query or query in mime.lower() or query in extension or query in note.lower()
    ]
    if not rows:
        return ok("No matching MIME type.", title="MIME Reference")
    return ok("\n".join(rows), title="MIME Reference")


_register(make_tool("mime-reference", mime_reference, title="MIME Types Reference", hint="query (optional)"))


_PORTS = [
    (20, "TCP", "FTP-DATA", "FTP data"), (21, "TCP", "FTP", "FTP control"),
    (22, "TCP", "SSH", "SSH/SFTP"), (23, "TCP", "Telnet", "Telnet"),
    (25, "TCP", "SMTP", "Mail transfer"), (53, "TCP/UDP", "DNS", "DNS"),
    (67, "UDP", "DHCP", "DHCP server"), (68, "UDP", "DHCP", "DHCP client"),
    (69, "UDP", "TFTP", "TFTP"), (80, "TCP", "HTTP", "HTTP"),
    (110, "TCP", "POP3", "POP3"), (123, "UDP", "NTP", "Time sync"),
    (135, "TCP", "RPC", "RPC"), (137, "UDP", "NetBIOS", "NetBIOS name"),
    (139, "TCP", "NetBIOS", "NetBIOS session"), (143, "TCP", "IMAP", "IMAP"),
    (161, "UDP", "SNMP", "SNMP"), (162, "UDP", "SNMP Trap", "SNMP traps"),
    (179, "TCP", "BGP", "BGP"), (389, "TCP/UDP", "LDAP", "LDAP"),
    (443, "TCP", "HTTPS", "HTTPS"), (445, "TCP", "SMB", "SMB"),
    (465, "TCP", "SMTPS", "SMTP over TLS"), (514, "UDP", "Syslog", "Syslog"),
    (587, "TCP", "SMTP", "SMTP submission"), (631, "TCP", "IPP", "Printing"),
    (636, "TCP", "LDAPS", "LDAP over TLS"), (993, "TCP", "IMAPS", "IMAP over TLS"),
    (995, "TCP", "POP3S", "POP3 over TLS"), (1080, "TCP", "SOCKS", "SOCKS proxy"),
    (1194, "UDP", "OpenVPN", "OpenVPN"), (1433, "TCP", "MSSQL", "SQL Server"),
    (1521, "TCP", "Oracle", "Oracle DB"), (2049, "TCP", "NFS", "NFS"),
    (2375, "TCP", "Docker", "Docker API"), (2376, "TCP", "Docker", "Docker API TLS"),
    (3000, "TCP", "Dev", "Dev server"), (3306, "TCP", "MySQL", "MySQL/MariaDB"),
    (3389, "TCP", "RDP", "Remote Desktop"), (5432, "TCP", "PostgreSQL", "PostgreSQL"),
    (5601, "TCP", "Kibana", "Kibana"), (5672, "TCP", "AMQP", "RabbitMQ"),
    (6379, "TCP", "Redis", "Redis"), (8080, "TCP", "HTTP-alt", "HTTP alternate"),
    (8443, "TCP", "HTTPS-alt", "HTTPS alternate"), (9000, "TCP", "Dev", "PHP-FPM/SonarQube"),
    (9200, "TCP", "Elasticsearch", "Elasticsearch"), (11211, "TCP/UDP", "Memcached", "Memcached"),
    (27017, "TCP", "MongoDB", "MongoDB"),
]


def ports_reference(item: Input) -> Output:
    query = to_ascii_digits(item.text.strip()).lower()
    rows = [
        f"{port:<6} {protocol:<8} {service:<14} {note}"
        for port, protocol, service, note in _PORTS
        if not query or query in str(port) or query in service.lower() or query in protocol.lower() or query in note.lower()
    ]
    if not rows:
        return ok("No matching port.", title="Ports Reference")
    return ok("\n".join(rows), title="Ports Reference")


_register(make_tool("ports-reference", ports_reference, title="Common Ports Reference", hint="query (optional)"))
