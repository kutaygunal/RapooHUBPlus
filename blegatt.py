"""Win32 Bluetooth LE GATT access (BluetoothApis.dll) to the MT760's Telink service.

WinRT refuses the 00010203-0405-0607-0809-0a0b0c0dba01 service (the HID driver owns it), but the
Win32 GATT API that Qt (and so A HUB) uses can open it as a device interface. Requests go to
characteristic ...ba03 and replies arrive as notifications from ...ba02.
"""
import ctypes as C
import ctypes.wintypes as W
import threading
import uuid

setupapi = C.WinDLL("setupapi", use_last_error=True)
kernel32 = C.WinDLL("kernel32", use_last_error=True)
bt = C.WinDLL("BluetoothApis", use_last_error=True)

DIGCF_PRESENT, DIGCF_DEVICEINTERFACE = 0x2, 0x10
GENERIC_READ, GENERIC_WRITE = 0x80000000, 0x40000000
OPEN_EXISTING = 3
BLUETOOTH_GATT_FLAG_NONE = 0
BLUETOOTH_GATT_FLAG_WRITE_WITHOUT_RESPONSE = 0x4
CharacteristicValueChangedEvent = 0
ClientCharacteristicConfiguration = 2  # BTH_LE_GATT_DESCRIPTOR_TYPE
HRESULT_MORE_DATA = 0x800700EA


class GUID(C.Structure):
    _fields_ = [("Data1", W.DWORD), ("Data2", W.WORD), ("Data3", W.WORD), ("Data4", C.c_ubyte * 8)]

    @classmethod
    def of(cls, text):
        u = uuid.UUID(text)
        g = cls(u.time_low, u.time_mid, u.time_hi_version)
        g.Data4[:] = list(u.bytes[8:])
        return g

    def text(self):
        return str(uuid.UUID(bytes_le=bytes(self)))


class _UU(C.Union):
    _fields_ = [("ShortUuid", W.USHORT), ("LongUuid", GUID)]


class BTH_LE_UUID(C.Structure):
    _fields_ = [("IsShortUuid", C.c_ubyte), ("Value", _UU)]

    def text(self):
        if self.IsShortUuid:
            return f"0000{self.Value.ShortUuid:04x}-0000-1000-8000-00805f9b34fb"
        return self.Value.LongUuid.text()


class BTH_LE_GATT_CHARACTERISTIC(C.Structure):
    _fields_ = [("ServiceHandle", W.USHORT), ("CharacteristicUuid", BTH_LE_UUID),
                ("AttributeHandle", W.USHORT), ("CharacteristicValueHandle", W.USHORT),
                ("IsBroadcastable", C.c_ubyte), ("IsReadable", C.c_ubyte), ("IsWritable", C.c_ubyte),
                ("IsWritableWithoutResponse", C.c_ubyte), ("IsSignedWritable", C.c_ubyte),
                ("IsNotifiable", C.c_ubyte), ("IsIndicatable", C.c_ubyte), ("HasExtendedProperties", C.c_ubyte)]


class BTH_LE_GATT_DESCRIPTOR(C.Structure):
    _fields_ = [("ServiceHandle", W.USHORT), ("CharacteristicHandle", W.USHORT),
                ("DescriptorType", C.c_int), ("DescriptorUuid", BTH_LE_UUID), ("AttributeHandle", W.USHORT)]


class _CCC(C.Structure):
    _fields_ = [("IsSubscribeToNotification", C.c_ubyte), ("IsSubscribeToIndication", C.c_ubyte)]


class _DescUnion(C.Union):
    _fields_ = [("ClientCharacteristicConfiguration", _CCC), ("pad", C.c_ubyte * 16)]


class BTH_LE_GATT_DESCRIPTOR_VALUE(C.Structure):
    _fields_ = [("DescriptorType", C.c_int), ("DescriptorUuid", BTH_LE_UUID), ("u", _DescUnion),
                ("DataSize", W.ULONG), ("Data", C.c_ubyte * 1)]


class VALUE_CHANGED_REGISTRATION(C.Structure):
    _fields_ = [("NumCharacteristics", W.USHORT), ("Characteristics", BTH_LE_GATT_CHARACTERISTIC * 1)]


