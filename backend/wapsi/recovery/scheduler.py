"""
Recovery Scheduler for WAPSI Autonomous Payment Recovery Engine.

Responsibilities:
- Schedules initial and follow-up recovery actions.
- Enforces configurable communication hours (e.g., 09:00 - 20:00) in the customer's timezone.
- Enforces configurable maximum retry attempts (default: 3).
- Applies bounded exponential backoff with jitter for retries.
- Strictly uses UTC internally for all timestamp calculations and persistence.
- Provides an injectable clock for fully deterministic testing.
- Coordinates with persistent opt-out and state machine.
"""

from __future__ import annotations

import datetime as dt
import logging
import random
from dataclasses import dataclass, field
from typing import Callable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger("wapsi.recovery.scheduler")


@dataclass
class RecoverySchedulePolicy:
    """Configurable scheduling policy parameters."""
    max_attempts: int = 3
    initial_delay_seconds: int = 0  # Immediate dispatch for initial failed payment nudge
    base_retry_backoff_seconds: int = 1800  # 30 minutes
    backoff_multiplier: float = 2.0         # 30m, 60m, 120m...
    max_backoff_seconds: int = 86400        # Max 24 hours between attempts
    jitter_fraction: float = 0.1            # +/- 10% jitter
    communication_start_hour: int = 9       # 09:00 AM local
    communication_end_hour: int = 20        # 08:00 PM (20:00) local
    default_timezone: str = "Asia/Kolkata"
    payment_link_validity_minutes: int = 15  # Minimum Razorpay link duration


@dataclass
class ScheduledRecoveryAction:
    """Represents a scheduled recovery dispatch."""
    case_id: str
    payment_id: str
    attempt_number: int
    scheduled_at_utc: dt.datetime
    target_timezone: str
    is_rescheduled_for_dnd: bool = False
    original_target_utc: Optional[dt.datetime] = None
    reason: str = "INITIAL_RECOVERY"


class RecoveryScheduler:
    """
    Schedules payment recovery actions in UTC with customer timezone awareness.
    """

    def __init__(
        self,
        policy: Optional[RecoverySchedulePolicy] = None,
        clock: Optional[Callable[[], dt.datetime]] = None,
    ):
        self.policy = policy or RecoverySchedulePolicy()
        self._clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))

    def now_utc(self) -> dt.datetime:
        """Returns the current UTC time via the injected clock."""
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=dt.timezone.utc)
        return now.astimezone(dt.timezone.utc)

    def _get_tz(self, tz_name: Optional[str]) -> ZoneInfo:
        target = tz_name or self.policy.default_timezone
        try:
            return ZoneInfo(target)
        except (ZoneInfoNotFoundError, ValueError):
            logger.warning(f"Timezone '{target}' not recognized; falling back to {self.policy.default_timezone}")
            return ZoneInfo(self.policy.default_timezone)

    def adjust_for_communication_window(
        self,
        target_utc: dt.datetime,
        tz_name: Optional[str] = None,
    ) -> Tuple[dt.datetime, bool]:
        """
        If target_utc falls outside allowed communication hours in tz_name,
        advances it to the opening hour (start_hour) of the next allowed window.

        Returns:
            Tuple[dt.datetime, bool]: (adjusted_utc, was_adjusted)
        """
        tz = self._get_tz(tz_name)
        local_dt = target_utc.astimezone(tz)

        start_h = self.policy.communication_start_hour
        end_h = self.policy.communication_end_hour

        # Check if currently within hours: start_hour <= hour < end_hour
        if start_h <= local_dt.hour < end_h:
            return target_utc, False

        # If before start_hour today: advance to start_hour today
        if local_dt.hour < start_h:
            adjusted_local = local_dt.replace(hour=start_h, minute=0, second=0, microsecond=0)
        else:
            # If at or after end_hour: advance to start_hour tomorrow
            next_day = local_dt.date() + dt.timedelta(days=1)
            adjusted_local = dt.datetime.combine(
                next_day,
                dt.time(hour=start_h, minute=0, second=0),
                tzinfo=tz,
            )

        adjusted_utc = adjusted_local.astimezone(dt.timezone.utc)
        return adjusted_utc, True

    def schedule_initial_action(
        self,
        case_id: str,
        payment_id: str,
        customer_timezone: Optional[str] = None,
        delay_seconds: Optional[int] = None,
    ) -> ScheduledRecoveryAction:
        """Schedules attempt 1 for a new recovery case."""
        now = self.now_utc()
        delay = delay_seconds if delay_seconds is not None else self.policy.initial_delay_seconds
        initial_target = now + dt.timedelta(seconds=delay)

        tz_str = customer_timezone or self.policy.default_timezone
        adjusted_utc, was_adjusted = self.adjust_for_communication_window(initial_target, tz_str)

        return ScheduledRecoveryAction(
            case_id=case_id,
            payment_id=payment_id,
            attempt_number=1,
            scheduled_at_utc=adjusted_utc,
            target_timezone=tz_str,
            is_rescheduled_for_dnd=was_adjusted,
            original_target_utc=initial_target if was_adjusted else None,
            reason="INITIAL_RECOVERY",
        )

    def schedule_retry_action(
        self,
        case_id: str,
        payment_id: str,
        current_attempt: int,
        customer_timezone: Optional[str] = None,
        custom_backoff_seconds: Optional[int] = None,
    ) -> Optional[ScheduledRecoveryAction]:
        """
        Schedules next attempt using bounded exponential backoff with jitter.
        Returns None if maximum retry attempts are exhausted.
        """
        next_attempt = current_attempt + 1
        if next_attempt > self.policy.max_attempts:
            logger.info(
                f"Case {case_id} reached attempt limit ({current_attempt}/{self.policy.max_attempts}). No further retry scheduled."
            )
            return None

        now = self.now_utc()

        if custom_backoff_seconds is not None:
            backoff = float(custom_backoff_seconds)
        else:
            # Exponential backoff: base * (multiplier ** (attempt - 2))
            exponent = max(0, next_attempt - 2)
            calculated = self.policy.base_retry_backoff_seconds * (self.policy.backoff_multiplier ** exponent)
            backoff = min(calculated, float(self.policy.max_backoff_seconds))

            # Add jitter (+/- jitter_fraction)
            if self.policy.jitter_fraction > 0:
                jitter_range = backoff * self.policy.jitter_fraction
                backoff += random.uniform(-jitter_range, jitter_range)
                backoff = max(60.0, backoff)  # At least 60 seconds

        raw_target_utc = now + dt.timedelta(seconds=int(backoff))
        tz_str = customer_timezone or self.policy.default_timezone
        adjusted_utc, was_adjusted = self.adjust_for_communication_window(raw_target_utc, tz_str)

        return ScheduledRecoveryAction(
            case_id=case_id,
            payment_id=payment_id,
            attempt_number=next_attempt,
            scheduled_at_utc=adjusted_utc,
            target_timezone=tz_str,
            is_rescheduled_for_dnd=was_adjusted,
            original_target_utc=raw_target_utc if was_adjusted else None,
            reason=f"RETRY_ATTEMPT_{next_attempt}",
        )

