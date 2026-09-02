from rest_framework.throttling import ScopedRateThrottle

from api.defaults import Throttle


class PerAddressThrottle(ScopedRateThrottle):
    """A sign-in link, counted against the address it would reach.

    The scoped throttle counts per caller, which stops one sender
    asking for many links. It does not stop many senders asking for
    links to one address. That is the shape that buries an inbox.
    """

    scope = Throttle.MAGIC_LINK

    def get_cache_key(self, request, view):
        address = (request.data.get("email") or "").strip().lower()
        if not address:
            return None
        # DRF's own key shape, with its scope and our identity. The
        # scoped throttle beside this one keys on the caller's address,
        # so the two never collide.
        return self.cache_format % {"scope": self.scope, "ident": f"to_{address}"}
