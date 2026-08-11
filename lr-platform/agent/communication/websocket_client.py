import socketio


class AgentSocketClient:
    def __init__(self, server_url, namespace="/agent"):
        self.server_url = server_url
        self.namespace = namespace
        self.client = socketio.Client()

    def on(self, event, handler):
        self.client.on(event, handler, namespace=self.namespace)

    def emit(self, event, data=None):
        self.client.emit(event, data or {}, namespace=self.namespace)

    def connect(self):
        self.client.connect(self.server_url, namespaces=[self.namespace])

    def wait(self):
        self.client.wait()

    def disconnect(self):
        self.client.disconnect()
