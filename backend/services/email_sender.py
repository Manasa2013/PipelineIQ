"""
Email Sender Service — abstraction for sending emails.

Provides a pluggable interface for sending emails.  Currently supports
simulated sending (logging) only.  Future providers can be added by
implementing the ``EmailSender`` abstract base class and registering
it in the factory.

Design
------
The ``EmailSender`` abstract base class defines the interface all
providers must implement:

- ``send(lead_name, lead_email, subject, body)`` → send result dict

The ``get_email_sender()`` factory function returns the configured
sender based on the ``EMAIL_PROVIDER`` setting.

Future Providers
----------------
- SMTP:    ``smtp://``  — direct SMTP connection
- SendGrid: ``sendgrid://`` — SendGrid API
- Gmail API: ``gmail://`` — Google Workspace / Gmail API
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from backend.config import get_settings

logger = logging.getLogger(__name__)


# ── Abstract base class ─────────────────────────────────────────────────


class EmailSender(ABC):
    """Abstract base class for email sending providers."""

    @abstractmethod
    async def send(
        self,
        to_name: str,
        to_email: str,
        subject: str,
        body: str,
    ) -> dict[str, Any]:
        """Send an email.

        Args:
            to_name: The recipient's name.
            to_email: The recipient's email address.
            subject: The email subject line.
            body: The email body (plain text).

        Returns:
            A dict with:
            - ``"success"``: True if the send was successful.
            - ``"provider"``: The name of the provider used.
            - ``"message_id"``: A unique identifier for the sent message.
            - ``"timestamp"``: ISO timestamp of when the send occurred.
            - ``"error"``: Error message (only on failure).
        """
        ...


# ── Simulated sender (current default) ─────────────────────────────────


class SimulatedEmailSender(EmailSender):
    """Simulated email sender — logs the send action without actually sending.

    This is the default provider.  It logs the email content and returns
    a success response.  Use this for development and testing.
    """

    async def send(
        self,
        to_name: str,
        to_email: str,
        subject: str,
        body: str,
    ) -> dict[str, Any]:
        """Simulate sending an email by logging it.

        Args:
            to_name: The recipient's name.
            to_email: The recipient's email address.
            subject: The email subject line.
            body: The email body (plain text).

        Returns:
            A success dict with a simulated message ID.
        """
        message_id = f"sim-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"

        logger.info(
            "📧 SIMULATED EMAIL SEND\n"
            "  To: %s <%s>\n"
            "  Subject: %s\n"
            "  Body:\n%s\n"
            "  --- End of simulated email ---",
            to_name,
            to_email,
            subject,
            body,
        )

        return {
            "success": True,
            "provider": "simulated",
            "message_id": message_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": None,
        }


# ── Factory ─────────────────────────────────────────────────────────────


def get_email_sender() -> EmailSender:
    """Return the configured email sender instance.

    Reads the ``EMAIL_PROVIDER`` setting from the environment and returns
    the appropriate sender implementation.

    Current providers:
    - ``"simulated"`` (default) — logs the email, does not send.

    Returns:
        An ``EmailSender`` instance.
    """
    settings = get_settings()
    provider = settings.EMAIL_PROVIDER.lower()

    if provider == "simulated":
        return SimulatedEmailSender()

    # Fallback to simulated for unknown providers
    logger.warning(
        "Unknown EMAIL_PROVIDER '%s', falling back to simulated sender",
        provider,
    )
    return SimulatedEmailSender()