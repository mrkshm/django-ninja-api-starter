# Refactoring Tests for Email Verification Authentication

This document provides guidelines for updating existing tests to work with our new email verification authentication system.

## Overview of Changes

With the implementation of email verification, the authentication flow has changed in the following ways:

1. New users are created with `email_verified=False` by default during registration
2. Users must verify their email before they can log in
3. Login attempts for unverified users return a 403 Forbidden response
4. The JWT token controller checks for email verification before issuing tokens

## Updating Test Cases

### 1. Use the Test Utility Function

We've created a utility function in `accounts/tests/utils.py` to make test user creation easier:

```python
from accounts.tests.utils import create_test_user

# Creates a verified user by default
user = create_test_user(email="test@example.com", password="testpass")

# To create an unverified user
unverified_user = create_test_user(email="unverified@example.com", password="testpass", email_verified=False)
```

### 2. Update Existing User Creation

For tests that directly create users with `User.objects.create_user()`, add the `email_verified=True` parameter:

```python
# Before
user = User.objects.create_user(email="test@example.com", password="testpass")

# After
user = User.objects.create_user(email="test@example.com", password="testpass", email_verified=True)
```

### 3. Update Test Fixtures

If you have test fixtures that create users, update them to set `email_verified=True`:

```python
@pytest.fixture
def test_user():
    return User.objects.create_user(
        email="fixture@example.com", 
        password="fixturepass",
        email_verified=True  # Add this parameter
    )
```

### 4. Update Authentication Tests

Tests that verify authentication behavior should be updated to account for email verification:

```python
# Test for verified users (should succeed)
def test_login_with_verified_user():
    user = create_test_user(email="verified@example.com", password="testpass")
    response = client.post("/token/pair", json={"email": user.email, "password": "testpass"})
    assert response.status_code == 200
    assert "access" in response.json()

# Test for unverified users (should fail with 403)
def test_login_with_unverified_user():
    user = create_test_user(email="unverified@example.com", password="testpass", email_verified=False)
    response = client.post("/token/pair", json={"email": user.email, "password": "testpass"})
    assert response.status_code == 403
    assert response.json()["email_verified"] == False
```

### 5. Update API Tests

For API tests that require authentication, ensure the test users are verified:

```python
def test_authenticated_endpoint():
    # Create a verified user
    user = create_test_user()
    
    # Get authentication token
    token_response = client.post("/token/pair", json={"email": user.email, "password": "testpassword"})
    token = token_response.json()["access"]
    
    # Test the authenticated endpoint
    response = client.get("/api/protected-endpoint/", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 200
```

## Common Patterns to Look For

1. **Test Client Authentication**: Any test using `client.post("/token/pair", ...)` needs a verified user
2. **Direct User Creation**: All `User.objects.create_user()` calls should include `email_verified=True`
3. **Fixtures**: Update all user fixtures to create verified users by default
4. **Factory Methods**: If you have factory methods for creating test users, update those

## Testing the Email Verification Flow

Make sure to test the complete email verification flow:

1. Registration (creates unverified user)
2. Verification (activates user account)
3. Login after verification (should succeed)
4. Resend verification (for expired tokens)

See `accounts/tests/test_email_verification.py` for examples of these test cases.

## Best Practices

1. Use the `create_test_user()` utility function whenever possible
2. Be explicit about verification status in test names and comments
3. Test both verified and unverified user scenarios
4. When testing registration, verify that users are created with `email_verified=False`
5. When testing verification, verify that users are updated with `email_verified=True`

## Troubleshooting

If tests are failing with a 403 status code and a message about email verification, check that:

1. The test user was created with `email_verified=True`
2. The email and password in the login request match the test user's credentials
3. The login endpoint URL is correct (`/token/pair`)

For any other issues, refer to the implementation in `accounts/api.py` and the test examples in `accounts/tests/test_email_verification.py`.
