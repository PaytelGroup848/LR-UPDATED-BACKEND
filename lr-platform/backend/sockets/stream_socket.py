from typing import Any, cast

from flask import request
from flask_login import current_user
from flask_socketio import emit, join_room, leave_room

from backend.extensions import socketio
from backend.sockets.agent_socket import get_agent_sid
from backend.manager.stream_manager import stream_manager
from backend.services.access_policy_service import AccessPolicyService
from backend.services.audit_service import AuditService


def register_socket_events(socketio_instance=None):
    return None


def _current_user():
    return cast(Any, current_user)


def _request_sid():
    return str(getattr(cast(Any, request), 'sid', ''))


def _current_user_payload():
    user = _current_user()
    if not user or not user.is_authenticated:
        return None
    return user.to_dict()


def can_view_stream(user, agent_id):
    allowed, _ = AccessPolicyService.can_view_stream(user, agent_id)
    return allowed


def can_control_stream(user, agent_id, action, session_id=None):
    allowed, _ = AccessPolicyService.can_control_stream(user, agent_id, action, session_id=session_id)
    return allowed


def _permission_error(required_role='Admin', reason=None):
    return {'success': False, 'error': reason or 'Forbidden', 'required_role': required_role}


def _emit_agent_command(agent_id, event, payload):
    user = _current_user()
    tenant_id = user.get("tenant_id") if user and hasattr(user, "get") else None
    agent_sid = get_agent_sid(agent_id, tenant_id)
    if not agent_sid:
        return False
    cast(Any, socketio).emit(event, payload, room=agent_sid, namespace='/agent')
    return True


def _settings_from_payload(data):
    if data.get('settings'):
        return data.get('settings') or {}
    return {
        key: data[key]
        for key in ('quality', 'fps', 'width', 'height', 'monitor')
        if key in data
    }


@socketio.on('admin_start_agent_stream')
def admin_start_agent_stream(data):
    data = data or {}
    agent_id = data.get('agent_id')
    session_id = data.get('session_id')

    if not agent_id:
        emit('stream_control_result', {'success': False, 'error': 'agent_id required'})
        return
    user = _current_user()
    allowed, reason = AccessPolicyService.can_control_stream(user, agent_id, 'start', session_id=session_id)
    if not allowed:
        AuditService.log(
            'stream.start.denied',
            user=user,
            category='stream',
            session_id=session_id,
            success=False,
            reason=reason,
            metadata={'agent_id': agent_id},
        )
        emit('stream_control_result', _permission_error('Admin', reason))
        return

    settings = stream_manager.configure_stream(agent_id, _settings_from_payload(data), session_id=session_id)
    stream_manager.start_stream(agent_id, started_by=user.id, session_id=session_id)
    ok = _emit_agent_command(agent_id, 'start_stream', {'agent_id': agent_id, 'session_id': session_id, 'settings': settings})
    AuditService.log(
        'stream.start',
        user=user,
        category='stream',
        session_id=session_id,
        success=ok,
        reason=None if ok else 'Agent is not connected',
        metadata={'agent_id': agent_id, 'settings': settings},
    )
    emit('stream_control_result', {
        'success': ok,
        'action': 'start',
        'agent_id': agent_id,
        'session_id': session_id,
        'stream': stream_manager.status(agent_id, session_id=session_id),
        'error': None if ok else 'Agent is not connected',
    })


@socketio.on('admin_start_stream')
def admin_start_stream(data):
    admin_start_agent_stream(data)


@socketio.on('admin_stop_agent_stream')
def admin_stop_agent_stream(data):
    data = data or {}
    agent_id = data.get('agent_id')
    session_id = data.get('session_id')

    if not agent_id:
        emit('stream_control_result', {'success': False, 'error': 'agent_id required'})
        return
    user = _current_user()
    allowed, reason = AccessPolicyService.can_control_stream(user, agent_id, 'stop', session_id=session_id)
    if not allowed:
        AuditService.log(
            'stream.stop.denied',
            user=user,
            category='stream',
            session_id=session_id,
            success=False,
            reason=reason,
            metadata={'agent_id': agent_id},
        )
        emit('stream_control_result', _permission_error('Admin', reason))
        return

    stream_manager.stop_stream(agent_id, session_id=session_id)
    ok = _emit_agent_command(agent_id, 'stop_stream', {'agent_id': agent_id, 'session_id': session_id})
    AuditService.log(
        'stream.stop',
        user=user,
        category='stream',
        session_id=session_id,
        success=ok,
        reason=None if ok else 'Agent is not connected',
        metadata={'agent_id': agent_id},
    )
    emit('stream_control_result', {
        'success': ok,
        'action': 'stop',
        'agent_id': agent_id,
        'session_id': session_id,
        'stream': stream_manager.status(agent_id, session_id=session_id),
        'error': None if ok else 'Agent is not connected',
    })


