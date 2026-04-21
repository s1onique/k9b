"""Notifications module for delivering alerts to external systems like Mattermost.

Public API:
"""

from .delivery import DEFAULT_JOURNAL, DeliveryJournal, artifact_digest
from .mattermost import (
    MattermostNotifier,
    load_notification_artifact,
    render_mattermost_payload,
)

__all__ = [
    # Delivery journal
    "DeliveryJournal",
    "artifact_digest",
    "DEFAULT_JOURNAL",
    # Mattermost integration
    "MattermostNotifier",
    "load_notification_artifact",
    "render_mattermost_payload",
]