class VALUE_CHANGED_EVENT(C.Structure):
    _fields_ = [("ChangedAttributeHandle", W.USHORT), ("CharacteristicValueDataSize", C.c_size_t),
                ("CharacteristicValue", C.c_void_p)]


class SP_DEVICE_INTERFACE_DATA(C.Structure):
    _fields_ = [("cbSize", W.DWORD), ("InterfaceClassGuid", GUID), ("Flags", W.DWORD), ("Reserved", C.c_void_p)]


EVENT_CB = C.WINFUNCTYPE(None, C.c_int, C.c_void_p, C.c_void_p)

setupapi.SetupDiGetClassDevsW.restype = C.c_void_p
setupapi.SetupDiGetClassDevsW.argtypes = [C.POINTER(GUID), W.LPCWSTR, W.HWND, W.DWORD]
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [C.c_void_p, C.c_void_p, C.POINTER(GUID), W.DWORD,
                                                 C.POINTER(SP_DEVICE_INTERFACE_DATA)]
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [C.c_void_p, C.POINTER(SP_DEVICE_INTERFACE_DATA),
                                                      C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p]
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [C.c_void_p]
kernel32.CreateFileW.restype = C.c_void_p
kernel32.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, C.c_void_p]
kernel32.CloseHandle.argtypes = [C.c_void_p]
bt.BluetoothGATTGetCharacteristics.argtypes = [C.c_void_p, C.c_void_p, W.USHORT,
                                               C.POINTER(BTH_LE_GATT_CHARACTERISTIC), C.POINTER(W.USHORT), W.ULONG]
bt.BluetoothGATTGetCharacteristics.restype = C.c_long
bt.BluetoothGATTGetDescriptors.argtypes = [C.c_void_p, C.POINTER(BTH_LE_GATT_CHARACTERISTIC), W.USHORT,
                                           C.POINTER(BTH_LE_GATT_DESCRIPTOR), C.POINTER(W.USHORT), W.ULONG]
bt.BluetoothGATTGetDescriptors.restype = C.c_long
bt.BluetoothGATTSetDescriptorValue.argtypes = [C.c_void_p, C.POINTER(BTH_LE_GATT_DESCRIPTOR),
                                               C.POINTER(BTH_LE_GATT_DESCRIPTOR_VALUE), W.ULONG]
bt.BluetoothGATTSetDescriptorValue.restype = C.c_long
bt.BluetoothGATTSetCharacteristicValue.argtypes = [C.c_void_p, C.POINTER(BTH_LE_GATT_CHARACTERISTIC),
                                                   C.c_void_p, C.c_uint64, W.ULONG]
bt.BluetoothGATTSetCharacteristicValue.restype = C.c_long
bt.BluetoothGATTRegisterEvent.argtypes = [C.c_void_p, C.c_int, C.c_void_p, EVENT_CB, C.c_void_p,
                                          C.POINTER(C.c_void_p), W.ULONG]
bt.BluetoothGATTRegisterEvent.restype = C.c_long
bt.BluetoothGATTUnregisterEvent.argtypes = [C.c_void_p, W.ULONG]
bt.BluetoothGATTUnregisterEvent.restype = C.c_long


class GattError(OSError):
    pass