@socketio.on('admin_stop_stream')
def admin_stop_stream(data):
    admin_stop_agent_stream(data)


@socketio.on('viewer_join_stream')
def viewer_join_stream(data):
    data = data or {}
    agent_id = data.get('agent_id')
    session_id = data.get('session_id')

    if not agent_id:
        emit('viewer_stream_result', {'success': False, 'error': 'agent_id required'})
        return
    user = _current_user()
    allowed, reason = AccessPolicyService.can_view_stream(user, agent_id, session_id=session_id)
    if not allowed:
        AuditService.log(
            'stream.join.denied',
            user=user,
            category='stream',
            session_id=session_id,
            success=False,
            reason=reason,
            metadata={'agent_id': agent_id},
        )
        emit('viewer_stream_result', _permission_error('valid session', reason))
        return

    room = stream_manager.room_name(agent_id, session_id=session_id)
    join_room(room)
    stream_manager.add_viewer(agent_id, _request_sid(), user_id=user.id, session_id=session_id)
    AuditService.log(
        'stream.join',
        user=user,
        category='stream',
        session_id=session_id,
        success=True,
        metadata={'agent_id': agent_id, 'room': room},
    )
    emit('viewer_stream_result', {
        'success': True,
        'action': 'join',
        'agent_id': agent_id,
        'session_id': session_id,
        'room': room,
        'user': _current_user_payload(),
        'stream': stream_manager.status(agent_id, session_id=session_id),
    })

    frame = stream_manager.get_frame(agent_id, session_id=session_id)
    if frame:
        emit('screen_update', {'agent_id': agent_id, 'session_id': session_id, 'frame': frame})
        emit('agent_frame', {'agent_id': agent_id, 'session_id': session_id, 'image': frame})
    frame_payload = stream_manager.get_frame_payload(agent_id, session_id=session_id)
    if frame_payload and frame_payload.get('binary'):
        emit('screen_update_binary', {
            'agent_id': agent_id,
            'session_id': session_id,
            'frame': frame_payload.get('binary'),
            'encoding': frame_payload.get('encoding'),
            'width': frame_payload.get('width'),
            'height': frame_payload.get('height'),
            'sent_at': frame_payload.get('sent_at'),
        })


@socketio.on('viewer_leave_stream')
def viewer_leave_stream(data):
    data = data or {}
    agent_id = data.get('agent_id')
    session_id = data.get('session_id')
    if agent_id:
        leave_room(stream_manager.room_name(agent_id, session_id=session_id))
    removed = stream_manager.remove_viewer(_request_sid())
    emit('viewer_stream_result', {'success': True, 'action': 'leave', 'agent_ids': removed})


@socketio.on('stream_status')
def stream_status(data=None):
    data = data or {}
    agent_id = data.get('agent_id')
    session_id = data.get('session_id')
    allowed, reason = AccessPolicyService.can_view_stream(_current_user(), agent_id, session_id=session_id)
    if not allowed:
        emit('stream_status_result', _permission_error('valid session', reason))
        return
    emit('stream_status_result', {'success': True, 'streams': stream_manager.status(agent_id, session_id=session_id)})


@socketio.on('viewer_mouse_event')
def viewer_mouse_event(data):
    data = data or {}
    agent_id = data.get('agent_id')
    session_id = data.get('session_id')
    user = _current_user()
    allowed, reason = AccessPolicyService.can_control_stream(user, agent_id, 'mouse', session_id=session_id)
    if not allowed:
        AuditService.log('stream.input.denied', user=user, category='stream', session_id=session_id, success=False, reason=reason, metadata={'agent_id': agent_id, 'type': 'mouse'})
        emit('input_control_result', _permission_error('Admin', reason))
        return
    ok = _emit_agent_command(agent_id, 'mouse_event', data)
    AuditService.log('stream.input.mouse', user=user, category='stream', session_id=session_id, success=ok, metadata={'agent_id': agent_id})
    emit('input_control_result', {'success': ok, 'type': 'mouse', 'agent_id': agent_id, 'session_id': session_id})


