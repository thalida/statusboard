from rest_framework.throttling import ScopedRateThrottle


class PerAddressThrottle(ScopedRateThrottle):
    """A sign-in link, counted against the address it would reach.

    The scoped throttle counts per caller, which stops one sender
    asking for many links. It does not stop many senders asking for
    links to one address. That is the shape that buries an inbox.
    """

    scope = "magic-link"

    def get_cache_key(self, request, view):
        address = (request.data.get("email") or "").strip().lower()
        if not address:
            return None
        return f"throttle_magic-link_to_{address}"
