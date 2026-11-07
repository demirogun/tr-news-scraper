"""The data the outlets module works with: months, article candidates and outlet definitions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import MAXYEAR, MINYEAR, date, timedelta


@dataclass(frozen=True, slots=True, order=True)
class Month:
    """A calendar month, such as ``Month(2023, 2)``. Months are ordered and hashable."""

    year: int
    month: int

    def __post_init__(self) -> None:
        if not MINYEAR <= self.year <= MAXYEAR or not 1 <= self.month <= 12:
            raise ValueError(f"{self.year}-{self.month} is not a calendar month")

    @classmethod
    def of(cls, day: date) -> Month:
        """The month ``day`` falls in."""
        return cls(day.year, day.month)

    @classmethod
    def span(cls, start: date, end: date) -> list[Month]:
        """Every month the range ``[start, end)`` touches, oldest first."""
        if start >= end:
            raise ValueError(f"the start ({start}) must be before the end ({end})")
        last = cls.of(end - timedelta(days=1))
        months = [cls.of(start)]
        while months[-1] < last:
            months.append(months[-1].next())
        return months

    @property
    def start(self) -> date:
        """The first day of the month."""
        return date(self.year, self.month, 1)

    def next(self) -> Month:
        """The month after this one."""
        if self.month == 12:
            return Month(self.year + 1, 1)
        return Month(self.year, self.month + 1)

    def previous(self) -> Month:
        """The month before this one."""
        if self.month == 1:
            return Month(self.year - 1, 12)
        return Month(self.year, self.month - 1)

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"
