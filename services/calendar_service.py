"""Генерация ICS-файлов и ссылок Google Calendar для записей на консультацию."""
from datetime import datetime, timedelta, timezone
from urllib.parse import quote


def generate_ics(
    title: str,
    start_dt: datetime,
    duration_hours: float = 1.0,
    location: str = "Онлайн",
    description: str = "",
    organizer_email: str = "info@vashsad.ru",
) -> bytes:
    """Генерирует ICS-файл для события календаря.

    Args:
        title: Заголовок события.
        start_dt: Дата и время начала (naive — трактуется как UTC, или aware).
        duration_hours: Продолжительность в часах.
        location: Место проведения.
        description: Описание события.
        organizer_email: Email организатора.

    Returns:
        Байты ICS-файла.
    """
    # Нормализуем к UTC
    if start_dt.tzinfo is None:
        start_utc = start_dt.replace(tzinfo=timezone.utc)
    else:
        start_utc = start_dt.astimezone(timezone.utc)

    end_utc = start_utc + timedelta(hours=duration_hours)

    def fmt(dt: datetime) -> str:
        return dt.strftime("%Y%m%dT%H%M%SZ")

    # Экранируем спецсимволы для ICS
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//VashSad//Booking//RU",
        "CALSCALE:GREGORIAN",
        "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"DTSTART:{fmt(start_utc)}",
        f"DTEND:{fmt(end_utc)}",
        f"SUMMARY:{esc(title)}",
        f"DESCRIPTION:{esc(description)}",
        f"LOCATION:{esc(location)}",
        f"ORGANIZER:mailto:{organizer_email}",
        "STATUS:CONFIRMED",
        "END:VEVENT",
        "END:VCALENDAR",
    ]

    return "\r\n".join(lines).encode("utf-8")


def build_google_calendar_url(
    title: str,
    start_dt: datetime,
    duration_hours: float = 1.0,
    location: str = "Онлайн",
    description: str = "",
) -> str:
    """Строит ссылку для добавления события в Google Calendar.

    Args:
        title: Заголовок события.
        start_dt: Дата и время начала (naive — трактуется как UTC, или aware).
        duration_hours: Продолжительность в часах.
        location: Место проведения.
        description: Описание события.

    Returns:
        URL для Google Calendar.
    """
    if start_dt.tzinfo is None:
        start_utc = start_dt.replace(tzinfo=timezone.utc)
    else:
        start_utc = start_dt.astimezone(timezone.utc)

    end_utc = start_utc + timedelta(hours=duration_hours)

    def fmt(dt: datetime) -> str:
        return dt.strftime("%Y%m%dT%H%M%SZ")

    dates = f"{fmt(start_utc)}/{fmt(end_utc)}"

    params = (
        f"text={quote(title)}"
        f"&dates={dates}"
        f"&details={quote(description)}"
        f"&location={quote(location)}"
    )
    return f"https://calendar.google.com/calendar/r/eventedit?{params}"
