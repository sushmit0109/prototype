"""
Parsing helpers for the portal's paged-search HTML fragments.

Every source built on the SearchNOA/DebarmentRpt/TenderDetailsServlet family
returns the same shape: a bare <tr>...</tr> sequence (no enclosing <table>),
one <td> per column, sometimes with <br/>-joined sub-values inside a cell.
Shared here once instead of re-implemented per source crawler.
"""
import re

ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def clean(html_fragment):
    text = TAG_RE.sub(" ", html_fragment)
    text = (text.replace("&amp;", "&").replace("&nbsp;", " ")
                .replace("&#39;", "'").replace("&quot;", '"'))
    return WS_RE.sub(" ", text).strip()


def split_br(html_fragment):
    parts = re.split(r"<br\s*/?>", html_fragment, flags=re.I)
    return [clean(p) for p in parts if clean(p)]


def split_br_clean(html_fragment):
    """split_br, then drop a trailing separator comma some cells embed before the <br/>."""
    return [p[:-1].strip() if p.endswith(",") else p for p in split_br(html_fragment)]


def total_pages(body):
    m = re.search(r'id="totalPages"\s+value="(\d+)"', body)
    return int(m.group(1)) if m else 1
