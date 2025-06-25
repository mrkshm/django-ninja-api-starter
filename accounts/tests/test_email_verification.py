import pytest
from django.contrib.auth import get_user_model
from ninja.testing import TestClient
from DjangoApiStarter.api import api
from accounts.models import PendingRegistration
from django.utils import timezone
import datetime

User = get_user_model()
client = TestClient(api)

@pytest.mark.django_db
def test_register_creates_unverified_user():
    # Arrange
    email = "newuser@example.com"
    password = "securepassword123"
    
    # Act
    response = client.post(
        "/auth/register/",
        json={"email": email, "password": password}
    )
    
    # Assert
    assert response.status_code == 200
    assert "detail" in response.json()
    assert "Please check your email" in response.json()["detail"]
    
    # Verify user was created with email_verified=False
    user = User.objects.get(email=email)
    assert user.email_verified is False
    
    # Verify PendingRegistration was created
    pending = PendingRegistration.objects.get(user=user)
    assert pending is not None
    assert pending.token is not None

@pytest.mark.django_db
def test_verify_registration_activates_user():
    # Arrange
    email = "verifyuser@example.com"
    password = "securepassword123"
    user = User.objects.create_user(email=email, password=password, email_verified=False)
    
    # Create a pending registration with a known token
    token = "test_verification_token"
    expires_at = timezone.now() + datetime.timedelta(hours=24)
    pending = PendingRegistration.objects.create(
        user=user,
        token=token,
        expires_at=expires_at
    )
    
    # Act
    response = client.get(f"/auth/verify-registration?token={token}")
    
    # Assert
    assert response.status_code == 200
    assert "access" in response.json()
    assert "refresh" in response.json()
    
    # Verify user is now marked as verified
    user.refresh_from_db()
    assert user.email_verified is True
    
    # Verify pending registration is deleted
    with pytest.raises(PendingRegistration.DoesNotExist):
        PendingRegistration.objects.get(token=token)

@pytest.mark.django_db
def test_verify_registration_with_expired_token():
    # Arrange
    email = "expireduser@example.com"
    password = "securepassword123"
    user = User.objects.create_user(email=email, password=password, email_verified=False)
    
    # Create an expired pending registration
    token = "expired_token"
    expires_at = timezone.now() - datetime.timedelta(hours=1)  # 1 hour in the past
    pending = PendingRegistration.objects.create(
        user=user,
        token=token,
        expires_at=expires_at
    )
    
    # Act
    response = client.get(f"/auth/verify-registration?token={token}")
    
    # Assert
    assert response.status_code == 400
    assert "expired" in response.json()["detail"]
    
    # Verify user is still not verified
    user.refresh_from_db()
    assert user.email_verified is False

@pytest.mark.django_db
def test_login_with_unverified_user(settings):
    # Override the global setting for this specific test
    settings.REQUIRE_EMAIL_VERIFICATION_FOR_LOGIN = True
    
    # Arrange
    email = "unverifieduser@example.com"
    password = "securepassword123"
    User.objects.create_user(email=email, password=password, email_verified=False)
    
    # Act
    response = client.post(
        "/token/pair",
        json={"email": email, "password": password}
    )
    
    # Assert
    assert response.status_code == 403  # Now returns 403 for unverified users
    assert "email_verified" in response.json()
    assert response.json()["email_verified"] is False
    assert "Please verify your email" in response.json()["detail"]

@pytest.mark.django_db
def test_login_with_verified_user():
    # Arrange
    email = "verifieduser@example.com"
    password = "securepassword123"
    User.objects.create_user(email=email, password=password, email_verified=True)
    
    # Act
    response = client.post(
        "/token/pair",
        json={"email": email, "password": password}
    )
    
    # Assert
    assert response.status_code == 200
    assert "access" in response.json()
    assert "refresh" in response.json()

@pytest.mark.django_db
def test_resend_verification():
    # Arrange
    email = "resenduser@example.com"
    password = "securepassword123"
    user = User.objects.create_user(email=email, password=password, email_verified=False)
    
    # Act
    response = client.post(
        "/auth/resend-verification",
        json={"email": email}
    )
    
    # Assert
    assert response.status_code == 200
    
    # Verify a new pending registration was created
    pending = PendingRegistration.objects.get(user=user)
    assert pending is not None
    assert pending.token is not None
