"""Rotating notice manager for LCD line 2.

Maintains a queue of notices that rotate on the display, with the
current date/time always occupying the last slot.  Notices can be
persistent (require explicit clear) or transient (auto-expire after
a TTL).
"""

from __future__ import annotations

import logging
import threading
from time import localtime, strftime, time
from typing import NamedTuple

log = logging.getLogger(__name__)

TIME_FMT = "%a %b %e %I:%M"


class Notice(NamedTuple):
    id: str
    message: str
    expires_at: float | None  # epoch seconds, or None for no expiry


class NoticeManager:
    """Thread-safe rotating notice queue for LCD line 2.

    Rotation order: notice_1, notice_2, ..., date/time.
    When no notices are active, only the date/time is shown.
    """

    def __init__(self) -> None:
        self._notices: dict[str, Notice] = {}
        self._index: int = 0
        self._lock = threading.Lock()

    def set(self, message: str, notice_id: str | None = None, ttl: int = 60) -> None:
        """Add or update a notice.

        Parameters
        ----------
        message:
            Text to display (max 16 chars).
        notice_id:
            Unique identifier.  Defaults to *message* if not given.
        ttl:
            Seconds until auto-expire.  0 means no expiry (must be
            cleared explicitly).
        """
        nid = notice_id if notice_id is not None else message
        expires_at = time() + ttl if ttl > 0 else None
        with self._lock:
            self._notices[nid] = Notice(id=nid, message=message, expires_at=expires_at)
        log.info("Notice set: id=%r message=%r ttl=%s", nid, message, ttl or "none")

    def clear(self, notice_id: str) -> None:
        """Remove a notice by id (falls back to matching message text)."""
        with self._lock:
            if notice_id in self._notices:
                del self._notices[notice_id]
                log.info("Notice cleared: id=%r", notice_id)
                return
            # Fall back: match by message text
            for nid, notice in list(self._notices.items()):
                if notice.message == notice_id:
                    del self._notices[nid]
                    log.info("Notice cleared by message: %r", notice_id)
                    return
        log.warning("Notice not found to clear: %r", notice_id)

    def get_current_display(self) -> str:
        """Return the next text to display on line 2, advancing the rotation."""
        with self._lock:
            self._prune_expired()
            items = [n.message for n in self._notices.values()]
        # Date/time is always the last slot
        items.append(strftime(TIME_FMT, localtime()))
        idx = self._index % len(items)
        self._index = idx + 1
        return items[idx]

    @property
    def active_count(self) -> int:
        """Number of active (non-expired) notices, excluding date/time."""
        with self._lock:
            self._prune_expired()
            return len(self._notices)

    def _prune_expired(self) -> None:
        """Remove expired notices.  Caller must hold ``_lock``."""
        now = time()
        expired = [
            nid for nid, n in self._notices.items()
            if n.expires_at is not None and n.expires_at <= now
        ]
        for nid in expired:
            del self._notices[nid]
            log.info("Notice expired: id=%r", nid)
