from datetime import datetime
from zoneinfo import ZoneInfo


CAMPUS_TIMEZONE = ZoneInfo("Asia/Kolkata")


def current_time() -> datetime:
    return datetime.now(CAMPUS_TIMEZONE)
