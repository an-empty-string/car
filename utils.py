import datetime


def time_taken_sec(t_start, t_end):
    now = datetime.datetime.now()

    if t_start is None:
        t_start = now
    else:
        t_start = datetime.datetime.fromisoformat(t_start)

    if t_end is None:
        t_end = now
    else:
        t_end = datetime.datetime.fromisoformat(t_end)

    return (t_end - t_start).total_seconds()


def format_date(ts, seconds=True):
    fmt = "%Y-%m-%d %H:%M"
    if seconds:
        fmt = "%Y-%m-%d %H:%M:%S"

    return datetime.datetime.fromisoformat(ts).strftime(fmt)


def human_interval(sec):
    if sec < 60:
        return "less than a minute"

    sec = round(sec)

    mins = sec // 60
    sec = sec % 60

    if mins < 60:
        return f"{mins}min"

    hours = mins // 60
    mins = mins % 60

    return f"{hours}hr {mins}min"


def time_taken(t_start, t_end):
    return human_interval(time_taken_sec(t_start, t_end))
