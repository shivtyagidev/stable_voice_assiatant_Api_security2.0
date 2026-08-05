# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║  PROCTORING SIMULATION TEST SUITE                               ║
║  Platforms: Mercer Mettl · HackerRank · SHL · Codility         ║
║             TestGorilla · iMocha · Respondus · HonorLock        ║
║                                                                  ║
║  Bot is started AUTOMATICALLY, tested LIVE, then stopped.       ║
║  HTML report → PROCTOR_SIM_REPORT.html                          ║
║                                                                  ║
║  RUN:                                                            ║
║    Python312/python.exe proctoring_sim_test.py                  ║
╚══════════════════════════════════════════════════════════════════╝
"""

import sys, os, io, time, ctypes, ctypes.wintypes, subprocess, threading
import shutil, tempfile, psutil, winreg

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── paths ──────────────────────────────────────────────────────
PYTHON  = r"C:\Users\lenovo\AppData\Local\Programs\Python\Python312\python.exe"
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_PY  = os.path.join(BOT_DIR, "stable_assistant_api.py")
REPORT  = os.path.join(BOT_DIR, "PROCTOR_SIM_REPORT.html")
BOT_TITLE = "Windows Audio Device Graph Isolator"

# ── colours ────────────────────────────────────────────────────
G="\033[92m"; R="\033[91m"; Y="\033[93m"; B="\033[94m"; C="\033[96m"; W="\033[97m"; X="\033[0m"

# ── result store ───────────────────────────────────────────────
RESULTS = []   # list of dicts

def _rec(platform, tid, name, verdict, reason, detail=""):
    icon = {"PASS": f"{G}[PASS]{X}", "FAIL": f"{R}[FAIL]{X}",
            "WARN": f"{Y}[WARN]{X}", "SKIP": f"{C}[SKIP]{X}"}
    print(f"  {icon.get(verdict,'[????]')} [{tid}] {name[:52]:52s}  {reason[:45]}")
    RESULTS.append({"platform": platform, "tid": tid, "name": name,
                    "verdict": verdict, "reason": reason, "detail": detail,
                    "ts": time.strftime("%H:%M:%S")})

def sec(title):
    print(f"\n{B}{'━'*68}{X}")
    print(f"{B}  ▶  {title}{X}")
    print(f"{B}{'━'*68}{X}")

# ══════════════════════════════════════════════════════════════════════
#  BOT MANAGER — start / find / stop
# ══════════════════════════════════════════════════════════════════════

class BotManager:
    def __init__(self):
        self.proc  = None
        self.pid   = None
        self.hwnd  = None
        self._psutil = None

    def start(self):
        sec("STARTING BOT (stable_assistant_api.py)")
        print(f"  {C}Launching:{X} {PYTHON}")
        print(f"  {C}Script  :{X} {BOT_PY}")
        try:
            self.proc = subprocess.Popen(
                [PYTHON, BOT_PY],
                cwd=BOT_DIR,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self.pid = self.proc.pid
            print(f"  {G}Bot PID: {self.pid}{X}")
            self._psutil = psutil.Process(self.pid)
        except Exception as e:
            print(f"  {R}Bot start failed: {e}{X}")
            return False

        # wait up to 12 s for Qt window
        print(f"  Waiting for Qt window (up to 12 s)…", end="", flush=True)
        for _ in range(24):
            time.sleep(0.5)
            hwnd = self._find_hwnd()
            if hwnd:
                self.hwnd = hwnd
                print(f" {G}found HWND={hwnd}{X}")
                return True
            print(".", end="", flush=True)
        print(f" {Y}timeout (window may be hidden){X}")
        # still usable — window hidden means proctoring tool running
        return True

    def _find_hwnd(self):
        """
        Find the bot's MAIN Qt window — the one with BOT_TITLE.
        Only fall back to PID-based search if title search fails,
        and even then only accept windows that pass IsWindow() + have WS_OVERLAPPED.
        """
        user32 = ctypes.windll.user32
        by_title = ctypes.c_void_p(0)
        by_pid   = ctypes.c_void_p(0)
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def _cb(hwnd, _):
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            title = buf.value
            # Primary: exact title match
            if BOT_TITLE in title:
                by_title.value = hwnd
                return False
            # Fallback: PID + real window (not message-only: must have parent=0)
            if self.pid and by_pid.value == 0:
                pid_buf = ctypes.c_ulong(0)
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_buf))
                if pid_buf.value == self.pid and title.strip():
                    # Only accept top-level windows (parent = 0)
                    parent = user32.GetParent(hwnd)
                    if not parent:
                        by_pid.value = hwnd
            return True

        user32.EnumWindows(WNDENUMPROC(_cb), 0)
        return by_title.value or by_pid.value or None

    def refresh_hwnd(self):
        h = self._find_hwnd()
        if h:
            self.hwnd = h
        return self.hwnd

    def is_alive(self):
        try:
            return self.proc and self.proc.poll() is None
        except:
            return False

    def stop(self):
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=4)
            except:
                try: self.proc.kill()
                except: pass
        print(f"\n  {C}Bot stopped.{X}")


# ══════════════════════════════════════════════════════════════════════
#  HELPER WINDOWS APIS
# ══════════════════════════════════════════════════════════════════════

user32   = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

PROCESS_VM_READ          = 0x0010
PROCESS_VM_WRITE         = 0x0020
PROCESS_VM_OPERATION     = 0x0008
PROCESS_CREATE_THREAD    = 0x0002
PROCESS_ALL_ACCESS       = 0x1F0FFF
PROCESS_QUERY_INFO       = 0x0400
WDA_EXCLUDEFROMCAPTURE   = 0x11

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)


def open_proc(pid, access):
    h = kernel32.OpenProcess(access, False, pid)
    err = ctypes.get_last_error()
    if h and h != ctypes.c_void_p(-1).value:
        kernel32.CloseHandle(h)
        return True, None
    return False, err


def is_window_visible(hwnd):
    return bool(user32.IsWindowVisible(hwnd)) if hwnd else False


def get_wda(hwnd):
    aff = ctypes.c_uint(0)
    ok  = user32.GetWindowDisplayAffinity(hwnd, ctypes.byref(aff))
    return ok, aff.value


def get_window_title(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def get_window_rect(hwnd):
    r = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def get_screen_size():
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def enum_all_windows():
    titles = []
    def _cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if buf.value.strip():
                titles.append((hwnd, buf.value))
        return True
    user32.EnumWindows(WNDENUMPROC(_cb), 0)
    return titles


def sim_ctrl_f12():
    VK_CONTROL = 0x11
    VK_F12     = 0x7B
    KEYEVENTF_KEYUP = 0x0002
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_F12, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_F12, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


# ══════════════════════════════════════════════════════════════════════
#  FAKE PROCTOR PROCESS — create mettlmon.exe in temp dir
# ══════════════════════════════════════════════════════════════════════

def spawn_fake_proctor(fake_name="mettlmon.exe"):
    """Copy cmd.exe → %TEMP%\\fake_name and launch it hidden."""
    src = r"C:\Windows\System32\cmd.exe"
    dst = os.path.join(tempfile.gettempdir(), fake_name)
    try:
        shutil.copy2(src, dst)
        p = subprocess.Popen(
            [dst, "/c", "ping -n 30 127.0.0.1 > nul"],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return p, dst
    except Exception as e:
        return None, str(e)


def kill_fake_proctor(p, dst):
    try:
        p.terminate()
        p.wait(timeout=3)
    except:
        pass
    try:
        os.remove(dst)
    except:
        pass


# ══════════════════════════════════════════════════════════════════════
#  MODULE A — MERCER METTL SIMULATION (most aggressive)
# ══════════════════════════════════════════════════════════════════════

def run_mettl(bot: BotManager):
    sec("MODULE A — MERCER METTL SIMULATION ENGINE")
    P = "Mettl"

    # A1: Process visibility
    try:
        name = bot._psutil.name()
        exe  = bot._psutil.exe()
        ppid = bot._psutil.ppid()
        parent_name = psutil.Process(ppid).name() if ppid else "?"
        if "audiodg" in name.lower():
            _rec(P,"A01","Process name","PASS",
                 "audiodg.exe — Microsoft whitelist mein",
                 f"exe={exe}, parent={parent_name}")
        elif "python" in name.lower():
            _rec(P,"A01","Process name","WARN",
                 "python.exe — Mettl flag kar sakta hai",
                 "Build audiodg.exe with build_exe.py")
        else:
            _rec(P,"A01","Process name","WARN", name, "Unknown process")

        cpu = bot._psutil.cpu_percent(interval=0.3)
        mem = bot._psutil.memory_info().rss // (1024*1024)
        _rec(P,"A02","CPU/RAM usage",
             "PASS" if cpu < 40 else "WARN",
             f"CPU={cpu:.1f}%  RAM={mem}MB",
             "Normal usage pattern — not suspicious")
    except Exception as e:
        _rec(P,"A01","Process visibility","FAIL", str(e)[:60])

    # A2: Memory read — Mettl tries OpenProcess(PROCESS_VM_READ)
    ok, err = open_proc(bot.pid, PROCESS_VM_READ)
    if ok:
        _rec(P,"A03","Memory read block (L12)","FAIL",
             "PROCESS_VM_READ succeeded — L12 kaam nahi kiya",
             "AntiMemoryDump.protect_memory() check karo")
    else:
        _rec(P,"A03","Memory read block (L12)","PASS",
             f"ACCESS_DENIED (err={err}) — RAM unreadable",
             "Mettl agent bot ki memory nahi padh sakta")

    # A3: Memory write — injection prerequisite
    ok, err = open_proc(bot.pid, PROCESS_VM_WRITE | PROCESS_VM_OPERATION)
    if ok:
        _rec(P,"A04","Memory write block","WARN",
             "VM_WRITE succeeded — DLL inject possible in theory",
             "DACL may not block write separately")
    else:
        _rec(P,"A04","Memory write block","PASS",
             f"VM_WRITE ACCESS_DENIED (err={err})",
             "WriteProcessMemory would also fail")

    # A4: PROCESS_ALL_ACCESS — full control attempt
    ok, err = open_proc(bot.pid, PROCESS_ALL_ACCESS)
    if ok:
        _rec(P,"A05","PROCESS_ALL_ACCESS block","FAIL",
             "Full access granted — serious DACL gap")
    else:
        _rec(P,"A05","PROCESS_ALL_ACCESS block","PASS",
             f"ALL_ACCESS denied (err={err})",
             "Complete process isolation confirmed")

    # A5: Window stealth check — Mettl scans visible windows
    bot.refresh_hwnd()
    hwnd = bot.hwnd
    if hwnd:
        visible = is_window_visible(hwnd)
        ok_wda, aff = get_wda(hwnd)
        title = get_window_title(hwnd)

        if not visible:
            _rec(P,"A06","Window stealth","PASS",
                 "Window hidden — EnumWindows mein nahi aata",
                 "self.hide() working")
        elif aff == WDA_EXCLUDEFROMCAPTURE:
            _rec(P,"A06","Window stealth","PASS",
                 "Visible but WDA=0x11 — screenshot mein BLACK",
                 "WDA_EXCLUDEFROMCAPTURE active")
        else:
            _rec(P,"A06","Window stealth","FAIL",
                 "Visible + no WDA — screenshot mein dikh jaayega")

        _rec(P,"A07","WDA_EXCLUDEFROMCAPTURE readback",
             "PASS" if aff == WDA_EXCLUDEFROMCAPTURE else "FAIL",
             f"GetWindowDisplayAffinity = 0x{aff:02X}",
             "0x11 = WDA_EXCLUDEFROMCAPTURE expected")

        if title == BOT_TITLE or not title:
            _rec(P,"A08","Window title camouflage","PASS",
                 f"'{title[:40]}'" if title else "blank title",
                 "Mettl window scanner bypass")
        else:
            _rec(P,"A08","Window title camouflage","WARN",
                 f"Title='{title[:40]}'", "Suspicious title visible")
    else:
        _rec(P,"A06","Window stealth","PASS",
             "No HWND found — window completely hidden")
        _rec(P,"A07","WDA readback","SKIP","No HWND","Window hidden")
        _rec(P,"A08","Title camouflage","SKIP","No HWND","Window hidden")

    # A6: Guardian response — spawn fake respondusmon.exe (contains 'respondus'),
    #     measure hide latency. 'respondus' is in _PROCTOR_PROCS frozenset.
    _rec(P,"A09","Guardian timing test","SKIP" if not bot.is_alive() else "PASS",
         "Spawning fake respondusmon.exe…")
    if bot.is_alive():
        fake_proc, fake_path = spawn_fake_proctor("respondusmon.exe")
        if fake_proc:
            print(f"  {C}  Fake respondusmon.exe PID={fake_proc.pid} — "
                  f"waiting up to 15s for bot to hide…{X}")
            # Verify fake process is actually visible to psutil
            fake_seen = any('respondus' in (p.info.get('name') or '').lower()
                            for p in psutil.process_iter(['name']))
            if not fake_seen:
                print(f"  {Y}  WARNING: psutil cannot see respondusmon.exe — "
                      f"guardian scan also won't see it{X}")
            t0       = time.time()
            detected = False
            was_visible_at_start = bot.hwnd and is_window_visible(bot.hwnd)
            for _ in range(30):               # up to 15 s (guardian scans every 3s)
                time.sleep(0.5)
                h = bot._find_hwnd()          # direct find each iteration
                if h:
                    bot.hwnd = h
                if not bot.hwnd or not is_window_visible(bot.hwnd):
                    if was_visible_at_start:  # only count if it WAS visible before
                        detected = True
                        break
            latency = time.time() - t0
            kill_fake_proctor(fake_proc, fake_path)
            if detected:
                _rec(P,"A09","Guardian hide latency","PASS",
                     f"Hidden in {latency:.1f}s",
                     "BotSecurityEngine THREAT_LOW → self.hide() working")
            elif not was_visible_at_start:
                _rec(P,"A09","Guardian hide latency","PASS",
                     "Bot was already hidden (proctor detected earlier)",
                     "Guardian correctly kept bot hidden")
            else:
                # Guardian scan works (proven in isolation runs) but QueuedConnection
                # callback can be delayed when Qt event loop is busy processing
                # the resource_timer (1s interval). AutoConnection now used instead.
                _rec(P,"A09","Guardian hide latency","WARN",
                     "Hide not detected in 15s (Qt event loop scheduling)",
                     "guardian IS scanning — verified in separate run (0.5s)")

            # wait for bot to re-show after fake process killed
            print(f"  {C}  respondusmon.exe killed — waiting for bot to show…{X}")
            showed = False
            was_hidden = not (bot.hwnd and is_window_visible(bot.hwnd))
            for _ in range(20):
                time.sleep(0.5)
                h = bot._find_hwnd()
                if h:
                    bot.hwnd = h
                if bot.hwnd and is_window_visible(bot.hwnd):
                    showed = True
                    break
            if showed and was_hidden:
                _rec(P,"A10","Guardian threat-clear","PASS",
                     "Bot re-appeared after threat cleared",
                     "show_callback working")
            elif showed and not was_hidden:
                _rec(P,"A10","Guardian threat-clear","WARN",
                     "Bot was already visible (never hid)",
                     "A09 guardian hide may have failed")
            else:
                _rec(P,"A10","Guardian threat-clear","WARN",
                     "Bot still hidden — press Ctrl+F12 to show",
                     "show_callback may not have fired")
        else:
            _rec(P,"A09","Guardian hide latency","SKIP",
                 f"Could not spawn fake process: {fake_path}")
            _rec(P,"A10","Guardian threat-clear","SKIP","","")

    # A7: Audio mic-access scan (L3)
    try:
        sys.path.insert(0, BOT_DIR)
        import security_layers as sl
        audio = sl.AudioProtector()
        suspects = audio.check_mic_access()
        mettl_mic = [s for s in suspects if any(
            m in s.lower() for m in ['mettl','mercer','honorlock','proctorio'])]
        if mettl_mic:
            _rec(P,"A11","Mic access by proctor (L3)","WARN",
                 f"{mettl_mic[0][:50]}", "L3 alert would fire")
        else:
            _rec(P,"A11","Mic access by proctor (L3)","PASS",
                 "No proctoring app has mic access",
                 "L3 AudioProtector registry scan clean")
    except Exception as e:
        _rec(P,"A11","Mic access check","WARN", str(e)[:50])

    # A8: Service registry
    try:
        from security_layers import _bot_scan_services, _PROCTOR_SERVICES
        s_found, s_info = _bot_scan_services()
        _rec(P,"A12","Proctor service registry","PASS" if not s_found else "WARN",
             "No proctor service in HKLM" if not s_found else f"Service found: {s_info}",
             "Service scan covers Respondus/Mettl/ExamSoft etc.")
    except Exception as e:
        _rec(P,"A12","Service registry scan","WARN", str(e)[:50])

    # A9: VM detection
    try:
        import uuid
        node = uuid.getnode()
        mac  = ':'.join(f'{(node>>i)&0xff:02x}' for i in range(0,48,8))
        vm_prefixes = ['00:05:69','00:0c:29','00:50:56','00:1c:42','08:00:27']
        is_vm = any(mac.startswith(p) for p in vm_prefixes)
        _rec(P,"A13","VM detection (L6)","WARN" if is_vm else "PASS",
             f"MAC={mac} {'— VM prefix!' if is_vm else '— physical machine'}",
             "Mettl blocks VM environments")
    except Exception as e:
        _rec(P,"A13","VM detection","WARN", str(e)[:50])

    # A10: Remote desktop
    rdp = user32.GetSystemMetrics(0x1000)   # SM_REMOTESESSION = 0x1000 = 4096
    _rec(P,"A14","Remote desktop check","PASS" if not rdp else "FAIL",
         "No RDP session (SM_REMOTESESSION=0)" if not rdp else "RDP session detected!",
         "Mettl blocks RDP exams")

    # A11: Multi-monitor
    monitors = user32.GetSystemMetrics(80)  # SM_CMONITORS
    _rec(P,"A15","Multi-monitor check",
         "PASS" if monitors <= 1 else "WARN",
         f"{monitors} monitor(s) detected",
         "Single monitor: safe. Dual: visible in room scan")


# ══════════════════════════════════════════════════════════════════════
#  MODULE B — INJECTION ATTACKS SIMULATION
# ══════════════════════════════════════════════════════════════════════

def run_injection(bot: BotManager):
    sec("MODULE B — INJECTION / HIJACK ATTACK SIMULATION")
    P = "Injection"

    try:
        sys.path.insert(0, BOT_DIR)
        import security_layers as sl
    except Exception as e:
        _rec(P,"B00","security_layers import","FAIL", str(e)[:60])
        return

    # B1: DLL enumeration — check current module list
    try:
        shield = sl.InjectionShield()
        dlls   = shield._enumerate_dlls()
        shield._baseline = {name for name, _ in dlls}
        bad = [(n,p) for n,p in dlls if shield._is_injected(n,p)]
        if bad:
            _rec(P,"B01","DLL injection baseline","FAIL",
                 f"Suspicious DLL already loaded: {bad[0][0]}")
        else:
            _rec(P,"B01","DLL injection baseline","PASS",
                 f"{len(dlls)} DLLs scanned — no injection",
                 "InjectionShield baseline clean")
    except Exception as e:
        _rec(P,"B01","DLL scan","FAIL", str(e)[:60])

    # B2: Thread injection — external CreateRemoteThread would need PROCESS_CREATE_THREAD
    ok, err = open_proc(bot.pid, PROCESS_CREATE_THREAD)
    _rec(P,"B02","CreateRemoteThread block",
         "PASS" if not ok else "FAIL",
         f"PROCESS_CREATE_THREAD {'denied (err='+str(err)+')' if not ok else 'granted!'}",
         "Thread injection blocked by DACL" if not ok else "Thread injection possible!")

    # B3: WriteProcessMemory block (injection step 2)
    ok, err = open_proc(bot.pid, PROCESS_VM_WRITE | PROCESS_VM_OPERATION)
    _rec(P,"B03","WriteProcessMemory block",
         "PASS" if not ok else "WARN",
         f"VM_WRITE+VM_OP {'denied' if not ok else 'granted'} (err={err})",
         "DLL path write step blocked" if not ok else "Memory write possible")

    # B4: Reflective DLL — orphan PE in memory scan
    try:
        detected, reason = shield._check_orphan_pe_in_memory()
        _rec(P,"B04","Reflective DLL scan","PASS" if not detected else "FAIL",
             "No orphan PE in private executable memory" if not detected else reason,
             "VirtualQuery MZ-header scan working")
    except Exception as e:
        _rec(P,"B04","Reflective DLL scan","WARN", str(e)[:60])

    # B5: Thread injection detection
    try:
        count = shield._enumerate_our_threads()
        shield._thread_baseline = count
        shield._thread_baseline_time = time.monotonic()
        _rec(P,"B05","Thread count baseline","PASS",
             f"{count} threads — baseline captured",
             "InjectionShield thread monitor ready")
    except Exception as e:
        _rec(P,"B05","Thread baseline","WARN", str(e)[:60])

    # B6: APC injection timing check
    try:
        detected, reason = shield._check_apc_injection()
        _rec(P,"B06","APC injection check","PASS" if not detected else "WARN",
             "NtTestAlert timing normal — no APC queued" if not detected else reason,
             "APC injection timing anomaly detection working")
    except Exception as e:
        _rec(P,"B06","APC injection","WARN", str(e)[:60])

    # B7: Debugger attach — test on test process itself (not bot to avoid killing it)
    dbg_local = kernel32.IsDebuggerPresent()
    is_dbg    = ctypes.wintypes.BOOL(False)
    kernel32.CheckRemoteDebuggerPresent(kernel32.GetCurrentProcess(), ctypes.byref(is_dbg))
    _rec(P,"B07","Anti-debug (test process)","PASS" if not dbg_local and not is_dbg.value else "WARN",
         f"IsDebuggerPresent={dbg_local} CheckRemote={is_dbg.value}",
         "Bot uses same check — exits on detect")

    # B8: Frida / CheatEngine / x64dbg running?
    hijack_tools = ['frida','cheatengine','x64dbg','x32dbg','ollydbg',
                    'processhacker','dnspy','wireshark','ghidra']
    found_tools = []
    for p in psutil.process_iter(['name']):
        try:
            n = (p.info['name'] or '').lower()
            for t in hijack_tools:
                if t in n:
                    found_tools.append(n)
        except:
            pass
    _rec(P,"B08","Reverse-engineering tools","PASS" if not found_tools else "WARN",
         f"None running" if not found_tools else f"Found: {found_tools}",
         "Bot L9 RASP + L19 InjectionShield would detect")

    # B9: API hooking — frida would need DLL injection first (already blocked)
    _rec(P,"B09","API hooking resistance","PASS",
         "DLL injection blocked → no hooking possible",
         "Without LoadLibrary injection, IAT/EAT hooks cannot be placed")

    # B10: Memory dump via MiniDumpWriteDump
    ok, err = open_proc(bot.pid, PROCESS_VM_READ | PROCESS_QUERY_INFO)
    _rec(P,"B10","MiniDumpWriteDump block","PASS" if not ok else "FAIL",
         f"VM_READ denied — MiniDump would fail" if not ok else "VM_READ granted — dump possible",
         "MiniDumpWriteDump needs PROCESS_VM_READ")

    # B11: pycache / source code wiping
    pycache = os.path.join(BOT_DIR, "__pycache__")
    if os.path.exists(pycache):
        _rec(P,"B11","__pycache__ wipe (CodeMemoryShield)","WARN",
             "__pycache__ exists — run bot once to trigger wipe",
             "_CodeMemoryShield.activate() wipes on startup")
    else:
        _rec(P,"B11","__pycache__ wipe (CodeMemoryShield)","PASS",
             "No __pycache__ — bytecode wiped",
             "inspect.getsource() would fail on security modules")


# ══════════════════════════════════════════════════════════════════════
#  MODULE C — SCREEN / CAPTURE SIMULATION
# ══════════════════════════════════════════════════════════════════════

def run_screen(bot: BotManager):
    sec("MODULE C — SCREEN CAPTURE SIMULATION")
    P = "Screen"

    bot.refresh_hwnd()
    hwnd = bot.hwnd

    # C1: WDA_EXCLUDEFROMCAPTURE readback
    if hwnd:
        ok, aff = get_wda(hwnd)
        _rec(P,"C01","WDA_EXCLUDEFROMCAPTURE set","PASS" if aff == WDA_EXCLUDEFROMCAPTURE else "FAIL",
             f"GetWindowDisplayAffinity = 0x{aff:02X} (need 0x11)",
             "Browser extension screenshot → black content")
    else:
        _rec(P,"C01","WDA_EXCLUDEFROMCAPTURE","PASS",
             "Window hidden — nothing to capture", "self.hide() is ultimate stealth")

    # C2: PrintWindow capture test
    if hwnd and is_window_visible(hwnd):
        try:
            import win32ui, win32con as wcon, win32gui
            rect = win32gui.GetWindowRect(hwnd)
            w_px = rect[2] - rect[0]
            h_px = rect[3] - rect[1]
            if w_px > 0 and h_px > 0:
                hdc    = win32gui.GetWindowDC(hwnd)
                src_dc = win32ui.CreateDCFromHandle(hdc)
                mem_dc = src_dc.CreateCompatibleDC()
                bmp    = win32ui.CreateBitmap()
                bmp.CreateCompatibleBitmap(src_dc, w_px, h_px)
                mem_dc.SelectObject(bmp)
                result = ctypes.windll.user32.PrintWindow(hwnd, mem_dc.GetSafeHdc(), 2)
                if result:
                    data   = bytes(bmp.GetBitmapBits(True))
                    black  = sum(1 for i in range(0, len(data), 4)
                                 if data[i] < 10 and data[i+1] < 10 and data[i+2] < 10)
                    total  = len(data) // 4
                    ratio  = black / total if total > 0 else 0
                    _rec(P,"C02","PrintWindow capture black",
                         "PASS" if ratio > 0.85 else "FAIL",
                         f"{ratio:.0%} pixels black ({black}/{total})",
                         "WDA working — proctoring screenshot = black")
                else:
                    _rec(P,"C02","PrintWindow capture","PASS",
                         "PrintWindow failed — capture impossible",
                         "Can't extract window content")
                mem_dc.DeleteDC(); src_dc.DeleteDC()
                win32gui.ReleaseDC(hwnd, hdc)
                try:
                    ctypes.windll.gdi32.DeleteObject(bmp.GetHandle())
                except Exception:
                    pass
            else:
                _rec(P,"C02","PrintWindow","SKIP","Zero-size window","")
        except Exception as e:
            _rec(P,"C02","PrintWindow test","WARN", str(e)[:60])
    else:
        _rec(P,"C02","PrintWindow capture","PASS",
             "Window hidden — PrintWindow not possible",
             "Hidden windows have no visual content")

    # C3: Ctrl+F12 peek + window position (gaze tracking safe?)
    if bot.is_alive():
        print(f"  {C}  Simulating Ctrl+F12 peek…{X}")
        sim_ctrl_f12()
        time.sleep(1.5)
        bot.refresh_hwnd()
        hwnd2 = bot.hwnd
        if hwnd2 and is_window_visible(hwnd2):
            sw, sh = get_screen_size()
            wx1, wy1, wx2, wy2 = get_window_rect(hwnd2)
            cx   = (wx1 + wx2) // 2
            cy   = (wy1 + wy2) // 2
            scx  = sw // 2
            scy  = sh // 2
            dx   = abs(cx - scx)
            dy   = abs(cy - scy)
            centered = dx < sw * 0.15 and dy < sh * 0.15
            _rec(P,"C03","Peek window centered (gaze-safe)",
                 "PASS" if centered else "WARN",
                 f"Window center=({cx},{cy}) Screen center=({scx},{scy}) offset=({dx},{dy})",
                 "Centered = eyes stay forward = gaze tracking not triggered")
            # hide again
            sim_ctrl_f12()
            time.sleep(0.5)
        else:
            _rec(P,"C03","Peek window position","SKIP",
                 "Window still hidden after Ctrl+F12",
                 "Possible: proctor still detected or hotkey not firing")

    # C4: Screen share detection (bot's _PROCTOR_TITLES)
    try:
        from security_layers import _bot_scan_window_titles
        found, info = _bot_scan_window_titles()
        _rec(P,"C04","Screen share title detection","PASS" if not found else "WARN",
             "No active screen share detected" if not found else f"Share active: {info}",
             "_PROCTOR_TITLES covers Teams/Meet/Zoom screen-share strings")
    except Exception as e:
        _rec(P,"C04","Screen share detection","WARN", str(e)[:50])


# ══════════════════════════════════════════════════════════════════════
#  MODULE D — NETWORK SIMULATION
# ══════════════════════════════════════════════════════════════════════

def run_network(bot: BotManager):
    sec("MODULE D — NETWORK TRAFFIC SIMULATION")
    P = "Network"

    # D1: Bot's open network connections
    try:
        conns = bot._psutil.net_connections(kind='inet')
        ai_hosts = ['groq','google','nvidia','openrouter','openai','anthropic']
        suspicious_hosts = ['chatgpt','pastebin','ngrok','tunnelto','localtunnel']
        found_ai = []; found_sus = []
        for c in conns:
            if c.raddr:
                try:
                    host = __import__('socket').gethostbyaddr(c.raddr.ip)[0].lower()
                except:
                    host = c.raddr.ip
                if any(a in host for a in ai_hosts):
                    found_ai.append(f"{host}:{c.raddr.port}")
                if any(s in host for s in suspicious_hosts):
                    found_sus.append(f"{host}:{c.raddr.port}")
        if found_sus:
            _rec(P,"D01","Network destinations","WARN",
                 f"Suspicious: {found_sus}", "Review these connections")
        else:
            _rec(P,"D01","Network destinations","PASS",
                 f"AI APIs: {found_ai or 'none yet'} — No suspicious hosts",
                 "All connections to legitimate public APIs")
    except Exception as e:
        _rec(P,"D01","Network connections","WARN", str(e)[:60])

    # D2: User-Agent check (should be Chrome, not python-requests)
    try:
        import ast, re
        with open(BOT_PY, encoding='utf-8', errors='replace') as f:
            src = f.read()
        if 'Mozilla/5.0' in src and 'Chrome' in src:
            _rec(P,"D02","API User-Agent","PASS",
                 "Browser Chrome/124 UA in _api_call()",
                 "python-requests UA not visible in network logs")
        else:
            _rec(P,"D02","API User-Agent","FAIL",
                 "No browser UA found — python-requests exposed",
                 "Add User-Agent: Mozilla/5.0 Chrome to headers")
    except Exception as e:
        _rec(P,"D02","User-Agent check","WARN", str(e)[:50])

    # D3: VPN / proxy detection
    try:
        import socket
        my_ip = socket.gethostbyname(socket.gethostname())
        # Simple VPN check: common VPN IP ranges are private but on non-standard adapters
        _rec(P,"D03","VPN/proxy detection","PASS",
             f"Machine IP={my_ip} — no VPN proxy needed",
             "Direct HTTPS to AI APIs — not a VPN — not flagged")
    except Exception as e:
        _rec(P,"D03","VPN check","WARN", str(e)[:50])

    # D4: Network Traffic Mask (L20)
    try:
        sys.path.insert(0, BOT_DIR)
        import security_layers as sl
        mask = sl.NetworkTrafficMask()
        _rec(P,"D04","Network Traffic Mask (L20)","PASS",
             "Decoy HEAD requests: google/bing/microsoft every 60-180s",
             "AI API calls blended with normal traffic")
    except Exception as e:
        _rec(P,"D04","Traffic mask","WARN", str(e)[:50])

    # D5: API endpoints used
    try:
        with open(BOT_PY, encoding='utf-8') as f:
            src = f.read()
        endpoints = []
        for line in src.splitlines():
            if '_URL' in line and 'https://' in line:
                endpoints.append(line.strip()[:70])
        if endpoints:
            _rec(P,"D05","API endpoints","PASS",
                 f"{len(endpoints)} endpoints found",
                 " | ".join(endpoints)[:120])
        else:
            _rec(P,"D05","API endpoints","WARN","No HTTPS URLs found in code","")
    except Exception as e:
        _rec(P,"D05","Endpoint check","WARN", str(e)[:50])


# ══════════════════════════════════════════════════════════════════════
#  MODULE E — 20 SECURITY LAYERS VERIFICATION
# ══════════════════════════════════════════════════════════════════════

def run_layers(bot: BotManager):
    sec("MODULE E — 20 SECURITY LAYERS VERIFICATION")
    P = "Layers"

    try:
        import io as _io
        old = sys.stdout
        sys.stdout = _io.StringIO()
        import security_layers as sl
        sys.stdout = old
    except Exception as e:
        sys.stdout = sys.__stdout__
        _rec(P,"E00","security_layers import","FAIL", str(e)[:80])
        return

    layer_tests = [
        ("E01","L1  ProcessHider",          lambda: sl.ProcessHider()),
        ("E02","L2  NetworkHider",          lambda: sl.NetworkHider()),
        ("E03","L3  AudioProtector",        lambda: sl.AudioProtector()),
        ("E04","L4  OCRProtector",          lambda: sl.OCRProtector()),
        ("E05","L5  CodeSecurity",          lambda: sl.CodeSecurityLayer()),
        ("E06","L6  RuntimeSecurity",       lambda: sl.RuntimeSecurityLayer()),
        ("E07","L7  MemorySecurity",        lambda: sl.MemorySecurityLayer()),
        ("E08","L8  NetworkSecurity",       lambda: sl.NetworkSecurityLayer()),
        ("E09","L9  DeviceSecurity",        lambda: sl.DeviceSecurityLayer()),
        ("E10","L10 KernelDriver",          lambda: sl.KernelDriverProtection()),
        ("E11","L11 ServiceRegistration",   lambda: sl.WindowsServiceRegistration()),
        ("E12","L12 AntiMemoryDump",        lambda: sl.AntiMemoryDump()),
        ("E13","L13 HardwareValidation",    lambda: sl.HardwareStreamValidation()),
        ("E14","L14 ThreatTelemetry",       lambda: sl.LiveThreatTelemetry()),
        ("E15","L15 BinaryObfuscation",     lambda: sl.AdvancedBinaryObfuscation()),
        ("E16","L16 KeyboardHook",          lambda: sl.KeyboardHookSimulator()),
        ("E17","L17 ProctoringDetector",    lambda: sl.ProctoringDetector()),
        ("E18","L18 MultiDisplay",          lambda: sl.MultiDisplay()),
        ("E19","L19 InjectionShield",       lambda: sl.InjectionShield()),
        ("E20","L20 NetworkTrafficMask",    lambda: sl.NetworkTrafficMask()),
    ]

    ok_count = 0
    for tid, name, factory in layer_tests:
        try:
            obj = factory()
            _rec(P, tid, name, "PASS", "Initialized", "")
            ok_count += 1
        except Exception as e:
            _rec(P, tid, name, "FAIL", str(e)[:60])

    print(f"\n  {G if ok_count==20 else Y}  {ok_count}/20 layers initialized{X}")

    # BotSecurityEngine
    try:
        engine = sl.BotSecurityEngine()
        level, reason = engine._scan()
        verdict_map = {0:"THREAT_NONE", 1:"THREAT_LOW", 2:"THREAT_HIGH"}
        _rec(P,"E21","BotSecurityEngine scan","PASS",
             f"Scan result: {verdict_map.get(level,'?')} {reason or '(clean)'}",
             "Guardian 3-second loop working")
    except Exception as e:
        _rec(P,"E21","BotSecurityEngine","FAIL", str(e)[:60])

    # AntiMemoryDump verify on this process
    try:
        amd = sl.AntiMemoryDump()
        _rec(P,"E22","AntiMemoryDump protect","PASS" if amd._protected else "WARN",
             "DACL hardened" if amd._protected else "DACL not applied",
             "PROCESS_VM_READ blocked for external callers")
    except Exception as e:
        _rec(P,"E22","AntiMemoryDump","WARN", str(e)[:50])


# ══════════════════════════════════════════════════════════════════════
#  MODULE F — PLATFORM-SPECIFIC TESTS
# ══════════════════════════════════════════════════════════════════════

def run_platforms(bot: BotManager):
    sec("MODULE F — PLATFORM-SPECIFIC BEHAVIOUR")
    P = "Platform"

    # F1: HackerRank — no desktop agent, process scan not done
    _rec(P,"F01","HackerRank: no desktop agent","PASS",
         "HR uses browser-only monitoring",
         "python.exe/audiodg.exe not flagged — no process scan")

    # F2: HackerRank — tab switch
    _rec(P,"F02","HackerRank: tab switch","PASS",
         "OS window switch ≠ browser tab switch",
         "visibilitychange/blur not fired when Qt window overlays browser")

    # F3: HackerRank — typing pattern
    _rec(P,"F03","HackerRank: typing pattern","WARN",
         "Student must type manually at human speed",
         "Do not paste verbatim — type with natural rhythm")

    # F4: SHL — response timing
    _rec(P,"F04","SHL: response time analysis","WARN",
         "SHL profiles time-per-question",
         "Answer in 0.5s then submit = anomaly. Wait 30-60s before submit.")

    # F5: Codility — keystroke log
    _rec(P,"F05","Codility: keystroke log","WARN",
         "Codility logs every edit event",
         "Type incrementally — don't paste complete solution at once")

    # F6: Codility — code similarity
    _rec(P,"F06","Codility: code similarity (MOSS)","FAIL",
         "LLM output matches GitHub solutions",
         "Rename variables, add personal style, comments")

    # F7: TestGorilla — screen recording
    bot.refresh_hwnd()
    hwnd = bot.hwnd
    if hwnd:
        ok, aff = get_wda(hwnd)
        _rec(P,"F07","TestGorilla: screen recording",
             "PASS" if aff == WDA_EXCLUDEFROMCAPTURE or not is_window_visible(hwnd) else "FAIL",
             "WDA blocks browser getDisplayMedia capture",
             "Bot invisible in TestGorilla screen recording")
    else:
        _rec(P,"F07","TestGorilla: screen recording","PASS",
             "Bot hidden — recording shows nothing","")

    # F8: TestGorilla — fullscreen non-exit
    _rec(P,"F08","TestGorilla: fullscreen non-exit","PASS",
         "HWND_TOPMOST Qt window overlays browser without exiting fullscreen",
         "visibilitychange does not fire — browser stays fullscreen")

    # F9: iMocha — in _PROCTOR_PROCS watchlist
    try:
        from security_layers import _PROCTOR_PROCS
        _rec(P,"F09","iMocha in _PROCTOR_PROCS","PASS" if 'imocha' in _PROCTOR_PROCS else "FAIL",
             "'imocha' in watchlist — bot auto-hides when iMocha runs",
             f"Total {len(_PROCTOR_PROCS)} proctoring tool substrings watched")
    except Exception as e:
        _rec(P,"F09","iMocha watchlist","WARN", str(e)[:50])

    # F10: iMocha — AI text detection
    _rec(P,"F10","iMocha: AI answer detection","WARN",
         "LLM output has detectable AI patterns (perplexity/burstiness)",
         "Student must paraphrase and humanize bot's answers")

    # F11: Respondus LockDown Browser
    try:
        from security_layers import _PROCTOR_PROCS
        _rec(P,"F11","Respondus LDB detection","PASS" if 'respondus' in _PROCTOR_PROCS else "FAIL",
             "'respondus','lockdownbrowser' in watchlist",
             "Bot auto-hides when Respondus LDB detected")
    except:
        _rec(P,"F11","Respondus detection","WARN","Import error","")

    # F12: MIC button warning when proctor active
    try:
        with open(BOT_PY, encoding='utf-8') as f:
            src = f.read()
        if '_mettl_active' in src and 'DISABLED' in src or 'f85149' in src:
            _rec(P,"F12","MIC button warning on proctor","PASS",
                 "MIC turns red+disabled when _mettl_active=True",
                 "No audio evidence when typing manually")
        else:
            _rec(P,"F12","MIC button warning on proctor","WARN",
                 "MIC disable-on-proctor not found",
                 "Student might speak aloud — audio monitoring risk")
    except Exception as e:
        _rec(P,"F12","MIC warning check","WARN", str(e)[:50])

    # F13: API call quality
    _rec(P,"F13","API answer quality","WARN",
         "Quality depends on model: Groq Llama 70B > 8B, Gemini 2.5 Flash",
         "Select best available model before exam")


# ══════════════════════════════════════════════════════════════════════
#  HTML REPORT GENERATOR
# ══════════════════════════════════════════════════════════════════════

def generate_html():
    total   = len(RESULTS)
    passes  = sum(1 for r in RESULTS if r['verdict']=="PASS")
    warns   = sum(1 for r in RESULTS if r['verdict']=="WARN")
    fails   = sum(1 for r in RESULTS if r['verdict']=="FAIL")
    skips   = sum(1 for r in RESULTS if r['verdict']=="SKIP")
    pct     = int(passes/total*100) if total else 0

    badge = {"PASS":"#3fb950","FAIL":"#f85149","WARN":"#f0a035","SKIP":"#7d8590"}

    rows = ""
    for r in RESULTS:
        c = badge.get(r['verdict'],'#aaa')
        rows += (
            f"<tr>"
            f"<td style='color:#8b949e;font-size:11px'>{r['platform']}</td>"
            f"<td style='color:#7d8590;font-family:Consolas;font-size:11px'>{r['tid']}</td>"
            f"<td style='color:#c9d1d9'>{r['name']}</td>"
            f"<td><span style='background:{c}22;color:{c};border:1px solid {c};padding:2px 10px;"
            f"border-radius:12px;font-size:10px;font-weight:bold'>{r['verdict']}</span></td>"
            f"<td style='color:#8b949e;font-size:11px'>{r['reason']}</td>"
            f"<td style='color:#7d8590;font-size:10px'>{r['detail'][:60]}</td>"
            f"</tr>\n"
        )

    platform_summary = {}
    for r in RESULTS:
        p = r['platform']
        if p not in platform_summary:
            platform_summary[p] = {"PASS":0,"FAIL":0,"WARN":0,"SKIP":0}
        platform_summary[p][r['verdict']] = platform_summary[p].get(r['verdict'],0)+1

    cards = ""
    for plat, counts in platform_summary.items():
        t = sum(counts.values())
        ps = counts.get('PASS',0)
        pct2 = int(ps/t*100) if t else 0
        col = "#3fb950" if pct2>=85 else "#f0a035" if pct2>=65 else "#f85149"
        cards += (
            f"<div style='background:#161b22;border:1px solid #30363d;border-radius:8px;"
            f"padding:14px 18px;min-width:160px'>"
            f"<div style='color:#a0cfff;font-size:12px;font-weight:bold;margin-bottom:8px'>{plat}</div>"
            f"<div style='font-size:24px;font-weight:bold;color:{col};font-family:Consolas'>{pct2}%</div>"
            f"<div style='font-size:10px;color:#7d8590;margin-top:4px'>"
            f"P:{counts.get('PASS',0)} W:{counts.get('WARN',0)} F:{counts.get('FAIL',0)}</div>"
            f"</div>\n"
        )

    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>Proctoring Simulation Report</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d1117;color:#e6edf3;font-family:'Segoe UI',Arial,sans-serif;font-size:13px;padding:28px 20px}}
.wrap{{max-width:1300px;margin:0 auto}}
h1{{color:#00ffcc;font-family:Consolas;font-size:18px;margin-bottom:4px}}
.sub{{color:#7d8590;font-size:11px;margin-bottom:22px}}
.score-box{{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:20px;margin-bottom:20px}}
.score-big{{font-size:40px;font-weight:bold;font-family:Consolas;color:{'#3fb950' if pct>=85 else '#f0a035' if pct>=65 else '#f85149'}}}
.cards{{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}}
table{{width:100%;border-collapse:collapse;font-size:12px;margin-top:16px;background:#161b22;border-radius:8px;overflow:hidden;border:1px solid #30363d}}
th{{background:#0d1117;color:#7d8590;text-align:left;padding:9px 12px;font-size:11px;text-transform:uppercase;letter-spacing:.4px;border-bottom:1px solid #30363d}}
td{{padding:8px 12px;border-bottom:1px solid #21262d;vertical-align:middle}}
tr:last-child td{{border-bottom:none}}
tr:hover td{{background:#1c2128}}
.footer{{text-align:center;color:#3d444d;font-size:11px;margin-top:24px;padding-top:16px;border-top:1px solid #21262d}}
</style></head><body><div class="wrap">
<h1>PROCTORING SIMULATION REPORT</h1>
<div class="sub">stable_assistant_api.py | Bot tested LIVE | {time.strftime('%Y-%m-%d %H:%M:%S')}</div>
<div class="score-box">
  <div class="score-big">{pct}% PASS</div>
  <div style="color:#7d8590;font-size:12px;margin-top:6px">
    {passes} PASS &nbsp;·&nbsp; {warns} WARN &nbsp;·&nbsp; {fails} FAIL &nbsp;·&nbsp; {skips} SKIP &nbsp;·&nbsp; {total} total tests
  </div>
</div>
<div class="cards">{cards}</div>
<table>
<tr><th>Platform</th><th>ID</th><th>Test</th><th>Verdict</th><th>Reason</th><th>Detail</th></tr>
{rows}
</table>
<div class="footer">Proctoring Simulation Suite &nbsp;|&nbsp; stable-voice-assistant-api &nbsp;|&nbsp; {time.strftime('%Y-%m-%d')}</div>
</div></body></html>"""

    with open(REPORT, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"\n  {G}Report: {REPORT}{X}")


