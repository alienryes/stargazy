#!/usr/bin/env python3
"""Render UpTonight's config.yaml from the [location] section of config.toml.

The site is configured in exactly one place. UpTonight needs the same latitude
and longitude the display uses to turn a declination into a peak altitude, and
two hand-maintained copies of a coordinate is one too many.

Usage: render_uptonight_config.py <config.toml> <template> <output.yaml>
"""

import sys
from pathlib import Path

import tomllib

PLACEHOLDERS = {
    "latitude": "__LATITUDE__",
    "longitude": "__LONGITUDE__",
    "elevation": "__ELEVATION__",
    "timezone": "__TIMEZONE__",
}


def main():
    if len(sys.argv) != 4:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    config, template, out = (Path(a) for a in sys.argv[1:])
    with open(config, "rb") as f:
        location = tomllib.load(f).get("location")
    if not location:
        print(f"{config} has no [location] section", file=sys.stderr)
        return 1

    text = template.read_text()
    for key, placeholder in PLACEHOLDERS.items():
        if key not in location:
            print(f"[location] is missing '{key}'", file=sys.stderr)
            return 1
        text = text.replace(placeholder, str(location[key]))

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(f"Wrote {out} for {location['latitude']}, {location['longitude']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
