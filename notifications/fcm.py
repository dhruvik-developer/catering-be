"""Firebase Cloud Messaging dispatcher.

Lazy-initialises the firebase-admin app from the service-account JSON pointed
at by `settings.FIREBASE_CREDENTIALS_PATH`. If the file is missing (e.g. local
dev without a service account), FCM is silently disabled — REST + WebSocket
delivery still work, only push-to-closed-app is unavailable.

`send_multicast` returns the list of tokens that the server marked invalid so
the caller can deactivate them.
"""

import logging
import os
import threading
from typing import Iterable, List, Mapping

from django.conf import settings

logger = logging.getLogger("notifications")

_init_lock = threading.Lock()
_initialized = False
_disabled_reason: str = ""


def _ensure_initialized() -> bool:
    global _initialized, _disabled_reason
    if _initialized:
        return True
    if _disabled_reason:
        return False

    with _init_lock:
        if _initialized:
            return True
        if _disabled_reason:
            return False

        path = getattr(settings, "FIREBASE_CREDENTIALS_PATH", "")
        if not path or not os.path.isfile(path):
            _disabled_reason = (
                f"FIREBASE_CREDENTIALS_PATH not set or missing ({path!r}); "
                "FCM dispatch disabled."
            )
            logger.warning(_disabled_reason)
            return False

        try:
            import firebase_admin
            from firebase_admin import credentials

            if not firebase_admin._apps:
                cred = credentials.Certificate(path)
                firebase_admin.initialize_app(cred)
            _initialized = True
            return True
        except Exception as exc:
            _disabled_reason = f"firebase-admin init failed: {exc}"
            logger.exception("firebase-admin init failed")
            return False


def send_multicast(
    tokens: Iterable[str],
    *,
    title: str,
    body: str,
    data: Mapping[str, object],
) -> List[str]:
    """Send the same notification to up to 500 tokens. Returns the subset of
    tokens that FCM reported as permanently invalid (UNREGISTERED /
    INVALID_ARGUMENT) — the caller should deactivate those rows."""
    tokens = [t for t in tokens if t]
    if not tokens:
        return []
    if not _ensure_initialized():
        return []

    from firebase_admin import messaging

    # FCM `data` payload is string→string only. Anything non-stringifiable
    # would raise ValueError deep inside the SDK.
    data_payload = {k: str(v) for k, v in (data or {}).items()}

    # Webpush `link` MUST be an absolute HTTPS URL or the SDK refuses to encode
    # the WHOLE multicast (so even Android/iOS tokens get nothing). Our `route`
    # is an in-app relative path the mobile app consumes from the data payload,
    # so only attach it as a browser deep-link when it's already a full HTTPS
    # URL; otherwise omit fcm_options.
    route = str(data_payload.get("route", ""))
    webpush_fcm_options = (
        messaging.WebpushFCMOptions(link=route)
        if route.startswith("https://")
        else None
    )

    message = messaging.MulticastMessage(
        tokens=tokens,
        notification=messaging.Notification(title=title, body=body),
        data=data_payload,
        android=messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(
                channel_id="catering_default",
                sound="default",
            ),
        ),
        apns=messaging.APNSConfig(
            headers={"apns-priority": "10"},
            payload=messaging.APNSPayload(
                aps=messaging.Aps(sound="default", content_available=True),
            ),
        ),
        webpush=messaging.WebpushConfig(
            notification=messaging.WebpushNotification(
                title=title,
                body=body,
                icon="/icons/icon-192.png",
            ),
            fcm_options=messaging.WebpushFCMOptions(
                link=data_payload.get("route", "/"),
            ),
        ),
    )

    try:
        resp = messaging.send_each_for_multicast(message)
    except Exception:
        logger.exception("FCM dispatch failed")
        return []

    invalid: List[str] = []
    for idx, r in enumerate(resp.responses):
        if r.success:
            continue
        exc = r.exception
        code = getattr(exc, "code", "") or ""
        if code in {
            "registration-token-not-registered",
            "invalid-argument",
            "invalid-registration-token",
        }:
            invalid.append(tokens[idx])
        else:
            logger.warning("FCM send error for token idx %s: %s", idx, exc)
    if resp.failure_count:
        logger.info(
            "FCM multicast: %s succeeded, %s failed (%s permanently invalid)",
            resp.success_count,
            resp.failure_count,
            len(invalid),
        )
    return invalid
