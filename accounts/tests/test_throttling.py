import json

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import Client, RequestFactory
from ninja.conf import settings as ninja_settings

from accounts.models import User
from accounts.services import issue_token_pair
from accounts.throttles import login_throttle

CADDY_REMOTE_ADDR = "172.20.0.10"


def post_json(client, path, payload, *, client_ip, authorization=None):
    request_kwargs = {
        "data": json.dumps(payload),
        "content_type": "application/json",
        "REMOTE_ADDR": CADDY_REMOTE_ADDR,
        "HTTP_X_FORWARDED_FOR": client_ip,
    }
    if authorization:
        request_kwargs["HTTP_AUTHORIZATION"] = authorization
    return client.post(path, **request_kwargs)


def patch_json(client, path, payload, *, client_ip, authorization):
    return client.patch(
        path,
        data=json.dumps(payload),
        content_type="application/json",
        REMOTE_ADDR=CADDY_REMOTE_ADDR,
        HTTP_X_FORWARDED_FOR=client_ip,
        HTTP_AUTHORIZATION=authorization,
    )


def test_supported_proxy_topology_selects_caddy_client_address():
    assert ninja_settings.NUM_PROXIES == 1
    factory = RequestFactory()

    proxied = factory.get(
        "/",
        REMOTE_ADDR=CADDY_REMOTE_ADDR,
        HTTP_X_FORWARDED_FOR="198.51.100.8",
    )
    chained = factory.get(
        "/",
        REMOTE_ADDR=CADDY_REMOTE_ADDR,
        HTTP_X_FORWARDED_FOR="198.51.100.7, 203.0.113.9",
    )
    direct = factory.get("/", REMOTE_ADDR="192.0.2.10")

    assert login_throttle.get_ident(proxied) == "198.51.100.8"
    assert login_throttle.get_ident(chained) == "203.0.113.9"
    assert login_throttle.get_ident(direct) == "192.0.2.10"


@pytest.mark.django_db
def test_login_throttle_uses_real_cache_and_separates_client_ips():
    client = Client()
    payload = {"email": "missing@example.com", "password": "wrong"}

    for _ in range(10):
        response = post_json(
            client,
            "/api/v1/token/pair",
            payload,
            client_ip="198.51.100.20",
        )
        assert response.status_code == 401

    limited = post_json(
        client,
        "/api/v1/token/pair",
        payload,
        client_ip="198.51.100.20",
    )
    other_ip = post_json(
        client,
        "/api/v1/token/pair",
        payload,
        client_ip="198.51.100.21",
    )

    assert limited.status_code == 429
    assert other_ip.status_code == 401


@pytest.mark.django_db
def test_registration_and_reset_use_independent_real_throttle_scopes():
    client = Client()
    client_ip = "198.51.100.30"

    for index in range(5):
        registration = post_json(
            client,
            "/api/v1/auth/register/",
            {"email": f"pending-{index}@example.com"},
            client_ip=client_ip,
        )
        reset = post_json(
            client,
            "/api/v1/auth/password-reset/request",
            {"email": "missing@example.com"},
            client_ip=client_ip,
        )
        assert registration.status_code == 200
        assert reset.status_code == 200

    registration_limited = post_json(
        client,
        "/api/v1/auth/register/",
        {"email": "pending-final@example.com"},
        client_ip=client_ip,
    )
    reset_limited = post_json(
        client,
        "/api/v1/auth/password-reset/request",
        {"email": "missing@example.com"},
        client_ip=client_ip,
    )

    assert registration_limited.status_code == 429
    assert reset_limited.status_code == 429


@pytest.mark.django_db
def test_authenticated_throttle_follows_user_across_ips_and_separates_users():
    first_user = User.objects.create_user(
        email="throttle-one@example.com", password="pw", email_verified=True
    )
    second_user = User.objects.create_user(
        email="throttle-two@example.com", password="pw", email_verified=True
    )
    first_access, _ = issue_token_pair(first_user)
    second_access, _ = issue_token_pair(second_user)
    client = Client()

    for index in range(3):
        response = patch_json(
            client,
            "/api/v1/auth/email",
            {
                "email": f"throttle-one-{index}@example.com",
                "current_password": "pw",
            },
            client_ip=f"198.51.100.{40 + index}",
            authorization=f"Bearer {first_access}",
        )
        assert response.status_code == 200

    limited = patch_json(
        client,
        "/api/v1/auth/email",
        {"email": "throttle-one-final@example.com", "current_password": "pw"},
        client_ip="198.51.100.50",
        authorization=f"Bearer {first_access}",
    )
    other_user = patch_json(
        client,
        "/api/v1/auth/email",
        {"email": "throttle-two-new@example.com", "current_password": "pw"},
        client_ip="198.51.100.50",
        authorization=f"Bearer {second_access}",
    )

    assert limited.status_code == 429
    assert other_user.status_code == 200


def test_throttle_cache_keys_have_distinct_operation_scopes():
    from accounts import throttles
    from contacts import throttles as contact_throttles
    from images import throttles as image_throttles

    request = RequestFactory().get(
        "/", REMOTE_ADDR=CADDY_REMOTE_ADDR, HTTP_X_FORWARDED_FOR="198.51.100.60"
    )
    request.user = AnonymousUser()
    instances = [
        throttles.login_throttle,
        throttles.refresh_throttle,
        throttles.register_throttle,
        throttles.verification_throttle,
        throttles.password_reset_request_throttle,
        throttles.password_reset_confirm_throttle,
        throttles.email_change_throttle,
        throttles.logout_throttle,
        throttles.token_verify_throttle,
        contact_throttles.contact_search_throttle,
        image_throttles.upload_throttle,
        image_throttles.bulk_upload_throttle,
        image_throttles.bulk_delete_throttle,
        image_throttles.bulk_attach_throttle,
        image_throttles.bulk_detach_throttle,
        image_throttles.share_link_throttle,
    ]

    keys = [instance.get_cache_key(request) for instance in instances]
    assert len(keys) == len(set(keys))
