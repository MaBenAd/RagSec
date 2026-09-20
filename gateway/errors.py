class ControlError(Exception):
    """Only stable, non-sensitive reason codes cross an API/log boundary."""

    def __init__(self, reason: str, status: str = "blocked"):
        super().__init__(reason)
        self.reason = reason
        self.status = status
