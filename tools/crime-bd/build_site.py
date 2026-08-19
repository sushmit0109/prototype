#!/usr/bin/env python3
"""
Inject the dataset and the map geometry into the page template.

The result is one self-contained HTML file. That is deliberate: the dashboard
has to survive being opened from disk, from GitHub Pages, or from a copy someone
emails to a colleague, and a page that fetches its own data does not.

    python3 build_site.py <template.html> <crime.json> <geo.json> <out.html>
"""
import json
import os
import sys


def main(template, data_path, geo_path, out_path):
    html = open(template, encoding="utf-8").read()
    data = json.load(open(data_path, encoding="utf-8"))
    geo = json.load(open(geo_path, encoding="utf-8"))

    for marker in ("/*__DATA__*/", "/*__GEO__*/"):
        if marker not in html:
            raise SystemExit(f"template is missing the {marker} placeholder")

    # `</script>` inside a JSON string would close the host <script> tag early.
    def embed(obj):
        return json.dumps(obj, separators=(",", ":")).replace("</", "<\\/")

    html = html.replace("/*__DATA__*/", embed(data))
    html = html.replace("/*__GEO__*/", embed(geo))

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(f"built {out_path}  ({os.path.getsize(out_path):,} bytes)")
    print(f"  {data['meta']['months']} months, "
          f"{data['meta']['first_month']} .. {data['meta']['last_month']}")


if __name__ == "__main__":
    main(*sys.argv[1:5])
