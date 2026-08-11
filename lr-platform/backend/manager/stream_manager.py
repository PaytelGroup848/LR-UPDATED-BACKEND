

import base64
import json
import os
from datetime import datetime


class StreamManager:
    def __init__(self):
        self.streams = {}
        self.viewers = {}
        self._recordings = {}
        self._recording_history = []

    def stream_key(self, agent_id, session_id=None):
        return f"{agent_id}:{session_id}" if session_id else str(agent_id)

    def safe_name(self, value):
        return ''.join(char if char.isalnum() or char in '._-' else '_' for char in str(value or 'stream'))

    def room_name(self, agent_id, session_id=None):
        return f"stream:{self.stream_key(agent_id, session_id)}"

    def start_stream(self, agent_id, started_by=None, session_id=None):
        key = self.stream_key(agent_id, session_id)
        stream = self.streams.setdefault(key, {})
        stream.update({
            'agent_id': agent_id,
            'session_id': session_id,
            'active': True,
            'started_by': started_by,
            'started_at': datetime.utcnow(),
            'stopped_at': None,
        })
        return stream

    def stop_stream(self, agent_id, session_id=None):
        key = self.stream_key(agent_id, session_id)
        stream = self.streams.setdefault(key, {'agent_id': agent_id, 'session_id': session_id})
        stream.update({
            'active': False,
            'stopped_at': datetime.utcnow(),
        })
        self.viewers.pop(key, None)
        return stream

    def update_frame(self, agent_id, sid, frame, metadata=None):
        metadata = metadata or {}
        session_id = metadata.get('session_id')
        key = self.stream_key(agent_id, session_id)
        normalized = self._normalize_frame(frame)
        stream = self.streams.setdefault(key, {'agent_id': agent_id, 'session_id': session_id})
        stream.update({
            'active': True,
            'agent_sid': sid,
            'session_id': session_id,
            'last_frame': normalized['data_url'],
            'last_frame_binary': normalized['binary'],
            'last_frame_encoding': normalized['encoding'],
            'last_frame_size': len(normalized['binary']) if normalized['binary'] else len(normalized['data_url'] or ''),
            'last_frame_width': metadata.get('width'),
            'last_frame_height': metadata.get('height'),
            'last_frame_sent_at': metadata.get('sent_at'),
            'last_frame_at': datetime.utcnow(),
        })
        self._record_frame(agent_id, normalized, session_id=session_id)
        return stream

    def get_frame(self, agent_id, session_id=None):
        stream = self.streams.get(self.stream_key(agent_id, session_id)) or {}
        return stream.get('last_frame')

    def get_frame_payload(self, agent_id, session_id=None):
        stream = self.streams.get(self.stream_key(agent_id, session_id)) or {}
        if stream.get('last_frame_binary'):
            return {
                'binary': stream.get('last_frame_binary'),
                'encoding': stream.get('last_frame_encoding') or 'jpeg',
                'width': stream.get('last_frame_width'),
                'height': stream.get('last_frame_height'),
                'sent_at': stream.get('last_frame_sent_at'),
            }
        if stream.get('last_frame'):
            return {
                'frame': stream.get('last_frame'),
                'encoding': stream.get('last_frame_encoding') or 'jpeg',
                'width': stream.get('last_frame_width'),
                'height': stream.get('last_frame_height'),
                'sent_at': stream.get('last_frame_sent_at'),
            }
        return None

    def add_viewer(self, agent_id, viewer_sid, user_id=None, session_id=None):
        key = self.stream_key(agent_id, session_id)
        viewers = self.viewers.setdefault(key, {})
        viewers[viewer_sid] = {
            'sid': viewer_sid,
            'user_id': user_id,
            'agent_id': agent_id,
            'session_id': session_id,
            'joined_at': datetime.utcnow(),
        }
        return viewers[viewer_sid]

    def remove_viewer(self, viewer_sid):
        removed = []
        for key, viewers in list(self.viewers.items()):
            if viewer_sid in viewers:
                del viewers[viewer_sid]
                removed.append(key)
            if not viewers:
                del self.viewers[key]
        return removed

    def remove_agent_sid(self, sid):
        removed = []
        for key, stream in list(self.streams.items()):
            if stream.get('agent_sid') == sid:
                self.stop_stream(stream.get('agent_id'), stream.get('session_id'))
                removed.append(key)
        return removed

    def status(self, agent_id=None, session_id=None):
        if agent_id:
            key = self.stream_key(agent_id, session_id)
            return self._serialize_stream(key, self.streams.get(key))
        return [self._serialize_stream(item_id, stream) for item_id, stream in self.streams.items()]

    def configure_stream(self, agent_id, settings, session_id=None):
        key = self.stream_key(agent_id, session_id)
        stream = self.streams.setdefault(key, {'agent_id': agent_id, 'session_id': session_id})
        stream['settings'] = {
            'fps': int(settings.get('fps', 10)),
            'quality': int(settings.get('quality', 55)),
            'width': int(settings.get('width', 1280)),
            'height': int(settings.get('height', 720)),
        }
        return stream['settings']

    def start_recording(self, agent_id, recording_dir, user_id=None, session_id=None):
        os.makedirs(recording_dir, exist_ok=True)
        started = datetime.utcnow()
        key = self.stream_key(agent_id, session_id)
        folder = os.path.join(recording_dir, f'{self.safe_name(key)}-{started.strftime("%Y%m%d%H%M%S")}')
        os.makedirs(folder, exist_ok=True)
        recording = {
            'agent_id': agent_id,
            'session_id': session_id,
            'started_by': user_id,
            'started_at': started,
            'stopped_at': None,
            'folder': folder,
            'frame_count': 0,
            'last_saved_at': None,
        }
        self._recordings[key] = recording
        self._write_recording_manifest(recording)
        return self._serialize_recording(recording)

    def stop_recording(self, agent_id, session_id=None):
        key = self.stream_key(agent_id, session_id)
        recording = self._recordings.get(key)
        if not recording:
            return {'agent_id': agent_id, 'active': False}
        recording['stopped_at'] = datetime.utcnow()
        self._write_recording_manifest(recording)
        result = self._serialize_recording(recording)
        self._recording_history.append(result)
        self._recordings.pop(key, None)
        return result

    def recordings(self):
        active = [self._serialize_recording(item) for item in self._recordings.values()]
        return active + list(reversed(self._recording_history[-100:]))

    def _serialize_stream(self, key, stream):
        stream = stream or {'agent_id': key, 'active': False}
        started_at = stream.get('started_at')
        stopped_at = stream.get('stopped_at')
        last_frame_at = stream.get('last_frame_at')
        return {
            'stream_key': key,
            'agent_id': stream.get('agent_id'),
            'session_id': stream.get('session_id'),
            'active': bool(stream.get('active')),
            'started_by': stream.get('started_by'),
            'started_at': started_at.isoformat() if started_at else None,
            'stopped_at': stopped_at.isoformat() if stopped_at else None,
            'last_frame_at': last_frame_at.isoformat() if last_frame_at else None,
            'viewer_count': len(self.viewers.get(key, {})),
            'recording': bool(self._recordings.get(key)),
            'settings': stream.get('settings') or {},
            'last_frame_size': stream.get('last_frame_size'),
        }

    def _normalize_frame(self, frame):
        if isinstance(frame, bytes):
            return {
                'binary': frame,
                'data_url': 'data:image/jpeg;base64,' + base64.b64encode(frame).decode('ascii'),
                'encoding': 'jpeg',
            }
        if isinstance(frame, str) and not frame.startswith('data:image'):
            try:
                binary = base64.b64decode(frame)
            except Exception:
                binary = None
            return {
                'binary': binary,
                'data_url': 'data:image/jpeg;base64,' + frame,
                'encoding': 'jpeg',
            }
        return {
            'binary': None,
            'data_url': frame,
            'encoding': 'jpeg',
        }

    def _record_frame(self, agent_id, normalized, session_id=None):
        recording = self._recordings.get(self.stream_key(agent_id, session_id))
        if not recording:
            return
        now = datetime.utcnow()
        last_saved = recording.get('last_saved_at')
        if last_saved and (now - last_saved).total_seconds() < 1:
            return
        try:
            content = normalized.get('binary')
            if content is None:
                frame = normalized.get('data_url') or ''
                payload = frame.split(',', 1)[1] if ',' in frame else frame
                content = base64.b64decode(payload)
            recording['frame_count'] += 1
            filename = f"frame-{recording['frame_count']:06d}.jpg"
            with open(os.path.join(recording['folder'], filename), 'wb') as handle:
                handle.write(content)
            recording['last_saved_at'] = now
            self._write_recording_manifest(recording)
        except Exception:
            return

    def _write_recording_manifest(self, recording):
        try:
            manifest_path = os.path.join(recording['folder'], 'recording.json')
            with open(manifest_path, 'w', encoding='utf-8') as handle:
                json.dump(self._serialize_recording(recording), handle, indent=2)
        except Exception:
            return

    def _serialize_recording(self, recording):
        started_at = recording.get('started_at')
        stopped_at = recording.get('stopped_at')
        return {
            'agent_id': recording.get('agent_id'),
            'session_id': recording.get('session_id'),
            'active': not bool(recording.get('stopped_at')),
            'started_by': recording.get('started_by'),
            'started_at': started_at.isoformat() if started_at else None,
            'stopped_at': stopped_at.isoformat() if stopped_at else None,
            'folder': recording.get('folder'),
            'frame_count': recording.get('frame_count', 0),
        }


stream_manager = StreamManager()


def save_frame(agent_id, sid, frame):
    return stream_manager.update_frame(agent_id, sid, frame)


def remove_sid(sid):
    removed = stream_manager.remove_agent_sid(sid)
    removed.extend(stream_manager.remove_viewer(sid))
    return sorted(set(removed))
