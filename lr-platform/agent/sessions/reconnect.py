import time

class ReconnectPolicy:
    def __init__(self, base_delay=2, max_delay=30):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.attempt = 0

    def next_delay(self):
        self.attempt += 1
        return min(self.max_delay, self.base_delay * (2 ** (self.attempt - 1)))

    def reset(self):
        self.attempt = 0


def wait_before_reconnect(policy):
    delay = policy.next_delay()
    time.sleep(delay)
    return delay