def service_paths(service_uuid, address=None):
    """Device-interface paths of a GATT service on currently present devices."""
    g = GUID.of(service_uuid)
    h = setupapi.SetupDiGetClassDevsW(C.byref(g), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    out, i = [], 0
    try:
        while True:
            d = SP_DEVICE_INTERFACE_DATA()
            d.cbSize = C.sizeof(d)
            if not setupapi.SetupDiEnumDeviceInterfaces(h, None, C.byref(g), i, C.byref(d)):
                break
            i += 1
            need = W.DWORD()
            setupapi.SetupDiGetDeviceInterfaceDetailW(h, C.byref(d), None, 0, C.byref(need), None)
            buf = C.create_string_buffer(need.value)
            C.cast(buf, C.POINTER(W.DWORD))[0] = 8 if C.sizeof(C.c_void_p) == 8 else 6
            setupapi.SetupDiGetDeviceInterfaceDetailW(h, C.byref(d), buf, need, None, None)
            p = C.wstring_at(C.addressof(buf) + 4)
            if address is None or f"{address:012x}" in p.lower():
                out.append(p)
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(h)
    return out


class GattChannel:
    """Write to one characteristic, receive notifications from another, on one GATT service."""

    def __init__(self, path, write_uuid, notify_uuid, on_notify):
        self.h = kernel32.CreateFileW(path, GENERIC_READ | GENERIC_WRITE, 3, None, OPEN_EXISTING, 0, None)
        if not self.h or self.h == C.c_void_p(-1).value:
            raise GattError(f"cannot open GATT service ({C.get_last_error()})")
        self.event = C.c_void_p()
        self._cb = EVENT_CB(self._on_event)  # keep a reference for the lifetime of the channel
        self.on_notify = on_notify
        try:
            chars = self._characteristics()
            self.write_char = self._find(chars, write_uuid)
            self.notify_char = self._find(chars, notify_uuid)
            self._subscribe()
        except Exception:
            self.close()
            raise

    def _characteristics(self):
        n = W.USHORT()
        bt.BluetoothGATTGetCharacteristics(self.h, None, 0, None, C.byref(n), BLUETOOTH_GATT_FLAG_NONE)
        arr = (BTH_LE_GATT_CHARACTERISTIC * max(1, n.value))()
        hr = bt.BluetoothGATTGetCharacteristics(self.h, None, n.value, arr, C.byref(n), BLUETOOTH_GATT_FLAG_NONE)
        if hr != 0:
            raise GattError(f"GetCharacteristics failed (0x{hr & 0xffffffff:08x})")
        return list(arr[:n.value])

    @staticmethod
    def _find(chars, want):
        for c in chars:
            if c.CharacteristicUuid.text() == want:
                return c
        raise GattError(f"characteristic {want} not found")

    def _subscribe(self):
        n = W.USHORT()
        bt.BluetoothGATTGetDescriptors(self.h, C.byref(self.notify_char), 0, None, C.byref(n), 0)
        descs = (BTH_LE_GATT_DESCRIPTOR * max(1, n.value))()
        bt.BluetoothGATTGetDescriptors(self.h, C.byref(self.notify_char), n.value, descs, C.byref(n), 0)
        for d in descs[:n.value]:
            if d.DescriptorType == ClientCharacteristicConfiguration:
                v = BTH_LE_GATT_DESCRIPTOR_VALUE()
                v.DescriptorType = ClientCharacteristicConfiguration
                v.u.ClientCharacteristicConfiguration.IsSubscribeToNotification = 1
                hr = bt.BluetoothGATTSetDescriptorValue(self.h, C.byref(d), C.byref(v), 0)
                if hr != 0:
                    raise GattError(f"enabling notifications failed (0x{hr & 0xffffffff:08x})")
        reg = VALUE_CHANGED_REGISTRATION(1)
        reg.Characteristics[0] = self.notify_char
        hr = bt.BluetoothGATTRegisterEvent(self.h, CharacteristicValueChangedEvent, C.byref(reg), self._cb,
                                           None, C.byref(self.event), 0)
        if hr != 0:
            raise GattError(f"RegisterEvent failed (0x{hr & 0xffffffff:08x})")

    def _on_event(self, event_type, out, context):
        try:
            ev = VALUE_CHANGED_EVENT.from_address(out)
            size = C.c_ulong.from_address(ev.CharacteristicValue).value
            data = C.string_at(ev.CharacteristicValue + 4, size)
            self.on_notify(data)
        except Exception:
            pass

    def write(self, data, without_response=True):
        data = bytes(data)
        buf = C.create_string_buffer(4 + len(data))
        C.c_ulong.from_buffer(buf).value = len(data)
        C.memmove(C.addressof(buf) + 4, data, len(data))
        flags = BLUETOOTH_GATT_FLAG_WRITE_WITHOUT_RESPONSE if without_response else BLUETOOTH_GATT_FLAG_NONE
        hr = bt.BluetoothGATTSetCharacteristicValue(self.h, C.byref(self.write_char), buf, 0, flags)
        if hr != 0:
            raise GattError(f"write failed (0x{hr & 0xffffffff:08x})")

    def close(self):
        if self.event:
            bt.BluetoothGATTUnregisterEvent(self.event, 0)
            self.event = C.c_void_p()
        if self.h:
            kernel32.CloseHandle(self.h)
            self.h = None
