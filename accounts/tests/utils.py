from django.contrib.auth import get_user_model

User = get_user_model()


def create_test_user(email="test@example.com", password="testpassword", email_verified=True, **kwargs):
    """
    Helper function to create a test user with email verification by default.
    
    Args:
        email: Email address for the test user
        password: Password for the test user
        email_verified: Whether the user's email is verified (default: True)
        **kwargs: Additional fields to set on the user
        
    Returns:
        The created user instance
    """
    return User.objects.create_user(
        email=email,
        password=password,
        email_verified=email_verified,
        **kwargs
    )
