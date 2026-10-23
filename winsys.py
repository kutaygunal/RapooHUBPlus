"""Windows mouse settings (the same ones A HUB's Parameter page changes)."""
import ctypes as C
import ctypes.wintypes as W

user32 = C.WinDLL("user32", use_last_error=True)
user32.SystemParametersInfoW.argtypes = [W.UINT, W.UINT, C.c_void_p, W.UINT]

SPI_GETWHEELSCROLLLINES, SPI_SETWHEELSCROLLLINES = 0x0068, 0x0069
SPI_GETMOUSESPEED, SPI_SETMOUSESPEED = 0x0070, 0x0071
SPIF_UPDATE_AND_BROADCAST = 0x01 | 0x02
WHEEL_PAGESCROLL = 0xFFFFFFFF


def wheel_lines():
    """Lines per wheel notch, or -1 for 'one page at a time'."""
    v = W.UINT()
    user32.SystemParametersInfoW(SPI_GETWHEELSCROLLLINES, 0, C.byref(v), 0)
    return -1 if v.value == WHEEL_PAGESCROLL else v.value


def set_wheel_lines(lines):
    value = WHEEL_PAGESCROLL if lines < 0 else max(1, min(100, lines))
    user32.SystemParametersInfoW(SPI_SETWHEELSCROLLLINES, value, None, SPIF_UPDATE_AND_BROADCAST)


def pointer_speed():
    v = C.c_int()
    user32.SystemParametersInfoW(SPI_GETMOUSESPEED, 0, C.byref(v), 0)
    return v.value


def set_pointer_speed(speed):
    # SPI_SETMOUSESPEED takes the value itself in pvParam
    user32.SystemParametersInfoW(SPI_SETMOUSESPEED, 0, C.c_void_p(max(1, min(20, speed))),
                                 SPIF_UPDATE_AND_BROADCAST)
