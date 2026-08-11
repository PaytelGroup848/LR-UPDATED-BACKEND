class LRPlatformError(Exception):
    status_code = 400

    def __init__(self, message="Request failed", status_code=None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code

    def to_dict(self):
        return {
            "success": False,
            "error": self.message,
        }


class NotFoundError(LRPlatformError):
    status_code = 404


class ForbiddenError(LRPlatformError):
    status_code = 403


class ValidationError(LRPlatformError):
    status_code = 422
