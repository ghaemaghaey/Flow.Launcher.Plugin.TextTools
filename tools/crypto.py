# -*- coding: utf-8 -*-
"""Hashing, crypto and security helper tools."""

from __future__ import annotations

import base64
import hashlib
import hmac as hmac_lib
import math
import os
import re
import secrets
import time
import urllib.parse

from .common import err, ok, parse_int, split_pipe, temp_path
from .meta import make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


# --------------------------------------------------------------------------
# Hashes
# --------------------------------------------------------------------------

def hash_text(item: Input) -> Output:
    data = item.require_text().encode("utf-8")
    lines = [
        f"MD5: {hashlib.md5(data).hexdigest()}",
        f"SHA-1: {hashlib.sha1(data).hexdigest()}",
        f"SHA-256: {hashlib.sha256(data).hexdigest()}",
        f"SHA-384: {hashlib.sha384(data).hexdigest()}",
        f"SHA-512: {hashlib.sha512(data).hexdigest()}",
    ]
    return ok("\n".join(lines), title="Text Hash")


_register(make_tool("hash-text", hash_text, title="Text Hash (MD5 / SHA)", hint="clipboard text"))


_HASH_ALGOS = {
    "SHA-1": hashlib.sha1,
    "SHA-256": hashlib.sha256,
    "SHA-384": hashlib.sha384,
    "SHA-512": hashlib.sha512,
    "MD5": hashlib.md5,
}


def _hash_name(value: str) -> str:
    key = (value or "SHA-256").strip().upper().replace("_", "-")
    if key in _HASH_ALGOS:
        return key
    if key in {"SHA1"}:
        return "SHA-1"
    if key in {"SHA256"}:
        return "SHA-256"
    if key in {"SHA384"}:
        return "SHA-384"
    if key in {"SHA512"}:
        return "SHA-512"
    raise ToolError(f"Unknown hash algorithm: {value}")


def hmac_tool(item: Input) -> Output:
    secret, message, algorithm = split_pipe(item.require_text(), 3, from_right=False, strip=False)
    if not secret and not message:
        raise ToolError("Use secret|message|algorithm in the clipboard.")
    name = _hash_name(algorithm)
    digest = hmac_lib.new(
        secret.encode("utf-8"), message.encode("utf-8"), _HASH_ALGOS[name]
    ).hexdigest()
    return ok(f"{name}: {digest}", title="HMAC")


_register(make_tool("hmac", hmac_tool, title="HMAC Generator", hint="secret|message|algorithm"))


def pbkdf2_tool(item: Input) -> Output:
    parts = split_pipe(item.require_text(), 5, from_right=False, strip=False)
    password, salt, iterations_text, algorithm, keylen_text = parts
    if not password or not salt:
        raise ToolError("Use password|salt|iterations|algorithm|keylen in the clipboard.")
    iterations = parse_int(iterations_text or "100000")
    if iterations < 1:
        raise ToolError("Iterations must be at least 1.")
    keylen = parse_int(keylen_text or "32")
    if keylen < 1 or keylen > 256:
        raise ToolError("Key length must be between 1 and 256 bytes.")
    name = _hash_name(algorithm or "SHA-256")
    derived = hashlib.pbkdf2_hmac(name.replace("-", "").lower(), password.encode("utf-8"), salt.encode("utf-8"), iterations, dklen=keylen)
    return ok(derived.hex(), title="PBKDF2")


_register(make_tool("pbkdf2", pbkdf2_tool, title="PBKDF2", hint="password|salt|iterations|algorithm|keylen"))


# --------------------------------------------------------------------------
# Password strength / entropy / secret scan
# --------------------------------------------------------------------------

def password_strength(item: Input) -> Output:
    password = item.require_text()
    pool = 0
    if re.search(r"[a-z]", password):
        pool += 26
    if re.search(r"[A-Z]", password):
        pool += 26
    if re.search(r"[0-9]", password):
        pool += 10
    if re.search(r"[^a-zA-Z0-9]", password):
        pool += 33
    entropy = len(password) * math.log2(pool or 1)
    seconds = (2 ** entropy) / 1e10
    if entropy < 28:
        band = "Very weak"
    elif entropy < 36:
        band = "Weak"
    elif entropy < 60:
        band = "Fair"
    elif entropy < 128:
        band = "Strong"
    else:
        band = "Very strong"
    return ok(
        "\n".join(
            [
                f"Length: {len(password)}",
                f"Character pool: {pool}",
                f"Entropy: {round(entropy)} bits",
                f"Strength: {band}",
                f"Offline crack estimate: {_human_time(seconds)}",
            ]
        ),
        title="Password Strength",
    )


