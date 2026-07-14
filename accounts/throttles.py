from ninja.throttling import UserRateThrottle


class ScopedRateThrottle(UserRateThrottle):
    def __init__(self, scope: str, rate: str):
        self.scope = scope
        super().__init__(rate)


login_throttle = ScopedRateThrottle("auth_login", "10/m")
refresh_throttle = ScopedRateThrottle("auth_refresh", "30/m")
register_throttle = ScopedRateThrottle("auth_register", "5/h")
verification_throttle = ScopedRateThrottle("auth_verification", "5/h")
password_reset_request_throttle = ScopedRateThrottle("auth_reset_request", "5/h")
password_reset_confirm_throttle = ScopedRateThrottle("auth_reset_confirm", "10/h")
email_change_throttle = ScopedRateThrottle("auth_email_change", "3/h")
logout_throttle = ScopedRateThrottle("auth_logout", "30/h")
token_verify_throttle = ScopedRateThrottle("auth_token_verify", "60/m")
