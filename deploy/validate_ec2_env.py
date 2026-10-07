"""Check an explicit EC2 env file without starting services or printing secrets.

Read the literal, one-line format used by deploy/ec2/.env.example. Reject missing
Compose inputs, empty secret sources and invalid query/cursor identifiers. Ask
Compose to render the deployment files in memory, then check the merged
ports and AWS mounts. Inherited application variables never satisfy a missing
file value. Public IP HTTPS requires the explicit fifth layer and flag; private mode still
rejects public bindings. This validates configuration, not live TLS or IAM.
"""

import base64
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import UUID


ROOT = Path(__file__).resolve().parents[1]
FILES = ("compose.yaml", "compose.sql.yaml", "compose.web.yaml", "compose.ec2.yaml")
INTERPOLATION = re.compile(r"\$\{([A-Z][A-Z0-9_]*)(?:(:\?|:-)([^}]*))?\}")


def read_literal_env(path):
    """Accept literal assignments; reject ambiguity without echoing input."""
    values = {}
    for number, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", name) or name in values:
            raise ValueError("Invalid or duplicate assignment at line %s" % number)
        # Single quotes keep JSON and special characters literal in Compose.
        if value.startswith("'") and value.endswith("'") and "'" not in value[1:-1]:
            value = value[1:-1]
        elif any(char in value for char in "\"'\\$#") or value != value.strip():
            raise ValueError("Use a literal single-quoted value at line %s" % number)
        values[name] = value
    return values


