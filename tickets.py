"""check-prose's ticket backlog: `pdm run tickets`."""

from pathlib import Path

from ticketkit import TicketSystem

SYSTEM = TicketSystem(
    repo=Path(__file__).resolve().parent,
    areas=["scope", "counting", "cli", "tests", "docs", "packaging"],
    severities=["blocker", "critical", "major", "minor", "trivial"],
)

if __name__ == "__main__":
    import sys

    sys.exit(SYSTEM.main())
