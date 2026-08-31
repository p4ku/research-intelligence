from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """
    Strict rate limiting for authentication login endpoint to prevent brute-force attacks.
    Defaults to 5 requests per minute per IP address.
    """
    scope = 'login'


class ChatRateThrottle(UserRateThrottle):
    """
    Rate limiting for interactive chat & knowledge explorer endpoints to guard against LLM budget drain.
    Defaults to 20 requests per minute per authenticated user.
    """
    scope = 'chat'
