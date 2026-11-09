# -*- coding: utf-8 -*-
"""Network diagnostics and IP tools."""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import urllib.parse

from .common import http_head, http_json, ok, split_pipe, to_ascii_digits
from .meta import make_tool
from .model import Input, Output, Tool, ToolError

TOOLS: list[Tool] = []


def _register(*tools: Tool) -> None:
    TOOLS.extend(tools)


# --------------------------------------------------------------------------
# HTTP headers
# --------------------------------------------------------------------------

def http_headers(item: Input) -> Output:
    url = item.require_text().strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        status, headers, final_url = http_head(url)
    except Exception as exc:
        raise ToolError(f"Request failed: {exc}") from exc
    lines = [f"Status: {status}", f"Final URL: {final_url}", ""]
    lines.extend(f"{key}: {value}" for key, value in headers.items())
    return ok("\n".join(lines), title="HTTP Headers")


_register(make_tool("http-headers", http_headers, title="HTTP Headers Inspector", hint="URL"))


# --------------------------------------------------------------------------
# DNS / reverse DNS / WHOIS
# --------------------------------------------------------------------------

_DNS_TYPES = {"A", "AAAA", "MX", "TXT", "NS", "CNAME", "SOA", "PTR"}
_TYPE_NAMES = {1: "A", 2: "NS", 5: "CNAME", 6: "SOA", 12: "PTR", 15: "MX", 16: "TXT", 28: "AAAA"}


def _doh_json(name: str, record_type: str) -> dict:
    """DNS-over-HTTPS with a Cloudflare then Google fallback."""
    encoded = urllib.parse.quote(name, safe="")
    errors = []
    endpoints = [
        (f"https://cloudflare-dns.com/dns-query?name={encoded}&type={record_type}", {"Accept": "application/dns-json"}),
        (f"https://dns.google/resolve?name={encoded}&type={record_type}", {}),
    ]
    for url, headers in endpoints:
        try:
            return http_json(url, headers=headers)
        except Exception as exc:
            errors.append(str(exc))
    raise ToolError("DNS lookup failed: " + "; ".join(errors))


def dns_lookup(item: Input) -> Output:
    domain, record_type = split_pipe(item.require_text(), 2, from_right=False, strip=True)
    if not domain:
        raise ToolError("A domain is required.")
    record_type = (record_type or "A").upper()
    if record_type not in _DNS_TYPES:
        raise ToolError(f"Unsupported DNS record type: {record_type}")
    try:
        import dns.resolver  # type: ignore

        answers = dns.resolver.resolve(domain, record_type)
        ttl = answers.rrset.ttl if answers.rrset else "-"
        lines = [f"{domain}\t{record_type}\t{ttl}\t{answer}" for answer in answers]
        return ok("\n".join(lines), title="DNS Lookup", message=f"{len(lines)} answer(s)")
    except Exception:
        pass
    data = _doh_json(domain, record_type)
    answers = data.get("Answer") or []
    if not answers:
        return ok(f"No {record_type} records found for {domain}.", title="DNS Lookup")
    lines = [f"{answer.get('name')}\t{_TYPE_NAMES.get(answer.get('type'), answer.get('type'))}\t{answer.get('TTL')}\t{answer.get('data')}" for answer in answers]
    return ok("\n".join(lines), title="DNS Lookup", message=f"{len(answers)} answer(s)")


_register(make_tool("dns-lookup", dns_lookup, title="DNS Lookup", hint="domain|type"))


def reverse_dns(item: Input) -> Output:
    value = to_ascii_digits(item.require_text().strip())
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ToolError("Invalid IPv4 address.") from exc
    if address.version == 4:
        arpa = ".".join(reversed(str(address).split("."))) + ".in-addr.arpa"
    else:
        arpa = address.reverse_pointer
    names = []
    try:
        import dns.resolver  # type: ignore

        answers = dns.resolver.resolve(arpa, "PTR")
        names = [str(answer) for answer in answers]
    except Exception:
        try:
            data = _doh_json(arpa, "PTR")
            answers = data.get("Answer") or []
            names = [answer.get("data") for answer in answers if answer.get("data")]
        except Exception:
            names = []
    if not names:
        try:
            host, aliases, _ = socket.gethostbyaddr(str(address))
            names = [host] + aliases
        except Exception:
            names = []
    if not names:
        return ok(f"{arpa}\nNo PTR record found.", title="Reverse DNS")
    return ok("\n".join([f"Query: {arpa}", *names]), title="Reverse DNS")


_register(make_tool("reverse-dns", reverse_dns, title="Reverse DNS Lookup", hint="IPv4 address"))


