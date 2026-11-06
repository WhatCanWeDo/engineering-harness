from collections import OrderedDict
from time import monotonic


class FeatureCache:
    def __init__(self, ttl_seconds, max_entries, clock=monotonic):
        if ttl_seconds <= 0 or max_entries <= 0:
            raise ValueError("ttl_seconds and max_entries must be positive")
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.clock = clock
        self.entries = OrderedDict()

    def get(self, key, loader):
        if key in self.entries:
            value, expires_at = self.entries[key]
            if self.clock() < expires_at:
                self.entries.move_to_end(key)
                return value
            del self.entries[key]
        value = loader()
        self.entries[key] = (value, self.clock() + self.ttl_seconds)
        self.entries.move_to_end(key)
        while len(self.entries) > self.max_entries:
            self.entries.popitem(last=False)
        return value

    def invalidate(self, key):
        return self.entries.pop(key, None) is not None