def validate(path, *, public_https=False):
    """Return errors containing variable names only; retain rendered secrets in memory."""
    values = read_literal_env(path)
    errors = []
    inputs = {}
    files = FILES + (("compose.public.yaml",) if public_https else ())
    for filename in files:
        # Ignore YAML comments and escaped shell dollars, including $$@.
        source = "\n".join(line for line in (ROOT / filename).read_text().splitlines()
                           if not line.lstrip().startswith("#")).replace("$$", "")
        for name, operator, default in INTERPOLATION.findall(source):
            inputs.setdefault(name, []).append((operator, default))
    for name, uses in sorted(inputs.items()):
        # HOME is only used by the base laptop mount, replaced by the EC2 file.
        value = values.get(name, os.environ.get("HOME", "") if name == "HOME" else "")
        if not value and any(operator != ":-" for operator, _ in uses):
            errors.append("Unresolved required interpolation: " + name)
    for name in ("TRINITY_POSTGRES_PASSWORD", "EIA_API_KEY"):
        if not values.get(name, "").strip():
            errors.append("Missing secret source: " + name)
        elif values[name].startswith("REDACTED_PENDING_"):
            errors.append("Review placeholder is not a secret: " + name)
    # A shape check cannot prove that this image exists on EC2.
    query_image = values.get("TRINITY_QUERY_IMAGE", "")
    if query_image and not re.fullmatch(r"sha256:[0-9a-f]{64}", query_image):
        errors.append("Invalid immutable image ID: TRINITY_QUERY_IMAGE")
    try:
        UUID(values.get("TRINITY_QUERY_DEPLOYMENT_ID", ""))
    except ValueError:
        errors.append("Invalid UUID: TRINITY_QUERY_DEPLOYMENT_ID")
    for purpose in ("PREVIEW", "REFRESH"):
        name = "TRINITY_%s_CURSOR_KEYS_JSON" % purpose
        active = values.get("TRINITY_%s_CURSOR_ACTIVE_KEY_ID" % purpose, "")
        if not values.get(name):
            continue  # Already reported as a required interpolation.
        try:
            raw = values[name]
            pairs = json.loads(raw, object_pairs_hook=list)
            keys = dict(pairs)
            if not raw.startswith("{") or len(raw.encode()) > 4096 or len(keys) != len(pairs):
                raise ValueError
            if not 1 <= len(keys) <= 4 or active not in keys:
                raise ValueError
            for identifier, key in keys.items():
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", identifier):
                    raise ValueError
                if not re.fullmatch(r"[A-Za-z0-9_-]{43}", key):
                    raise ValueError
                decoded = base64.urlsafe_b64decode(key + "=")
                if len(decoded) != 32 or base64.urlsafe_b64encode(decoded).decode().rstrip("=") != key:
                    raise ValueError
        except (ValueError, TypeError, RecursionError):
            errors.append("Invalid cursor key ring or active ID: " + name)
    if values.get("TRINITY_PREVIEW_ENABLED") not in ("true", "false"):
        errors.append("Invalid boolean: TRINITY_PREVIEW_ENABLED")
    if not values.get("TRINITY_DOCKER_GID", "").isdigit():
        errors.append("Invalid numeric group: TRINITY_DOCKER_GID")
    if errors:
        return inputs, errors

    # Do not inherit shell overrides or the checkout's development .env file.
    environment = {key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ}
    command = ["docker", "compose", "--env-file", str(path), "--project-name", "trinity-ec2"]
    for filename in files:
        command.extend(("-f", filename))
    command.extend(("--profile", "workers", "config", "--format", "json"))
    result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True)
    if result.returncode:
        return inputs, ["Compose rejected the file; raw output withheld to protect secrets."]
    model = json.loads(result.stdout)
    services = model["services"]
    for name in ("api", "postgres", "redis"):
        if services[name].get("ports"):
            errors.append("Unexpected host port: " + name)
    web = services["web"]
    if public_https:
        # Public mode is explicit and includes the matching certificate config.
        # Reject plaintext site addresses and unexpected service exposure.
        try:
            if not ipaddress.ip_address(values.get("TRINITY_SITE_ADDRESS", "")).is_global:
                raise ValueError
        except ValueError:
            errors.append("Public IP HTTPS requires a global IP site address.")
        ports = {(port.get("host_ip"), str(port.get("published")), port.get("target"),
                  port.get("protocol", "tcp")) for port in web.get("ports", [])}
        if ports != {("0.0.0.0", "80", 80, "tcp"), ("0.0.0.0", "443", 443, "tcp"),
                     ("127.0.0.1", "8080", 8080, "tcp")}:
            errors.append("Unexpected public HTTPS or private preview port bindings.")
        mounts = [item for item in web.get("volumes", []) if item["target"] == "/etc/caddy/Caddyfile"]
        if (len(mounts) != 1 or not mounts[0].get("read_only")
                or mounts[0].get("source") != str(ROOT / "deploy/ec2/Caddyfile.public")):
            errors.append("Public HTTPS requires the reviewed read-only Caddy configuration.")
    else:
        for port in web.get("ports", []):
            if port.get("host_ip") != "127.0.0.1":
                errors.append("The private preview requires loopback-only Caddy ports.")
    for name in ("api", "refresh", "recovery", "publication"):
        service = services[name]
        env = service["environment"]
        mounts = service.get("volumes", [])
        configs = [item for item in mounts if item["target"] == "/run/trinity-aws/config"]
        if len(configs) != 1 or not configs[0].get("read_only"):
            errors.append("Missing read-only AWS config mount: " + name)
        if env.get("AWS_SHARED_CREDENTIALS_FILE") != "/dev/null" or env.get("AWS_LOGIN_CACHE_DIRECTORY"):
            errors.append("Unexpected AWS credential source: " + name)
        if any(item["target"] in ("/home/trinity/.aws", "/run/query-aws", "/run/query-aws-login") for item in mounts):
            errors.append("Laptop credential mount retained: " + name)
    return inputs, errors


def main():
    """Print only the audit count and safe diagnostics; return nonzero on failure."""
    public_https = len(sys.argv) == 3 and sys.argv[2] == "--public-https"
    if len(sys.argv) != 2 and not public_https:
        print("Usage: python3 deploy/validate_ec2_env.py /path/to/env [--public-https]")
        return 2
    try:
        inputs, errors = validate(Path(sys.argv[1]).resolve(), public_https=public_https)
    except (OSError, ValueError):
        print("FAIL: Cannot read or parse the configuration; values withheld.")
        return 1
    print("Audited %s distinct Compose interpolation variables." % len(inputs))
    for error in errors:
        print("FAIL: " + error)
    if not errors:
        print("PASS: File inputs and merged Compose structure. IAM/images/runtime remain unverified.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
