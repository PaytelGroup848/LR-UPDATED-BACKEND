from datetime import datetime


class TimestampMixin:
    def __init__(self, created_at=None, updated_at=None, **kwargs):
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at
        for key, value in kwargs.items():
            setattr(self, key, value)