def _human_time(seconds: float) -> str:
    if seconds < 1:
        return "instantly"
    units = [(60, "seconds"), (60, "minutes"), (24, "hours"), (365, "days"), (1000, "years")]
    value = seconds
    label = "seconds"
    for factor, name in units:
        if value < factor:
            label = name
            break
        value /= factor
        label = name
    if value > 1e6:
        return "longer than the age of the universe"
    return f"{value:,.0f} {label}"


_register(make_tool("password-strength", password_strength, title="Password Strength", hint="clipboard password"))


def entropy_calculator(item: Input) -> Output:
    text = item.require_text()
    if not text:
        raise ToolError("Clipboard is empty.")
    counts: dict[str, int] = {}
    for char in text:
        counts[char] = counts.get(char, 0) + 1
    per_char = 0.0
    for count in counts.values():
        probability = count / len(text)
        per_char -= probability * math.log2(probability)
    return ok(
        "\n".join(
            [
                f"Bits per character: {per_char:.2f}",
                f"Total entropy: {per_char * len(text):.1f} bits",
                f"Characters: {len(text)}",
                f"Unique characters: {len(counts)}",
            ]
        ),
        title="Entropy Calculator",
    )


_register(make_tool("entropy-calculator", entropy_calculator, title="Entropy Calculator", hint="clipboard text"))


