"""Verify vendored JavaScript hashes and check versions against OSV, without npm.

Run from any directory with Python 3.11+. Network/response errors fail the check.
"""

import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen


def main() -> int:
    vendor_dir = Path(__file__).resolve().parents[1] / "static" / "vendor"
    packages = json.loads((vendor_dir / "manifest.json").read_text(encoding="utf-8"))
    for package in packages:
        asset = (vendor_dir / package["file"]).resolve()
        if asset.parent != vendor_dir.resolve():
            raise ValueError("Vendor asset must be inside static/vendor")
        if hashlib.sha256(asset.read_bytes()).hexdigest() != package["sha256"]:
            raise ValueError(f"Vendored asset hash mismatch: {package['file']}")

    query = {
        "queries": [
            {"package": {"name": p["name"], "ecosystem": "npm"}, "version": p["version"]}
            for p in packages
        ]
    }
    request = Request(
        "https://api.osv.dev/v1/querybatch",
        data=json.dumps(query).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=60) as response:  # noqa: S310 — fixed HTTPS endpoint
        results = json.load(response)["results"]
    if len(results) != len(packages):
        raise ValueError("Incomplete OSV response")
    failed = False
    for package, result in zip(packages, results, strict=True):
        if result.get("next_page_token"):
            raise ValueError("Incomplete OSV result: additional advisory pages exist")
        vulnerabilities = result.get("vulns", [])
        failed |= bool(vulnerabilities)
        print(
            f"{package['name']}=={package['version']}: "
            + (", ".join(v["id"] for v in vulnerabilities) or "no known vulnerabilities")
        )
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
