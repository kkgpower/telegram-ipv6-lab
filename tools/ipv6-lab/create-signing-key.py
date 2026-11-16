#!/usr/bin/env python3
"""Create a genuine local test signing key outside the repository, without logging passwords."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="Private directory outside the checkout")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    private = args.directory.expanduser().resolve()
    if private == repo or repo in private.parents:
        parser.error("The signing directory must be outside the repository")
    keytool = shutil.which("keytool")
    if not keytool:
        parser.error("keytool from a trusted JDK is required")
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    private.chmod(0o700)
    store = private / "ipv6-lab.p12"
    env_file = private / "signing.env"
    cert = private / "ipv6-lab-cert.der"
    if any(p.exists() for p in (store, env_file, cert)):
        parser.error("Signing files already exist; existing keys are preserved")
    os.umask(0o077)
    password = secrets.token_urlsafe(32)
    values = {
        "LAB_KEYSTORE": str(store), "LAB_KEY_ALIAS": "ipv6lab",
        "LAB_STORE_PASSWORD": password, "LAB_KEY_PASSWORD": password,
    }
    key_env = dict(os.environ, **values)
    subprocess.run([
        keytool, "-genkeypair", "-noprompt", "-storetype", "PKCS12",
        "-keystore", str(store), "-alias", values["LAB_KEY_ALIAS"],
        "-keyalg", "RSA", "-keysize", "3072", "-validity", "3650",
        "-dname", "CN=IPv6 Lab Local Test (unofficial)",
        "-storepass:env", "LAB_STORE_PASSWORD", "-keypass:env", "LAB_KEY_PASSWORD",
    ], env=key_env, check=True)
    store.chmod(0o600)
    subprocess.run([
        keytool, "-exportcert", "-keystore", str(store),
        "-alias", values["LAB_KEY_ALIAS"], "-file", str(cert),
        "-storepass:env", "LAB_STORE_PASSWORD",
    ], env=key_env, check=True)
    with env_file.open("x") as f:
        for name, value in values.items():
            f.write("export " + name + "=" + shlex.quote(value) + "\n")
    env_file.chmod(0o600)
    public_info = {
        "purpose": "Unofficial local IPv6 Lab test signing key; not a Telegram certificate",
        "alias": values["LAB_KEY_ALIAS"],
        "certificate_sha256": hashlib.sha256(cert.read_bytes()).hexdigest(),
        "signing_environment_file": str(env_file),
    }
    (private / "certificate-info.json").write_text(json.dumps(public_info, indent=2) + "\n")
    print(json.dumps(public_info, indent=2))


if __name__ == "__main__":
    main()