def whois_rdap(item: Input) -> Output:
    domain = re.sub(r"^https?://", "", item.require_text().strip()).split("/")[0]
    if not domain:
        raise ToolError("A domain is required.")
    try:
        data = http_json(f"https://rdap.org/domain/{domain}")
    except Exception as exc:
        raise ToolError(f"RDAP lookup failed: {exc}") from exc
    lines = [f"Domain: {data.get('ldhName', domain)}"]
    for entity in data.get("entities") or []:
        if "registrar" in (entity.get("roles") or []):
            vcard = entity.get("vcardArray") or []
            name = "-"
            if len(vcard) > 1:
                for row in vcard[1]:
                    if row and row[0] == "fn":
                        name = row[3]
                        break
            lines.append(f"Registrar: {name}")
    for event in data.get("events") or []:
        lines.append(f"{event.get('eventAction')}: {event.get('eventDate')}")
    statuses = data.get("status") or []
    if statuses:
        lines.append("Status: " + ", ".join(statuses))
    nameservers = [ns.get("ldhName") for ns in data.get("nameservers") or [] if ns.get("ldhName")]
    if nameservers:
        lines.append("Nameservers: " + ", ".join(nameservers))
    return ok("\n".join(lines), title="WHOIS (RDAP)")


_register(make_tool("whois-rdap", whois_rdap, title="WHOIS (RDAP)", hint="domain"))


# --------------------------------------------------------------------------
# Public IP / IP info
# --------------------------------------------------------------------------

def public_ip(item: Input) -> Output:
    lines = []
    try:
        v4 = http_json("https://api.ipify.org?format=json")
        value = v4.get("ip")
        lines.append(f"IPv4: {value}" if value and ":" not in value else f"IPv4: not available ({value})")
    except Exception as exc:
        lines.append(f"IPv4 lookup failed: {exc}")
    try:
        v6 = http_json("https://api64.ipify.org?format=json")
        value = v6.get("ip")
        lines.append(f"IPv6: {value}" if value and ":" in value else "IPv6: not available")
    except Exception as exc:
        lines.append(f"IPv6 lookup failed: {exc}")
    return ok("\n".join(lines), title="My Public IP")


_register(make_tool("public-ip", public_ip, title="My Public IP", hint="no input needed"))


def ip_info(item: Input) -> Output:
    value = item.text.strip()
    url = f"https://ipapi.co/{value}/json/" if value else "https://ipapi.co/json/"
    try:
        data = http_json(url)
    except Exception:
        try:
            data = http_json(f"https://ip-api.com/json/{value}" if value else "https://ip-api.com/json/")
        except Exception as exc:
            raise ToolError(f"IP lookup failed: {exc}") from exc
    if data.get("error"):
        raise ToolError(str(data.get("reason") or data.get("error")))
    rows = [
        ("IP", data.get("ip") or data.get("query")),
        ("Country", data.get("country_name") or data.get("country")),
        ("Country code", data.get("country_code") or data.get("countryCode")),
        ("Region", data.get("region") or data.get("regionName")),
        ("City", data.get("city")),
        ("Timezone", data.get("timezone")),
        ("Latitude", data.get("latitude") or data.get("lat")),
        ("Longitude", data.get("longitude") or data.get("lon")),
        ("ASN", data.get("asn") or (f"AS{data.get('as')}" if data.get("as") else None)),
        ("Organization", data.get("org") or data.get("isp")),
    ]
    lines = [f"{label}: {value}" for label, value in rows if value not in (None, "")]
    return ok("\n".join(lines), title="IP Info")


_register(make_tool("ip-info", ip_info, title="IP Info", hint="IP (optional)"))


# --------------------------------------------------------------------------
# IP conversion / subnet
# --------------------------------------------------------------------------

def ip_to_int(item: Input) -> Output:
    value = to_ascii_digits(item.require_text().strip())
    if value.startswith("0x") or re.fullmatch(r"[0-9a-fA-F]+", value) and not re.fullmatch(r"\d+", value):
        try:
            number = int(value, 16)
        except ValueError as exc:
            raise ToolError("Invalid hex value.") from exc
    elif re.fullmatch(r"\d+", value):
        number = int(value)
    else:
        try:
            number = int(ipaddress.IPv4Address(value))
        except ValueError as exc:
            raise ToolError("Invalid IPv4 address.") from exc
    if number > 0xFFFFFFFF:
        raise ToolError("Value is larger than 32 bits.")
    address = str(ipaddress.IPv4Address(number))
    return ok(
        f"IPv4: {address}\nInteger: {number}\nHex: 0x{number:08x}",
        title="IPv4 ↔ Integer",
    )


_register(make_tool("ip-to-int", ip_to_int, title="IPv4 ↔ Integer", hint="IPv4, integer or hex"))


