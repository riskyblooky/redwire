"""
NetExec (nxc) / CrackMapExec (CME) log parser.

Handles output from any nxc protocol (smb, ssh, ldap, mssql, ftp, winrm, etc.)
in either of the two formats nxc emits:

  1. Console output / piped stdout:
       PROTOCOL  HOST  PORT  HOSTNAME  [STATUS]  DETAIL

  2. `--log <file>` file output (with a logger prefix):
       2026-04-29 21:40:52 | ssh.py:60 - INFO - SSH 192.168.69.125 22 ... [+] pi:hunter2

Status markers:
    [*] = info (server banner, version)
    [-] = failed auth
    [+] = success
    (Pwn3d!) suffix = admin/high-priv (some protocols append a description after it,
                                      e.g. "Linux - Shell access!" on SSH)

Examples:
    SMB   10.10.10.252  445  DC01  [-] LAB.LOCAL\\user1:Summer2025! STATUS_LOGON_FAILURE
    SMB   10.10.10.252  445  DC01  [+] LAB.LOCAL\\admin1:Summer2025! (Pwn3d!)
    SSH   192.168.69.190 22   192.168.69.190 [+] pi:P@$$w0rd! (Pwn3d!) Linux - Shell access!
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ParsedSprayResult:
    username: str
    domain: Optional[str] = None
    result: str = "failed"            # success / success_admin / failed / locked / disabled
    status_code: Optional[str] = None
    is_admin: bool = False
    # Per-result target and credential — populated for every parsed line so we
    # don't lose info when the campaign sprays multiple hosts or wordlists.
    target_host: Optional[str] = None
    target_port: Optional[int] = None
    password: Optional[str] = None


@dataclass
class ParsedSprayCampaign:
    protocol: Optional[str] = None
    target_host: Optional[str] = None        # Best-effort summary (CLI target if known, else inferred)
    target_port: Optional[int] = None
    target_hostname: Optional[str] = None
    domain: Optional[str] = None
    password_used: Optional[str] = None      # Set only when ALL results share one password; else None
    total_attempts: int = 0
    successful: int = 0
    locked_out: int = 0
    failed: int = 0
    host_count: int = 0                      # Number of distinct hosts touched
    command_line: Optional[str] = None       # Raw `nxc ...` command from the log preamble, if present
    command_target: Optional[str] = None     # Target spec from the command line (e.g. "192.168.69.0/24")
    results: List[ParsedSprayResult] = field(default_factory=list)


# Strips the `--log` file prefix: "YYYY-MM-DD HH:MM:SS | foo.py:NN - LEVEL - "
# When present we drop it so the protocol-line regex below applies uniformly to
# both stdout and log-file inputs.
_LOG_PREFIX_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s*\|\s*\S+\s*-\s*\w+\s*-\s*"
)

# Matches nxc's command-line preamble that gets written to --log files:
#   "[2026-04-29 21:40:51]> /home/risky/.local/bin/nxc ssh 192.168.69.0/24 -u pi -p P@$$w0rd! --log nxc.log"
_COMMAND_PREAMBLE_RE = re.compile(
    r"^\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\]>\s*(.+)$"
)

# Regex to match nxc authentication result lines
# Groups: protocol, host, port, hostname, status_char (+/-/*), detail
_LINE_RE = re.compile(
    r"^(\w+)\s+"           # protocol (SMB, SSH, LDAP, MSSQL, FTP, WINRM, ...)
    r"([\d.]+)\s+"         # IP address
    r"(\d+)\s+"            # port
    r"(\S+)\s+"            # hostname (often == IP for SSH)
    r"\[([+\-*!])\]\s+"   # status indicator
    r"(.+)$"               # detail
)

# Regex to extract domain\user:password [trailing] from detail.
# Password is captured as the first non-whitespace run after `:`, so trailing
# text (e.g. SSH's "Linux - Shell access!" after Pwn3d, or SMB's STATUS_X) is
# captured separately for inspection.
_CRED_RE = re.compile(
    r"^(?:(\S+?)\\)?(\S+?):(\S+)(?:\s+(.*))?\s*$"
)

# Status codes that indicate lockout
_LOCKOUT_CODES = {
    "STATUS_ACCOUNT_LOCKED_OUT",
    "STATUS_ACCOUNT_LOCKED",
}

# Status codes that indicate disabled
_DISABLED_CODES = {
    "STATUS_ACCOUNT_DISABLED",
}


def _parse_command_line(command: str) -> Optional[str]:
    """
    Extract the target spec from an nxc command line.

    nxc's CLI shape is roughly:
        nxc <protocol> <target> [-u user|userlist] [-p pass|passlist] [flags...]

    The target is the first positional after the protocol. We don't try to
    distinguish single IPs / CIDRs / files — we just capture whatever was
    passed so the user sees their original intent (e.g. "192.168.69.0/24").
    Returns None if the command shape doesn't match.
    """
    import shlex
    try:
        tokens = shlex.split(command)
    except ValueError:
        # shlex can fail on unbalanced quotes — fall back to whitespace split
        tokens = command.split()

    # Find the nxc binary in the tokens (could be /path/to/nxc, ./nxc, or nxc)
    for i, tok in enumerate(tokens):
        if tok.endswith("nxc") or tok.endswith("netexec") or tok.endswith("crackmapexec") or tok.endswith("cme"):
            # Next token is the protocol; the one after that is the target
            if i + 2 < len(tokens):
                return tokens[i + 2]
            break
    return None


def parse_netexec_log(content: str) -> ParsedSprayCampaign:
    """Parse a NetExec/CME log file and return structured campaign data."""
    campaign = ParsedSprayCampaign()
    passwords_seen = set()
    hosts_seen = set()
    lines = content.strip().splitlines()

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Strip ANSI color codes if present
        line = re.sub(r"\x1b\[[0-9;]*m", "", line)

        # Capture the command-line preamble that nxc writes at the start of a
        # --log file, e.g. "[2026-04-29 21:40:51]> nxc ssh 192.168.69.0/24 -u pi -p ..."
        # We use this to recover the actual target spec the user typed (e.g. a
        # CIDR), which the per-line output doesn't preserve.
        if campaign.command_line is None:
            cmd_match = _COMMAND_PREAMBLE_RE.match(line)
            if cmd_match:
                campaign.command_line = cmd_match.group(1).strip()
                campaign.command_target = _parse_command_line(campaign.command_line)
                continue

        # Strip the `--log` file prefix ("2026-04-29 21:40:52 | ssh.py:60 - INFO - ")
        # so the protocol-line regex below works on both stdout and log-file input.
        line = _LOG_PREFIX_RE.sub("", line)

        match = _LINE_RE.match(line)
        if not match:
            continue

        protocol, host, port_str, hostname, status_char, detail = match.groups()
        port_int = int(port_str)

        # Populate campaign-level protocol from first matching line. The
        # target host/port is set per-result below and reconciled at the end.
        if campaign.protocol is None:
            campaign.protocol = protocol.upper()
            campaign.target_port = port_int
            campaign.target_hostname = hostname

        # Track every distinct host the run touched so we can summarise later.
        hosts_seen.add(host)

        # [*] lines are info/banner — skip for result parsing
        if status_char == "*":
            continue

        # Parse credential detail
        # Check for (Pwn3d!) anywhere in the detail
        is_admin = "(Pwn3d!)" in detail
        # Clean the detail for credential parsing
        clean_detail = detail.replace("(Pwn3d!)", "").strip()

        cred_match = _CRED_RE.match(clean_detail)
        if not cred_match:
            # Try simpler parsing: domain\user:password
            # Some nxc output has spaces in unusual places
            parts = clean_detail.split(":", 1)
            if len(parts) < 2:
                continue
            user_part = parts[0]
            password_part = parts[1].strip().split(" ")[0] if parts[1] else ""
            if "\\" in user_part:
                domain_str, username = user_part.rsplit("\\", 1)
            else:
                domain_str, username = None, user_part
            status_code = None
            remaining = parts[1].strip()
            status_parts = remaining.split(" ", 1)
            if len(status_parts) > 1 and status_parts[1].startswith("STATUS_"):
                status_code = status_parts[1].strip()
        else:
            domain_str = cred_match.group(1)
            username = cred_match.group(2)
            password_part = cred_match.group(3).strip()
            # `trailing` may be any leftover text (e.g. "STATUS_LOGON_FAILURE",
            # "Linux - Shell access!" on SSH success). Only the first token
            # matters here: if it starts with STATUS_ we treat it as a status
            # code; otherwise it's protocol-specific descriptive text we ignore.
            trailing = cred_match.group(4) or ""
            first_token = trailing.split()[0] if trailing else ""
            status_code = first_token if first_token.startswith("STATUS_") else None

        # Track passwords and domain
        if password_part:
            passwords_seen.add(password_part)
        if domain_str and not campaign.domain:
            campaign.domain = domain_str

        # Determine result type
        if status_char == "+":
            result_type = "success_admin" if is_admin else "success"
        elif status_code and any(code in status_code for code in _LOCKOUT_CODES):
            result_type = "locked"
        elif status_code and any(code in status_code for code in _DISABLED_CODES):
            result_type = "disabled"
        else:
            result_type = "failed"

        spray_result = ParsedSprayResult(
            username=username,
            domain=domain_str,
            result=result_type,
            status_code=status_code,
            is_admin=is_admin,
            target_host=host,
            target_port=port_int,
            password=password_part or None,
        )
        campaign.results.append(spray_result)

    # Compute aggregates
    campaign.total_attempts = len(campaign.results)
    campaign.successful = sum(1 for r in campaign.results if r.result.startswith("success"))
    campaign.locked_out = sum(1 for r in campaign.results if r.result == "locked")
    campaign.failed = sum(1 for r in campaign.results if r.result in ("failed", "disabled"))
    campaign.host_count = len(hosts_seen)

    # Campaign-level password is meaningful only when every attempt used the
    # same password. Otherwise leave it None — per-result `password` is the
    # source of truth (used by auto-vault, etc.).
    if len(passwords_seen) == 1:
        campaign.password_used = next(iter(passwords_seen))
    else:
        campaign.password_used = None

    # Pick a campaign-level target_host that represents the run's intent:
    #   1. The CLI target spec from the command preamble (e.g. "192.168.69.0/24")
    #   2. The single host if the run only touched one
    #   3. None — the frontend can render "{host_count} hosts" when this is null
    if campaign.command_target:
        campaign.target_host = campaign.command_target
    elif len(hosts_seen) == 1:
        campaign.target_host = next(iter(hosts_seen))
    else:
        campaign.target_host = None

    return campaign


# ── Scanner import (host/service enumeration) ────────────────────────────────
#
# `nxc <proto> <targets>` without credentials prints one `[*]` banner line per
# responding host, e.g.
#   SMB  10.0.0.5  445  DC01  [*] Windows Server 2019 Build 17763 x64 (name:DC01) (domain:lab.local) (signing:True) (SMBv1:False)
#   RDP  10.0.0.7  3389 WS01  [*] Windows 10 Build 19041 (name:WS01) (domain:lab.local) (nla:False)
#   SSH  10.0.0.9  22   10.0.0.9 [*] SSH-2.0-OpenSSH_8.9p1 Ubuntu-3ubuntu0.1
# parse() turns those into assets + ports, and the security-relevant flags into
# findings. Credential lines ([+]/[-]) are not imported here — the spray import
# is the place for those, and finding text is no place for passwords.

_FLAG_RE = re.compile(r"\((\w[\w ]*?):([^)]*)\)")

# (protocol, flag, bad value) → finding template. Values compare lowercased.
_FLAG_FINDINGS = {
    ("smb", "signing", "false"): (
        "SMB Signing Not Required", "MEDIUM",
        "The host does not require SMB message signing. An attacker in a position to "
        "relay NTLM authentication (e.g. via LLMNR/NBT-NS poisoning or coerced "
        "authentication) can relay it to this host's SMB service.",
        "Require SMB signing on all hosts (Group Policy: \"Microsoft network server: "
        "Digitally sign communications (always)\" = Enabled).",
    ),
    ("smb", "smbv1", "true"): (
        "SMBv1 Enabled", "MEDIUM",
        "The host accepts SMB version 1, a deprecated protocol with known remote code "
        "execution vulnerabilities (e.g. MS17-010 / EternalBlue) and no modern security features.",
        "Disable SMBv1 on the server and clients (Disable-WindowsOptionalFeature -Online "
        "-FeatureName SMB1Protocol) after confirming no legacy dependencies.",
    ),
    ("smb", "null auth", "true"): (
        "SMB Null Session Allowed", "MEDIUM",
        "The host accepts unauthenticated (null) SMB sessions, which can expose domain "
        "information such as users, groups and password policy to anonymous users.",
        "Restrict anonymous access (RestrictAnonymous / RestrictAnonymousSAM, and "
        "\"Network access: Allow anonymous SID/Name translation\" = Disabled).",
    ),
    ("rdp", "nla", "false"): (
        "RDP Network Level Authentication Not Required", "LOW",
        "Remote Desktop does not require Network Level Authentication, so the login "
        "screen and pre-authentication attack surface are exposed to unauthenticated users.",
        "Require NLA for Remote Desktop connections (System Properties → Remote, or the "
        "\"Require user authentication for remote connections by using NLA\" policy).",
    ),
}


def looks_like_netexec(text: str) -> bool:
    """True when any of the first lines is an nxc/CME protocol line."""
    for line in text.splitlines()[:200]:
        if _LINE_RE.match(_LOG_PREFIX_RE.sub("", line.strip())):
            return True
    return False


def parse(content: bytes):
    """Parse nxc console/--log output into scanner-import data."""
    from utils.parsers import ParsedAsset, ParsedFinding, ParsedImportData, ParsedPort

    result = ParsedImportData(source_tool="nxc")
    text = content.decode("utf-8", errors="ignore")
    asset_index: dict[str, int] = {}
    finding_index: dict[str, int] = {}
    info: dict[int, list[str]] = {}
    cred_lines = 0

    for raw in text.splitlines():
        line = _LOG_PREFIX_RE.sub("", raw.strip())
        cmd = _COMMAND_PREAMBLE_RE.match(raw.strip())
        if cmd and "command" not in result.raw_metadata:
            # Strip credentials from the recorded command line.
            result.raw_metadata["command"] = re.sub(r"(\s-(?:p|H|-password|-hash)\s+)\S+", r"\1****", cmd.group(1))
            continue
        m = _LINE_RE.match(line)
        if not m:
            continue
        proto, ip, port_s, hostname, status, detail = m.groups()
        proto = proto.lower()
        if status in ("+", "-"):
            cred_lines += 1
            continue
        if status != "*":
            continue

        if ip not in asset_index:
            asset_index[ip] = len(result.assets)
            name = hostname if hostname and hostname != ip else ip
            result.assets.append(ParsedAsset(name=name, asset_type="IP Address", identifier=ip))
            info[asset_index[ip]] = []
        idx = asset_index[ip]
        asset = result.assets[idx]

        flags = {k.strip().lower(): v.strip() for k, v in _FLAG_RE.findall(detail)}
        banner = _FLAG_RE.sub("", detail).strip()
        port = int(port_s)
        if not any(p.port_number == port for p in asset.ports):
            asset.ports.append(ParsedPort(
                port_number=port, protocol="TCP", service_name=proto, state="OPEN",
                version=banner[:255] or None,
            ))
        if banner:
            info[idx].append(f"- {proto.upper()} {port}: {banner}")
        for key in ("domain", "name"):
            if flags.get(key) and f"{key}:{flags[key]}" not in info[idx]:
                info[idx].append(f"{key}:{flags[key]}")

        for (fproto, flag, bad), (title, sev, desc, fix) in _FLAG_FINDINGS.items():
            if proto == fproto and flags.get(flag, "").lower() == bad:
                if title not in finding_index:
                    finding_index[title] = len(result.findings)
                    result.findings.append(ParsedFinding(
                        title=title, severity=sev, description=desc, mitigations=fix,
                        category="Network", affected_asset_indices=[],
                    ))
                f = result.findings[finding_index[title]]
                if idx not in f.affected_asset_indices:
                    f.affected_asset_indices.append(idx)

    for idx, lines in info.items():
        services = [l for l in lines if l.startswith("- ")]
        meta = [l for l in lines if not l.startswith("- ")]
        parts = ["Imported from NetExec (nxc)"]
        if meta:
            parts.append(" · ".join(meta))
        if services:
            parts.append("\n".join(services))
        result.assets[idx].description = "\n\n".join(parts)

    if cred_lines:
        result.warnings.append(
            f"Skipped {cred_lines} credential result line(s) — import nxc credential "
            "output through the Spray import instead."
        )
    if not result.assets:
        result.warnings.append("No nxc host banner ([*]) lines found.")
    result.raw_metadata.update({"total_hosts": len(result.assets)})
    return result
