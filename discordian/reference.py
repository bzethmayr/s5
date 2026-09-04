"""Reference Discordian date implementation, mirroring canonical ddate.c logic.

Given an 8-digit ISO date like 20260903 (YYYYMMDD), returns the structured
Discordian fields:
    (season, day_in_season, weekday, yold, is_tib)
  season        1-5   (Chaos..The Aftermath)
  day_in_season 1-73
  weekday       1-5   (Sweetmorn..Setting Orange)
  yold          year+1166
  is_tib        True iff St. Tib's Day (Feb 29 in a leap year)
"""

MONTHS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
SEASONS = [1, 2, 3, 4, 5]


def is_leap(y):
    return (y % 4 == 0 and y % 100 != 0) or y % 400 == 0


def ddate(yyyymmdd):
    if not isinstance(yyyymmdd, int):
        yyyymmdd = int(yyyymmdd)
    if not (10000000 <= yyyymmdd <= 99999999):
        raise ValueError(f"not an 8-digit date: {yyyymmdd}")
    year = yyyymmdd // 10000
    month = (yyyymmdd // 100) % 100
    day = yyyymmdd % 100
    if not (1 <= month <= 12):
        raise ValueError(f"bad month: {month}")
    if not (1 <= day <= MONTHS[month - 1] + (1 if month == 2 and is_leap(year) else 0)):
        raise ValueError(f"bad day: {day}/{month}")

    yold = year + 1166

    if is_leap(year) and month == 2 and day == 29:
        return (0, 0, 0, yold, True)

    days0 = sum(MONTHS[:month - 1]) + day - 1  # 0-indexed day of year (Feb=28 base)

    season = days0 // 73  # 0-indexed
    din = days0 % 73      # 0-indexed day within season
    weekday = days0 % 5 + 1

    return (SEASONS[season], din + 1, weekday, yold, False)


def format_fields(res):
    season, din, weekday, yold, is_tib = res
    if is_tib:
        return "0\n0\n0\n%d" % yold
    return "%d\n%d\n%d\n%d" % (season, din, weekday, yold)


if __name__ == "__main__":
    import sys
    date_in = sys.argv[1] if len(sys.argv) > 1 else "20260903"
    print(format_fields(ddate(date_in)))