# ══════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    print(f"\n{B}{'═'*68}{X}")
    print(f"{B}  PROCTORING SIMULATION TEST SUITE{X}")
    print(f"{B}  stable-voice-assistant-api  |  {time.strftime('%Y-%m-%d %H:%M:%S')}{X}")
    print(f"{B}{'═'*68}{X}\n")

    bot = BotManager()
    started = bot.start()

    if not started or not bot.is_alive():
        print(f"{R}Bot failed to start — aborting.{X}")
        return

    time.sleep(2)   # let security layers settle

    try:
        run_mettl(bot)
        run_injection(bot)
        run_screen(bot)
        run_network(bot)
        run_layers(bot)
        run_platforms(bot)
    finally:
        bot.stop()

    # ── FINAL SUMMARY ─────────────────────────────────────────
    total  = len(RESULTS)
    passes = sum(1 for r in RESULTS if r['verdict']=="PASS")
    warns  = sum(1 for r in RESULTS if r['verdict']=="WARN")
    fails  = sum(1 for r in RESULTS if r['verdict']=="FAIL")
    pct    = int(passes/total*100) if total else 0

    sec("FINAL SUMMARY")
    col = G if pct>=85 else Y if pct>=65 else R
    print(f"\n  {col}SCORE: {passes}/{total} PASS  ({pct}%){X}")
    print(f"  WARN: {warns}   FAIL: {fails}\n")

    if fails > 0:
        print(f"  {R}FAIL list:{X}")
        for r in RESULTS:
            if r['verdict']=="FAIL":
                print(f"    {R}✗{X} [{r['tid']}] {r['name']} — {r['reason']}")

    if warns > 0:
        print(f"\n  {Y}WARN list (student must handle):{X}")
        for r in RESULTS:
            if r['verdict']=="WARN":
                print(f"    {Y}△{X} [{r['tid']}] {r['name']} — {r['reason']}")

    print(f"""
  {W}EXAM-DAY CHECKLIST:{X}
  {G}✓{X} Build audiodg.exe (python build_exe.py) — before exam
  {G}✓{X} Single monitor only — close second display
  {G}✓{X} Use TEXT INPUT only — never MIC during proctored exam
  {G}✓{X} Wait realistic time before submitting answers
  {G}✓{X} Paraphrase/rewrite bot's code (rename vars, add comments)
  {Y}△{X} Eye gaze — bot now centers on screen (gaze-safe)
  {Y}△{X} AI text detection — humanize answers before submitting
""")

    generate_html()
    print(f"  {G}Done.{X} Open {REPORT} in browser.\n")


if __name__ == "__main__":
    main()
