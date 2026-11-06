class FeatureCache:
    def __init__(self):
        self.entries = {}

    def get(self, key, loader):
        if key not in self.entries:
            self.entries[key] = loader()
        return self.entries[key]
