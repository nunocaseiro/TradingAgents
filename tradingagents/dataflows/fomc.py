"""Scheduled FOMC meetings, for placing a run's events against the next rate decision.

The Fed publishes its calendar more than a year ahead, so a date in this table
was public long before any run that sees it, and serving it carries no
look-ahead. No free API serves the calendar, so the table is copied from
https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm and extended
when the Fed publishes a new year (``test_the_table_reaches_at_least_six_months_ahead``
fails when it is due). Each date is tentative until the meeting before confirms
it; unscheduled meetings cannot be listed.
"""

# (first day, decision day, with a Summary of Economic Projections), as published
# on 2026-10-07.
FOMC_MEETINGS = (
    ("2026-01-27", "2026-01-28", False),
    ("2026-03-17", "2026-03-18", True),
    ("2026-04-28", "2026-04-29", False),
    ("2026-06-16", "2026-06-17", True),
    ("2026-07-28", "2026-07-29", False),
    ("2026-09-15", "2026-09-16", True),
    ("2026-10-27", "2026-10-28", False),
    ("2026-12-08", "2026-12-09", True),
    ("2027-01-26", "2027-01-27", False),
    ("2027-03-16", "2027-03-17", True),
    ("2027-04-27", "2027-04-28", False),
    ("2027-06-08", "2027-06-09", True),
    ("2027-07-27", "2027-07-28", False),
    ("2027-09-14", "2027-09-15", True),
    ("2027-10-26", "2027-10-27", False),
    ("2027-12-07", "2027-12-08", True),
    ("2028-01-25", "2028-01-26", False),
)

# How many upcoming decisions to list.
UPCOMING = 2


def _describe(start: str, end: str, projections: bool) -> str:
    extra = ", with economic projections" if projections else ""
    return f"{end} (meeting {start} to {end}{extra})"


def schedule_note(as_of_date: str) -> str:
    """The last and next scheduled FOMC decisions around ``as_of_date``, or "" before the table.

    A decision on the analysis date counts as upcoming: the statement is
    released at 14:00 ET, after a run made that day.
    """
    if as_of_date < FOMC_MEETINGS[0][0]:
        return ""
    past = [m for m in FOMC_MEETINGS if m[1] < as_of_date]
    upcoming = [m for m in FOMC_MEETINGS if m[1] >= as_of_date][:UPCOMING]
    lines = []
    if past:
        lines.append(f"Last FOMC decision: {past[-1][1]}.")
    if upcoming:
        lines.append("Next scheduled FOMC decisions: "
                     + "; ".join(_describe(*m) for m in upcoming)
                     + ". Dates are from the Fed's published calendar; each is tentative until "
                       "the meeting before it confirms it, and unscheduled meetings are not listed.")
    else:
        lines.append(f"FOMC meetings after {FOMC_MEETINGS[-1][1]} are not in this build's "
                     "calendar; do not guess their dates.")
    return " ".join(lines)
