import ctypes as C, ctypes.wintypes as W, threading
hid=C.WinDLL('hid'); sa=C.WinDLL('setupapi'); k=C.WinDLL('kernel32',use_last_error=True)
class GUID(C.Structure): _fields_=[('a',W.DWORD),('b',W.WORD),('c',W.WORD),('d',C.c_ubyte*8)]
class IDD(C.Structure): _fields_=[('cbSize',W.DWORD),('g',GUID),('f',W.DWORD),('r',C.c_void_p)]
class CAPS(C.Structure): _fields_=[('Usage',W.USHORT),('UsagePage',W.USHORT),('In',W.USHORT),('Out',W.USHORT),('Feat',W.USHORT),('r',W.USHORT*17),('nLinkColl',W.USHORT),('nInBtn',W.USHORT),('nInVal',W.USHORT),('nInData',W.USHORT),('nOutBtn',W.USHORT),('nOutVal',W.USHORT),('nOutData',W.USHORT),('nFeatBtn',W.USHORT),('nFeatVal',W.USHORT),('nFeatData',W.USHORT)]
class VCAPS(C.Structure): _fields_=[('UsagePage',W.USHORT),('ReportID',C.c_ubyte),('rest',C.c_ubyte*69)]
k.CreateFileW.restype=C.c_void_p; sa.SetupDiGetClassDevsW.restype=C.c_void_p
def paths(filt):
    g=GUID(); hid.HidD_GetHidGuid(C.byref(g)); h=sa.SetupDiGetClassDevsW(C.byref(g),None,None,0x12); i=0; out=[]
    while True:
        d=IDD(); d.cbSize=C.sizeof(IDD)
        if not sa.SetupDiEnumDeviceInterfaces(C.c_void_p(h),None,C.byref(g),i,C.byref(d)): break
        i+=1; need=W.DWORD(); sa.SetupDiGetDeviceInterfaceDetailW(C.c_void_p(h),C.byref(d),None,0,C.byref(need),None)
        buf=C.create_string_buffer(need.value); C.cast(buf,C.POINTER(W.DWORD))[0]=8 if C.sizeof(C.c_void_p)==8 else 6
        sa.SetupDiGetDeviceInterfaceDetailW(C.c_void_p(h),C.byref(d),buf,need,None,None)
        p=C.wstring_at(C.addressof(buf)+4)
        if all(f in p.lower() for f in filt): out.append(p)
    return out
class Dev:
    def __init__(s,path):
        s.h=k.CreateFileW(path,0xC0000000,3,None,3,0,None)
        if s.h in (None,C.c_void_p(-1).value): raise OSError(C.get_last_error())
        pp=C.c_void_p(); hid.HidD_GetPreparsedData(C.c_void_p(s.h),C.byref(pp)); s.caps=CAPS(); hid.HidP_GetCaps(pp,C.byref(s.caps)); s.pp=pp
    def rids(s,kind):
        n=W.USHORT(64); arr=(VCAPS*64)(); hid.HidP_GetValueCaps(kind,arr,C.byref(n),s.pp)
        return sorted({arr[i].ReportID for i in range(n.value)})
    def write(s,data):
        b=bytes(data).ljust(s.caps.Out,b'\0'); w=W.DWORD()
        ok=k.WriteFile(C.c_void_p(s.h),b,len(b),C.byref(w),None); return ok,C.get_last_error()
    def read(s,timeout=1.0):
        res={}
        def r():
            b=C.create_string_buffer(s.caps.In); n=W.DWORD()
            if k.ReadFile(C.c_void_p(s.h),b,s.caps.In,C.byref(n),None): res['d']=b.raw[:n.value]
        t=threading.Thread(target=r,daemon=True); t.start(); t.join(timeout)
        if t.is_alive(): k.CancelIoEx(C.c_void_p(s.h),None); t.join(0.5)
        return res.get('d')
    def close(s): k.CloseHandle(C.c_void_p(s.h))
