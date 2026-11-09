# -*- coding: utf-8 -*-
"""End-to-end checks that exercise the plugin exactly as Flow Launcher does:
`python main.py '<json-rpc request>'` plus real clipboard reads/writes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIP_FILE = os.path.join(tempfile.gettempdir(), "texttools-e2e-clipboard.txt")
ENV = dict(os.environ)
ENV["TEXTTOOLS_NO_OPEN"] = "1"
ENV["TEXTTOOLS_CLIPBOARD_FILE"] = CLIP_FILE
ENV["PYTHONIOENCODING"] = "utf-8"


def call(method: str, parameters: list):
    request = json.dumps({"method": method, "parameters": parameters})
    result = subprocess.run(
        [sys.executable, "main.py", request],
        cwd=ROOT,
        env=ENV,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise AssertionError(f"plugin exited {result.returncode}: {result.stderr}")
    return result.stdout


def run_tool(tool_id: str, clipboard: str) -> str:
    with open(CLIP_FILE, "w", encoding="utf-8", newline="") as fh:
        fh.write(clipboard)
    output = call("run_tool", [tool_id])
    with open(CLIP_FILE, encoding="utf-8") as fh:
        return fh.read(), output


def test_query_and_manifest():
    output = call("query", ["base64"])
    payload = json.loads(output)
    results = payload["result"]
    assert results, "no query results"
    assert any(item["Title"] == "Base64 Encode" for item in results), [r["Title"] for r in results]
    first = results[0]
    assert first["JsonRPCAction"]["method"] == "run_tool"
    assert first["JsonRPCAction"]["parameters"], "missing tool id"

    empty = json.loads(call("query", [""]))["result"]
    assert len(empty) > 200, len(empty)

    with open(os.path.join(ROOT, "plugin.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    assert manifest["ActionKeyword"] == "tt"
    assert manifest["ExecuteFileName"] == "main.py"
    assert os.path.isfile(os.path.join(ROOT, manifest["ExecuteFileName"]))
    assert os.path.isfile(os.path.join(ROOT, manifest["IcoPath"].replace("\\", os.sep)))


def test_text_and_encoding():
    value, _ = run_tool("base64", "hello world")
    assert value == "aGVsbG8gd29ybGQ=", value

    value, _ = run_tool("base64-decode", "aGVsbG8=")
    assert value == "hello", value

    value, _ = run_tool("case-camel", "hello world_example")
    assert value == "helloWorldExample", value

    value, _ = run_tool("line-sort-asc", "b\na")
    assert value == "a\nb", value

    value, _ = run_tool("find-replace", "foo|bar|foo foo")
    assert value == "bar bar", value

    value, _ = run_tool("hash-text", "abc")
    assert "SHA-256: ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad" in value


def test_crypto_and_generators():
    value, _ = run_tool("hmac", "secret|message|SHA-256")
    assert value.startswith("SHA-256: "), value

    value, _ = run_tool("uuid", "1|1|0")
    assert len(value) == 36 and value.count("-") == 4, value

    value, _ = run_tool("totp", "JBSWY3DPEHPK3PXP|30|6|SHA-1")
    assert value.splitlines()[0].isdigit(), value


def test_data_and_units():
    value, _ = run_tool("json-formatter", '{"b":1,"a":2}')
    assert '"b": 1' in value and value.startswith("{"), value

    value, _ = run_tool("csv-json", "name,age\nAli,30")
    assert '"name": "Ali"' in value, value

    value, _ = run_tool("unit-converter", "length|10|m")
    assert "Kilometer: 0.01" in value, value

    value, _ = run_tool("timestamp", "1700000000")
    assert "Unix seconds: 1700000000" in value, value


def test_visual_tool_writes_a_file():
    temp_dir = os.path.join(tempfile.gettempdir(), "TextTools")
    before = set(os.listdir(temp_dir)) if os.path.isdir(temp_dir) else set()
    run_tool("identicon", "rasmio")
    after = set(os.listdir(temp_dir)) if os.path.isdir(temp_dir) else set()
    created = [name for name in after - before if name.startswith("identicon-")]
    assert created, f"no identicon file created (before={len(before)}, after={len(after)})"


def test_error_is_reported():
    output = run_tool("base64-decode", "not-base64!!!")[1]
    assert "ShowMsg" in output, output


def test_pyperclip_code_path():
    """The real clipboard path (without touching the OS clipboard in CI)."""
    sys.path.insert(0, ROOT)
    sys.path.insert(0, os.path.join(ROOT, "lib"))
    import tools.common as common

    original_paste = common.pyperclip.paste
    original_copy = common.pyperclip.copy
    copied = []
    try:
        common.pyperclip.paste = lambda: "clipboard text"
        common.pyperclip.copy = lambda value: copied.append(value)
        item = common.read_clipboard()
        assert item.text == "clipboard text", item
        common.copy_text("result text")
        assert copied == ["result text"], copied
    finally:
        common.pyperclip.paste = original_paste
        common.pyperclip.copy = original_copy


def test_registry_coverage():
    sys.path.insert(0, ROOT)
    sys.path.insert(0, os.path.join(ROOT, "lib"))
    from tools.registry import ALL_TOOLS, SKIPPED, missing_metadata_ids

    assert not missing_metadata_ids(), missing_metadata_ids()
    assert len(ALL_TOOLS) > 250
    assert "base64" in {tool.id for tool in ALL_TOOLS}
    assert "cors-tester" in SKIPPED


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"\n{len(tests)} end-to-end tests passed")
