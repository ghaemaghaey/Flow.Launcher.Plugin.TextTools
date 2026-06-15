# -*- coding: utf-8 -*-

import sys, os
parent_folder_path = os.path.abspath(os.path.dirname(__file__))
sys.path.append(parent_folder_path)
sys.path.append(os.path.join(parent_folder_path, 'lib'))
sys.path.append(os.path.join(parent_folder_path, 'plugin'))

from flowlauncher import FlowLauncher
import pyperclip
import re

class TextTools(FlowLauncher):

    def query(self, query):
        try:
            text = pyperclip.paste()
        except:
            text = ""

        tools = [
            {"name": "Arabic to Persian", "subtitle": "Replace ك→ک and ي→ی", "method": "arabic_to_persian"},
            {"name": "Add comma to each line", "subtitle": "Append , to end of every line", "method": "add_comma"},
            {"name": "UPPERCASE", "subtitle": "Convert text to uppercase", "method": "to_upper"},
            {"name": "lowercase", "subtitle": "Convert text to lowercase", "method": "to_lower"},
            {"name": "Remove empty lines", "subtitle": "Delete all blank lines", "method": "remove_empty_lines"},
            {"name": "Trim each line", "subtitle": "Remove leading/trailing spaces from each line", "method": "trim_lines"},
            {"name": "Remove all spaces", "subtitle": "Remove full spaces, half spaces, and zero-width chars", "method": "remove_spaces"},
        ]

        return [
            {
                "Title": tool["name"],
                "SubTitle": tool["subtitle"],
                "IcoPath": "Images/app.png",
                "JsonRPCAction": {
                    "method": tool["method"],
                    "parameters": [text]
                }
            }
            for tool in tools
            if query.lower() in tool["name"].lower() or query == ""
        ]

    def arabic_to_persian(self, text):
        pyperclip.copy(text.replace("ك", "ک").replace("ي", "ی"))

    def add_comma(self, text):
        pyperclip.copy("\n".join(line + "," for line in text.splitlines()))

    def to_upper(self, text):
        pyperclip.copy(text.upper())

    def to_lower(self, text):
        pyperclip.copy(text.lower())

    def remove_empty_lines(self, text):
        pyperclip.copy("\n".join(l for l in text.splitlines() if l.strip()))

    def trim_lines(self, text):
        pyperclip.copy("\n".join(l.strip() for l in text.splitlines()))

    def remove_spaces(self, text):
        # Remove: regular space, half-space (ZWNJ U+200C), zero-width space (U+200B),
        # non-breaking space (U+00A0), em space, en space, thin space, and all unicode spaces
        cleaned = re.sub(r'[\s\u200c\u200b\u00a0\u2000-\u200a\u202f\u205f\u3000\ufeff]', '', text)
        pyperclip.copy(cleaned)

if __name__ == "__main__":
    TextTools()