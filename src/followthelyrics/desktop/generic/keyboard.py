from PyQt6.QtCore import Qt

Key = Qt.Key

QT_TO_VIRTUAL_KEY = {
    Key.Key_Backspace: 0x08,
    Key.Key_Tab: 0x09,
    Key.Key_Return: 0x0D,
    Key.Key_Enter: 0x0D,
    Key.Key_Shift: 0x10,
    Key.Key_Control: 0x11,
    Key.Key_Alt: 0x12,
    Key.Key_AltGr: 0x12,
    Key.Key_Pause: 0x13,
    Key.Key_Escape: 0x1B,
    Key.Key_Space: 0x20,
    Key.Key_PageUp: 0x21,
    Key.Key_PageDown: 0x22,
    Key.Key_End: 0x23,
    Key.Key_Home: 0x24,
    Key.Key_Left: 0x25,
    Key.Key_Up: 0x26,
    Key.Key_Right: 0x27,
    Key.Key_Down: 0x28,
    Key.Key_Insert: 0x2D,
    Key.Key_Delete: 0x2E,
    Key.Key_Meta: 0x5B,
    Key.Key_Super_L: 0x5B,
    Key.Key_Super_R: 0x5C,
}
LETTERS = range(Key.Key_A.value, Key.Key_Z.value + 1)
DIGITS = range(Key.Key_0.value, Key.Key_9.value + 1)
FUNCTION_KEYS = range(Key.Key_F1.value, Key.Key_F24.value + 1)
VK_F1 = 0x70


class QtKeyboard:
    def virtual_key(self, native_key, qt_key):
        if qt_key in LETTERS or qt_key in DIGITS:
            return qt_key
        if qt_key in FUNCTION_KEYS:
            return VK_F1 + qt_key - Key.Key_F1.value
        try:
            return QT_TO_VIRTUAL_KEY.get(Key(qt_key), 0)
        except ValueError:
            return 0

    def key_char(self, virtual_key):
        return None
