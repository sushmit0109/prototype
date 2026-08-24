"""
Political-era boundaries, for slicing procurement activity by government
rather than by calendar year. Boundaries as given: the Awami League
government through its fall, the interim government that followed, and the
elected government since. The one-week gap between the Awami League's last
day and the interim government's swearing-in (2024-08-08) is attached to
the interim era rather than left as an orphan.
"""
ERAS = [
    ("Awami League (2009–2024)", "0000-01-01", "2024-08-07"),
    ("Interim Government (2024–2026)", "2024-08-08", "2026-02-16"),
    ("Elected Government (2026–)", "2026-02-17", "9999-12-31"),
]


def era_of(iso_date):
    """iso_date: 'YYYY-MM-DD' string (or None) -> era name or None."""
    if not iso_date:
        return None
    for name, start, end in ERAS:
        if start <= iso_date <= end:
            return name
    return None


ERA_NAMES = [name for name, _, _ in ERAS]
