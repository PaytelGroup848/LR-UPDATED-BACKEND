import time
import threading

try:
    import cv2
    import mss
    import numpy as np
except ImportError as error:
    cv2 = None
    mss = None
    np = None
    IMPORT_ERROR = error
else:
    IMPORT_ERROR = None


class ScreenAgent:

    def __init__(self, socket_client, agent_id):
        self.socket = socket_client
        self.agent_id = agent_id
        self.streaming = False
        self.fps = 15
        self.quality = 60
        self.width = 1280
        self.height = 720
        self.monitor_index = 1
        self.transport = "binary"
        self.session_id = None
        self.keyframe_interval = 2.0
        self.change_threshold = 1.5
        self.adaptive = True
        self._thread = None


    def start(self, settings=None):
        print("[SCREEN] Starting streaming...")
      
        if self.streaming:
            return
        if IMPORT_ERROR:
            self.socket.emit(
                'screen_error',
                {'agent_id': self.agent_id, 'error': f'Screen capture dependency missing: {IMPORT_ERROR}'},
                namespace='/agent',
            )
            print(f"[SCREEN] Cannot start: {IMPORT_ERROR}")
            return
        settings = settings or {}
        self.fps = max(1, min(30, int(settings.get('fps', self.fps))))
        self.quality = max(25, min(90, int(settings.get('quality', self.quality))))
        self.width = max(320, min(1920, int(settings.get('width', self.width))))
        self.height = max(240, min(1080, int(settings.get('height', self.height))))
        self.monitor_index = max(0, int(settings.get('monitor', self.monitor_index)))
        self.session_id = settings.get('session_id')
        self.transport = str(settings.get('transport', self.transport)).lower()
        self.keyframe_interval = max(0.5, min(10.0, float(settings.get('keyframe_interval', self.keyframe_interval))))
        self.change_threshold = max(0.0, min(20.0, float(settings.get('change_threshold', self.change_threshold))))
        self.adaptive = str(settings.get('adaptive', self.adaptive)).lower() not in ('0', 'false', 'no', 'off')

        self.streaming = True

        self._thread = threading.Thread(
            target=self.capture_loop,
            daemon=True
        )

        self._thread.start()

        print("[SCREEN] Streaming started")


    def stop(self):
        print("[SCREEN] Stopping streaming...")
        self.streaming = False
        print("[SCREEN] Streaming stopped")


    def capture_loop(self):
        print("[SCREEN] Capture loop started")
        if IMPORT_ERROR:
            self.socket.emit(
                'screen_error',
                {'agent_id': self.agent_id, 'error': str(IMPORT_ERROR)},
                namespace='/agent',
            )
            self.streaming = False
            return
        if cv2 is None or mss is None or np is None:
            self.streaming = False
            return

        try:
            with mss.mss() as sct:
                if not sct.monitors:
                    raise RuntimeError('No monitor found for screen capture')

                monitor_index = self.monitor_index
                if monitor_index >= len(sct.monitors):
                    monitor_index = 1 if len(sct.monitors) > 1 else 0
                monitor = sct.monitors[monitor_index]
                previous_small = None
                last_keyframe_at = 0.0

                while self.streaming:
                    start_time = time.time()

                    image = sct.grab(monitor)
                    frame = np.array(image)

                    frame = cv2.cvtColor(
                        frame,
                        cv2.COLOR_BGRA2BGR
                    )

                    frame = cv2.resize(
                        frame,
                        (
                            self.width,
                            self.height
                        )
                    )

                    if self.adaptive:
                        small = cv2.resize(frame, (160, 90))
                        small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                        force_keyframe = (start_time - last_keyframe_at) >= self.keyframe_interval
                        if previous_small is not None and not force_keyframe:
                            diff = cv2.absdiff(previous_small, small)
                            if float(diff.mean()) < self.change_threshold:
                                delay = max(0, (1 / self.fps) - (time.time() - start_time))
                                time.sleep(delay)
                                continue
                        previous_small = small
                        last_keyframe_at = start_time

                    success, buffer = cv2.imencode(
                        ".jpg",
                        frame,
                        [
                            cv2.IMWRITE_JPEG_QUALITY,
                            self.quality
                        ]
                    )

                    if success:
                        frame_bytes = buffer.tobytes()
                        payload = {
                            "agent_id": self.agent_id,
                            "session_id": self.session_id,
                            "encoding": "jpeg",
                            "transport": self.transport,
                            "width": self.width,
                            "height": self.height,
                            "sent_at": start_time,
                        }
                        if self.transport == "base64":
                            import base64
                            payload["frame"] = base64.b64encode(frame_bytes).decode('ascii')
                        else:
                            payload["frame"] = frame_bytes
                        self.socket.emit(
                            "screen_frame",
                            payload,
                            namespace='/agent',
                        )

                    elapsed = time.time() - start_time
                    delay = max(
                        0,
                        (1 / self.fps) - elapsed
                    )
                    time.sleep(delay)
        except Exception as error:
            print(f"[SCREEN] Capture error: {error}")
            self.socket.emit(
                'screen_error',
                {'agent_id': self.agent_id, 'session_id': self.session_id, 'error': str(error)},
                namespace='/agent',
            )
            self.streaming = False