_SECRET_PATTERNS = [
    ("AWS Access Key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("Google API Key", r"\bAIza[0-9A-Za-z\-_]{35}\b"),
    ("JWT", r"\beyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\b"),
    ("PEM Private Key", r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    ("Slack Token", r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"),
    ("Hex Token (32+)", r"\b[0-9a-fA-F]{32,}\b"),
    ("Base64 Token (40+)", r"\b[A-Za-z0-9+/]{40,}={0,2}\b"),
]


def _mask(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= 12:
        return value[0] + "*" * max(1, len(value) - 2) + value[-1]
    return f"{value[:6]}...{value[-4:]} ({len(value)})"


def secret_scanner(item: Input) -> Output:
    text = item.require_text()
    findings = []
    seen = set()
    for label, pattern in _SECRET_PATTERNS:
        for match in re.finditer(pattern, text):
            value = match.group(0)
            key = f"{label}:{value}"
            if key in seen:
                continue
            seen.add(key)
            findings.append(f"{label}: {_mask(value)}")
    if not findings:
        return ok("No obvious secrets found.", title="Secret Scanner")
    return ok("\n".join(findings), title="Secret Scanner", message=f"{len(findings)} finding(s)")


_register(make_tool("secret-scanner", secret_scanner, title="Secret Scanner", hint="clipboard text"))


# --------------------------------------------------------------------------
# OTP
# --------------------------------------------------------------------------

def _base32_secret(secret: str) -> bytes:
    clean = re.sub(r"\s+", "", secret).upper().rstrip("=")
    clean += "=" * (-len(clean) % 8)
    try:
        data = base64.b32decode(clean, casefold=True)
    except Exception as exc:
        raise ToolError(f"Invalid Base32 secret: {exc}") from exc
    if not data:
        raise ToolError("The Base32 secret is empty.")
    return data


def _hotp(secret: bytes, counter: int, digits: int, algorithm: str = "SHA-1") -> str:
    digest = hmac_lib.new(secret, counter.to_bytes(8, "big"), _HASH_ALGOS[_hash_name(algorithm)]).digest()
    offset = digest[-1] & 0x0F
    code = (
        ((digest[offset] & 0x7F) << 24)
        | ((digest[offset + 1] & 0xFF) << 16)
        | ((digest[offset + 2] & 0xFF) << 8)
        | (digest[offset + 3] & 0xFF)
    )
    return str(code % (10 ** digits)).zfill(digits)


def totp_tool(item: Input) -> Output:
    secret, period_text, digits_text, algorithm = split_pipe(item.require_text(), 4, from_right=False, strip=False)
    if not secret:
        raise ToolError("Use secret|period|digits|algorithm in the clipboard.")
    period = parse_int(period_text or "30")
    digits = parse_int(digits_text or "6")
    if period < 1 or digits < 1 or digits > 10:
        raise ToolError("Period must be >= 1 and digits 1-10.")
    key = _base32_secret(secret)
    counter = int(time.time()) // period
    code = _hotp(key, counter, digits, algorithm or "SHA-1")
    remaining = period - (int(time.time()) % period)
    return ok(f"{code}\n(valid for {remaining}s)", title="TOTP")


_register(make_tool("totp", totp_tool, title="TOTP Generator", hint="secret|period|digits|algorithm"))


def hotp_tool(item: Input) -> Output:
    secret, counter_text, digits_text, algorithm = split_pipe(item.require_text(), 4, from_right=False, strip=False)
    if not secret:
        raise ToolError("Use secret|counter|digits|algorithm in the clipboard.")
    counter = parse_int(counter_text or "0")
    digits = parse_int(digits_text or "6")
    if counter < 0 or digits < 1 or digits > 10:
        raise ToolError("Counter must be >= 0 and digits 1-10.")
    return ok(_hotp(_base32_secret(secret), counter, digits, algorithm or "SHA-1"), title="HOTP")


_register(make_tool("hotp", hotp_tool, title="HOTP Generator", hint="secret|counter|digits|algorithm"))


def otp_uri(item: Input) -> Output:
    otp_type, issuer, account, secret = split_pipe(item.require_text(), 4, from_right=False, strip=False)
    otp_type = (otp_type or "totp").strip().lower()
    if otp_type not in {"totp", "hotp"}:
        otp_type = "totp"
    secret = re.sub(r"\s+", "", secret).upper()
    if not secret or not account:
        raise ToolError("Use type|issuer|account|secret in the clipboard.")
    label = urllib.parse.quote(f"{issuer}:{account}" if issuer else account, safe="")
    params = {"secret": secret}
    if issuer:
        params["issuer"] = issuer
    if otp_type == "hotp":
        params["counter"] = "0"
    uri = f"otpauth://{otp_type}/{label}?{urllib.parse.urlencode(params)}"
    path = None
    try:
        import qrcode  # type: ignore

        path = temp_path("png", "otp-uri")
        qrcode.make(uri).save(path)
    except Exception:
        path = None
    return Output(text=uri, title="OTP URI", open_path=path, message=uri[:180])


_register(make_tool("otp-uri", otp_uri, title="OTP URI + QR", hint="type|issuer|account|secret"))


# --------------------------------------------------------------------------
# Diceware
# --------------------------------------------------------------------------

_WORDS = [
    "apple", "river", "stone", "cloud", "tiger", "amber", "ocean", "maple", "ember", "frost",
    "grape", "honey", "ivory", "jolly", "koala", "lemon", "mango", "noble", "olive", "pearl",
    "quartz", "raven", "sunny", "tulip", "umber", "vivid", "willow", "xenon", "yacht", "zebra",
    "anchor", "bridge", "candle", "dragon", "eagle", "forest", "garden", "harbor", "island", "jungle",
    "kettle", "ladder", "meadow", "needle", "orange", "pepper", "quiver", "rocket", "silver", "thunder",
    "violet", "walnut", "yellow", "almond", "bamboo", "carbon", "diamond", "engine", "falcon", "galaxy",
    "hammer", "indigo", "jacket", "kitten", "lantern", "marble", "nectar", "onion", "pebble", "quilt",
    "ribbon", "saddle", "temple", "udder", "velvet", "wagon", "yarn", "acorn", "bison", "cedar",
    "daisy", "elbow", "fable", "glove", "hazel", "igloo", "jewel", "knot", "lilac", "moss",
    "north", "otter", "plum", "quail", "robin", "shell", "trout", "unity", "vase", "wheat",
    "zest", "angle", "berry", "cabin", "dune", "echo", "flame", "grain", "hill", "iron",
    "jade", "kite", "leaf", "mint", "nest", "oak", "pine", "reed", "sand", "vine",
]


def diceware(item: Input) -> Output:
    count_text, separator = split_pipe(item.require_text(), 2, from_right=False, strip=False)
    count = 5
    if count_text.strip():
        try:
            count = max(1, min(20, int(count_text.strip())))
        except ValueError:
            count = 5
    sep = separator if separator != "" else "-"
    words = [secrets.choice(_WORDS) for _ in range(count)]
    return ok(sep.join(words), title="Diceware Passphrase")


_register(make_tool("diceware", diceware, title="Diceware Passphrase", hint="count|separator"))


# --------------------------------------------------------------------------
# RSA / ECDSA / AES-GCM
# --------------------------------------------------------------------------

def _require_cryptography():
    try:
        from cryptography.hazmat.primitives import serialization  # type: ignore
        from cryptography.hazmat.primitives.asymmetric import ec, rsa  # type: ignore
        return serialization, ec, rsa
    except Exception as exc:
        raise ToolError("The 'cryptography' package is required for this tool.") from exc


def rsa_keygen(item: Input) -> Output:
    serialization, _ec, rsa = _require_cryptography()
    bits_text = item.text.strip()
    bits = 2048
    if bits_text.isdigit():
        bits = max(1024, min(8192, int(bits_text)))
    key = rsa.generate_private_key(public_exponent=65537, key_size=bits)
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    return ok(
        f"PUBLIC KEY:\n{public_pem}\nPRIVATE KEY:\n{private_pem}",
        title=f"RSA {bits}-bit Key Pair",
    )


_register(make_tool("rsa-keygen", rsa_keygen, title="RSA Key Pair", hint="bits (optional)"))


def ecdsa_keygen(item: Input) -> Output:
    serialization, ec, _rsa = _require_cryptography()
    curve_name = (item.text.strip() or "P-256").upper().replace("SECP", "P-")
    curves = {
        "P-256": ec.SECP256R1,
        "P-384": ec.SECP384R1,
        "P-521": ec.SECP521R1,
    }
    factory = curves.get(curve_name, ec.SECP256R1)
    key = ec.generate_private_key(factory())
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    return ok(
        f"PUBLIC KEY:\n{public_pem}\nPRIVATE KEY:\n{private_pem}",
        title="ECDSA Key Pair",
    )


_register(make_tool("ecdsa-keygen", ecdsa_keygen, title="ECDSA Key Pair", hint="curve (P-256/P-384/P-521)"))


def _aes_key(passphrase: str, salt: bytes):
    try:
        from cryptography.hazmat.primitives import hashes  # type: ignore
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC  # type: ignore
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore
    except Exception as exc:
        raise ToolError("The 'cryptography' package is required for AES-GCM.") from exc
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=150000)
    key = kdf.derive(passphrase.encode("utf-8"))
    return AESGCM(key)


def aes_gcm_encrypt(item: Input) -> Output:
    passphrase, plaintext = split_pipe(item.require_text(), 2, from_right=True, strip=False)
    if not passphrase:
        raise ToolError("Use passphrase|plaintext in the clipboard.")
    salt = os.urandom(16)
    nonce = os.urandom(12)
    aes = _aes_key(passphrase, salt)
    ciphertext = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
    packed = base64.b64encode(salt + nonce + ciphertext).decode("ascii")
    return ok(packed, title="AES-GCM Encrypt")


def aes_gcm_decrypt(item: Input) -> Output:
    passphrase, encoded = split_pipe(item.require_text(), 2, from_right=True, strip=False)
    if not passphrase:
        raise ToolError("Use passphrase|base64 in the clipboard.")
    try:
        packed = base64.b64decode(re.sub(r"\s+", "", encoded) + "=" * (-len(encoded) % 4))
    except Exception as exc:
        raise ToolError(f"Invalid Base64: {exc}") from exc
    if len(packed) < 28:
        raise ToolError("Ciphertext is too short.")
    salt, nonce, ciphertext = packed[:16], packed[16:28], packed[28:]
    aes = _aes_key(passphrase, salt)
    try:
        plaintext = aes.decrypt(nonce, ciphertext, None)
    except Exception as exc:
        raise ToolError("Decryption failed (wrong passphrase or corrupted data).") from exc
    return ok(plaintext.decode("utf-8", "replace"), title="AES-GCM Decrypt")


_register(make_tool("aes-gcm", aes_gcm_encrypt, title="AES-GCM Encrypt", hint="passphrase|plaintext"))
_register(make_tool("aes-gcm", aes_gcm_decrypt, id="aes-gcm-decrypt", title="AES-GCM Decrypt", hint="passphrase|base64"))
