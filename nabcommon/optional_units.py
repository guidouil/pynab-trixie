"""Identify configured legacy integrations without exposing their settings."""

import json


def url_configured(url, tags_json):
    if (url or "").strip():
        return True
    try:
        tags = json.loads(tags_json or "{}")
    except json.JSONDecodeError:
        return False
    return isinstance(tags, dict) and any(
        isinstance(url, str) and url.strip() for url in tags.values()
    )


def configured_units():
    from nabiftttd.models import Config as IftttConfig
    from nabmastodond.models import Config as MastodonConfig
    from nabradio.models import Config as RadioConfig
    from nabwebhook.models import Config as WebhookConfig

    ifttt = IftttConfig.objects.filter(pk=1).first()
    if ifttt and (ifttt.ifttt_key or "").strip():
        yield "nabiftttd.service"
    mastodon = MastodonConfig.objects.filter(pk=1).first()
    if mastodon and (mastodon.access_token or "").strip():
        yield "nabmastodond.service"
    radio = RadioConfig.objects.filter(pk=1).first()
    if radio and url_configured(radio.streaming_url, radio.json_data_base):
        yield "nabradio.service"
    webhook = WebhookConfig.objects.filter(pk=1).first()
    if webhook and url_configured(webhook.webhook_url, webhook.json_data_base):
        yield "nabwebhook.service"
