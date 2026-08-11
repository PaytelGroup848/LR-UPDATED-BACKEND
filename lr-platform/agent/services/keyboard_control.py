import logging

try:
    import pyautogui
except ImportError:
    pyautogui = None

try:
    import win32clipboard
except ImportError:
    win32clipboard = None

logger = logging.getLogger(__name__)

# Key normalization map converting browser / JS / socket key names to pyautogui key names
KEY_MAP = {
    'control': 'ctrl',
    'controlleft': 'ctrlleft',
    'controlright': 'ctrlright',
    'ctrl': 'ctrl',
    'key_control': 'ctrl',
    'alt': 'alt',
    'altleft': 'altleft',
    'altright': 'altright',
    'key_alt': 'alt',
    'shift': 'shift',
    'shiftleft': 'shiftleft',
    'shiftright': 'shiftright',
    'key_shift': 'shift',
    'meta': 'win',
    'command': 'win',
    'windows': 'win',
    'super': 'win',
    'escape': 'esc',
    'esc': 'esc',
    'return': 'enter',
    'enter': 'enter',
    'backspace': 'backspace',
    'tab': 'tab',
    'space': 'space',
    ' ': 'space',
    'delete': 'delete',
    'del': 'delete',
    'insert': 'insert',
    'arrowup': 'up',
    'up': 'up',
    'arrowdown': 'down',
    'down': 'down',
    'arrowleft': 'left',
    'left': 'left',
    'arrowright': 'right',
    'right': 'right',
    'pageup': 'pgup',
    'prior': 'pgup',
    'pagedown': 'pgdn',
    'next': 'pgdn',
    'home': 'home',
    'end': 'end',
    'capslock': 'capslock',
    'numlock': 'numlock',
    'scrolllock': 'scrolllock',
    'printscreen': 'printscreen',
    'prtsc': 'printscreen',
    'pause': 'pause',

    # Numpad
    'numpad0': 'num0',
    'numpad1': 'num1',
    'numpad2': 'num2',
    'numpad3': 'num3',
    'numpad4': 'num4',
    'numpad5': 'num5',
    'numpad6': 'num6',
    'numpad7': 'num7',
    'numpad8': 'num8',
    'numpad9': 'num9',
    'decimal': 'decimal',
    'divide': 'divide',
    'multiply': 'multiply',
    'subtract': 'subtract',
    'add': 'add',

     # Media keys
    'volumeup': 'volumeup',
    'volumedown': 'volumedown',
    'volumemute': 'volumemute',
    'mediaplaypause': 'playpause',
    'playpause': 'playpause',
    'medianexttrack': 'nexttrack',
    'mediaprevioustrack': 'prevtrack',
    'stopmedia': 'stop',

    # Browser keys
    'browserback': 'browserback',
    'browserforward': 'browserforward',
    'browserrefresh': 'browserrefresh',
    'browserstop': 'browserstop',
    'browserhome': 'browserhome',
    'browsersearch': 'browsersearch',
    'favorites': 'favorites',

    # Extra modifiers
    'altgr': 'altgr',
    'option': 'alt',
    'optionleft': 'altleft',
    'optionright': 'altright',

     # Common aliases
    'cmd': 'win',
    'winleft': 'winleft',
    'winright': 'winright',
    'leftctrl': 'ctrlleft',
    'rightctrl': 'ctrlright',
    'leftshift': 'shiftleft',
    'rightshift': 'shiftright',
    'leftalt': 'altleft',
    'rightalt': 'altright',

     # Symbols / punctuation (agar raw key events aate hain)
    '`': '`',
    '~': '~',
    '-': '-',
    '=': '=',
    '[': '[',
    ']': ']',
    '\\': '\\',
    ';': ';',
    "'": "'",
    ',': ',',
    '.': '.',
    '/': '/',

    'f1': 'f1',
    'f2': 'f2',
    'f3': 'f3',
    'f4': 'f4',
    'f5': 'f5',
    'f6': 'f6',
    'f7': 'f7',
    'f8': 'f8',
    'f9': 'f9',
    'f10': 'f10',
    'f11': 'f11',
    'f12': 'f12',
    'f13': 'f13',
    'f14': 'f14',
    'f15': 'f15',
    'f16': 'f16',
    'f17': 'f17',
    'f18': 'f18',
    'f19': 'f19',
    'f20': 'f20',
    'f21': 'f21',
    'f22': 'f22',
    'f23': 'f23',
    'f24': 'f24',
}

for i in range(1, 13):
    KEY_MAP[f'f{i}'] = f'f{i}'
    KEY_MAP[f'key_f{i}'] = f'f{i}'


def _normalize_key(key_str):
    if not key_str:
        return ''
    raw = str(key_str).strip()
    lower = raw.lower()
    return KEY_MAP.get(lower, lower)


def set_clipboard(text: str) -> bool:
    if win32clipboard is None:
        return False
    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        if text:
            win32clipboard.SetClipboardText(str(text), win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
        return True
    except Exception as e:
        logger.error(f"Error setting clipboard: {e}")
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass
        return False


def get_clipboard() -> str:
    if win32clipboard is None:
        return ""
    try:
        win32clipboard.OpenClipboard()
        if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
            data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        elif win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_TEXT):
            data = win32clipboard.GetClipboardData(win32clipboard.CF_TEXT)
            if isinstance(data, bytes):
                data = data.decode('utf-8', errors='ignore')
        else:
            data = ""
        win32clipboard.CloseClipboard()
        return str(data or "")
    except Exception as e:
        logger.error(f"Error getting clipboard: {e}")
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass
        return ""


class KeyboardControl:
    def __init__(self):
        if pyautogui:
            pyautogui.FAILSAFE = False

    def handle_event(self, event):
        if pyautogui is None:
            return {'success': False, 'error': 'pyautogui is not installed'}

        event = event or {}
        action = str(event.get('action') or '').strip().lower()
        key = event.get('key')
        text = event.get('text')
        raw_keys = event.get('keys') or []

        # Clipboard specific actions
        if action in ('set_clipboard', 'copy_text', 'write_clipboard'):
            success = set_clipboard(text or '')
            return {'success': success, 'text': text or ''}

        if action in ('get_clipboard', 'read_clipboard'):
            clip_text = get_clipboard()
            return {'success': True, 'text': clip_text}

        if action in ('paste', 'paste_text'):
            if text:
                set_clipboard(text)
            if pyautogui:
                pyautogui.hotkey('ctrl', 'v')
            return {'success': True}

        if action == 'copy':
            if pyautogui:
                pyautogui.hotkey('ctrl', 'c')
            clip_text = get_clipboard()
            return {'success': True, 'text': clip_text}

        if action in ('press', 'down', 'up') and not key:
            return {'success': False, 'error': 'key is required'}

        norm_key = _normalize_key(key)

        if action == 'press':
            pyautogui.press(norm_key)
        elif action == 'down':
            pyautogui.keyDown(norm_key)
        elif action == 'up':
            pyautogui.keyUp(norm_key)
        elif action in ('hotkey', 'shortcut'):
            norm_keys = [_normalize_key(k) for k in raw_keys if k]
            if norm_keys:
                pyautogui.hotkey(*norm_keys)
        elif action == 'write':
            text_val = str(text or '')
            if text_val:
                if len(text_val) > 1 or any(ord(c) > 127 for c in text_val):
                    set_clipboard(text_val)
                    pyautogui.hotkey('ctrl', 'v')
                else:
                    pyautogui.write(text_val, interval=float(event.get('interval', 0)))
        else:
            return {'success': False, 'error': f'Unknown keyboard action: {action}'}

        return {'success': True}