@socketio.on('viewer_keyboard_event')
def viewer_keyboard_event(data):
    data = data or {}
    agent_id = data.get('agent_id')
    session_id = data.get('session_id')
    user = _current_user()
    allowed, reason = AccessPolicyService.can_control_stream(user, agent_id, 'keyboard', session_id=session_id)
    if not allowed:
        AuditService.log('stream.input.denied', user=user, category='stream', session_id=session_id, success=False, reason=reason, metadata={'agent_id': agent_id, 'type': 'keyboard'})
        emit('input_control_result', _permission_error('Admin', reason))
        return
    ok = _emit_agent_command(agent_id, 'keyboard_event', data)
    AuditService.log('stream.input.keyboard', user=user, category='stream', session_id=session_id, success=ok, metadata={'agent_id': agent_id})
    emit('input_control_result', {'success': ok, 'type': 'keyboard', 'agent_id': agent_id, 'session_id': session_id})


@socketio.on('admin_input')
def admin_input(data):
    data = data or {}
    input_type = data.get('type')
    if input_type == 'mouse':
        viewer_mouse_event(data)
    elif input_type == 'keyboard':
        viewer_keyboard_event(data)
    else:
        emit('input_control_result', {'success': False, 'error': 'input type required'})


@socketio.on('disconnect')
def viewer_disconnect():
    stream_manager.remove_viewer(_request_sid())


@socketio.on('screen_frame', namespace='/agent')
def handle_screen_frame(data):
    data = data or {}
    agent_id = data.get('agent_id')
    session_id = data.get('session_id')
    frame = data.get('frame')

    if not agent_id or not frame:
        return

    metadata = {
        'width': data.get('width'),
        'height': data.get('height'),
        'sent_at': data.get('sent_at'),
        'session_id': session_id,
    }
    stream = stream_manager.update_frame(agent_id, _request_sid(), frame, metadata=metadata)
    if isinstance(frame, bytes):
        payload = {
            'agent_id': agent_id,
            'session_id': session_id,
            'frame': frame,
            'encoding': data.get('encoding') or stream.get('last_frame_encoding') or 'jpeg',
            'width': data.get('width'),
            'height': data.get('height'),
            'sent_at': data.get('sent_at'),
            'server_at': stream.get('last_frame_at').isoformat() if stream.get('last_frame_at') else None,
        }
        cast(Any, socketio).emit(
            'screen_update_binary',
            payload,
            room=stream_manager.room_name(agent_id, session_id=session_id),
            namespace='/',
        )
        return

    payload = {
        'agent_id': agent_id,
        'session_id': session_id,
        'frame': stream.get('last_frame'),
        'encoding': data.get('encoding') or stream.get('last_frame_encoding') or 'jpeg',
        'width': data.get('width'),
        'height': data.get('height'),
        'sent_at': data.get('sent_at'),
        'server_at': stream.get('last_frame_at').isoformat() if stream.get('last_frame_at') else None,
    }
    cast(Any, socketio).emit(
        'screen_update',
        payload,
        room=stream_manager.room_name(agent_id, session_id=session_id),
        namespace='/',
    )
    cast(Any, socketio).emit(
        'agent_frame',
        {'agent_id': agent_id, 'session_id': session_id, 'image': stream.get('last_frame')},
        room=stream_manager.room_name(agent_id, session_id=session_id),
        namespace='/',
    )


@socketio.on('screen_error', namespace='/agent')
def handle_screen_error(data):
    data = data or {}
    agent_id = data.get('agent_id')
    session_id = data.get('session_id')
    cast(Any, socketio).emit(
        'screen_error',
        {'agent_id': agent_id, 'session_id': session_id, 'error': data.get('error')},
        room=stream_manager.room_name(agent_id, session_id=session_id),
        namespace='/',
    )


@socketio.on('mouse_event_result', namespace='/agent')
def handle_mouse_event_result(data):
    data = data or {}
    cast(Any, socketio).emit(
        'input_control_result',
        {'type': 'mouse', **data},
        room=stream_manager.room_name(data.get('agent_id'), session_id=data.get('session_id')),
        namespace='/',
    )


@socketio.on('keyboard_event_result', namespace='/agent')
def handle_keyboard_event_result(data):
    data = data or {}
    cast(Any, socketio).emit(
        'input_control_result',
        {'type': 'keyboard', **data},
        room=stream_manager.room_name(data.get('agent_id'), session_id=data.get('session_id')),
        namespace='/',
    )