def ipv4_subnet(item: Input) -> Output:
    value = to_ascii_digits(item.require_text().strip())
    if "/" in value:
        host, prefix = value.split("/", 1)
    else:
        parts = split_pipe(value, 2, from_right=False, strip=True)
        host, prefix = parts[0], parts[1] or "24"
    try:
        interface = ipaddress.IPv4Interface(f"{host}/{prefix}")
    except ValueError as exc:
        raise ToolError("Invalid IPv4 address or prefix.") from exc
    network = interface.network
    if network.prefixlen <= 30:
        first = network.network_address + 1
        last = network.broadcast_address - 1
    elif network.prefixlen == 31:
        first = network.network_address
        last = network.broadcast_address
    else:
        first = last = network.network_address
    return ok(
        "\n".join(
            [
                f"Network: {network.network_address}/{network.prefixlen}",
                f"Broadcast: {network.broadcast_address}",
                f"First host: {first}",
                f"Last host: {last}",
                f"Netmask: {network.netmask}",
                f"Wildcard: {network.hostmask}",
                f"IP (integer): {int(interface.ip)}",
                f"Total addresses: {network.num_addresses}",
                f"Usable hosts: {max(0, network.num_addresses - 2) if network.prefixlen < 31 else network.num_addresses}",
            ]
        ),
        title="IPv4 Subnet",
    )


_register(make_tool("ipv4-subnet", ipv4_subnet, title="IPv4 Subnet Calculator", hint="IP or IP/prefix"))


def ipv6_cidr(item: Input) -> Output:
    value = to_ascii_digits(item.require_text().strip())
    try:
        interface = ipaddress.IPv6Interface(value)
    except ValueError as exc:
        raise ToolError("Invalid IPv6 address or prefix.") from exc
    network = interface.network
    return ok(
        "\n".join(
            [
                f"Expanded: {network.network_address.exploded}",
                f"Compressed: {network.network_address.compressed}",
                f"Prefix: /{network.prefixlen}",
                f"Addresses: {network.num_addresses}",
                f"Network: {network}",
            ]
        ),
        title="IPv6 CIDR",
    )


_register(make_tool("ipv6-cidr", ipv6_cidr, title="IPv6 CIDR Calculator", hint="IPv6 or IPv6/prefix"))


def ip_validator(item: Input) -> Output:
    value = to_ascii_digits(item.require_text().strip())
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return ok(f"Invalid IP address: {value}", title="IP Validator")
    return ok(
        f"Valid IPv{address.version}: {address.compressed}",
        title="IP Validator",
    )


_register(make_tool("ip-validator", ip_validator, title="IP Validator", hint="IPv4 or IPv6"))


def mac_formatter(item: Input) -> Output:
    hex_digits = re.sub(r"[^0-9a-fA-F]", "", item.require_text())
    if len(hex_digits) != 12:
        raise ToolError("MAC address must contain 12 hexadecimal digits.")
    lower = hex_digits.lower()
    pairs = [lower[index : index + 2] for index in range(0, 12, 2)]
    quads = [lower[index : index + 4] for index in range(0, 12, 4)]
    return ok(
        "\n".join(
            [
                f"Colon: {':'.join(pairs)}",
                f"Hyphen: {'-'.join(pairs)}",
                f"Dot: {'.'.join(quads)}",
                f"Plain: {lower}",
                f"Upper: {lower.upper()}",
            ]
        ),
        title="MAC Formatter",
    )


_register(make_tool("mac-formatter", mac_formatter, title="MAC Address Formatter", hint="MAC address"))


def private_ip_checker(item: Input) -> Output:
    value = to_ascii_digits(item.require_text().strip())
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ToolError("Invalid IPv4 or IPv6 address.") from exc
    if address.version == 4:
        if address.is_private:
            kind = "Private (RFC1918)"
        elif address.is_loopback:
            kind = "Loopback"
        elif address.is_link_local:
            kind = "Link-local"
        elif address.is_multicast:
            kind = "Multicast"
        elif address.is_reserved:
            kind = "Reserved"
        else:
            kind = "Public"
    else:
        if address.is_loopback:
            kind = "Loopback"
        elif address.is_link_local:
            kind = "Link-local"
        elif address.is_private:
            kind = "Unique Local (private)"
        elif address.is_multicast:
            kind = "Multicast"
        elif address.is_global:
            kind = "Global Unicast (public)"
        else:
            kind = "Reserved"
    return ok(f"{address.compressed}\n{kind}", title="Private IP Checker")


_register(make_tool("private-ip-checker", private_ip_checker, title="Private IP Checker", hint="IP address"))
