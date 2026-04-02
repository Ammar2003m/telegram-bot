"""
نقطة دخول البوت — متوافق مع VPS و systemd
تشغيل: python main.py
"""
import os
import sys
import time
import signal
import logging

# ── إعداد السجل ─────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ── تأمين عدم تشغيل نسختين معاً ────────────────────
LOCK_FILE = "/tmp/storerozbot.lock"


def _kill_old_instance():
    try:
        with open(LOCK_FILE) as f:
            old_pid = int(f.read().strip())
        if old_pid == os.getpid():
            return
        try:
            os.kill(old_pid, signal.SIGTERM)
            time.sleep(2)
            try:
                os.kill(old_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        except ProcessLookupError:
            pass
        log.info(f"أوقفت النسخة القديمة PID={old_pid}")
    except Exception:
        pass


def acquire_lock():
    _kill_old_instance()
    try:
        import fcntl
        lock_fh = open(LOCK_FILE, "w")
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fh.write(str(os.getpid()))
        lock_fh.flush()
        return lock_fh
    except IOError:
        log.error("لا يمكن الحصول على القفل — هل يعمل البوت مسبقاً؟")
        sys.exit(1)
    except ImportError:
        # fcntl غير متاح على Windows
        return None


def release_lock(lock_fh):
    if lock_fh is None:
        return
    try:
        import fcntl
        fcntl.flock(lock_fh, fcntl.LOCK_UN)
        lock_fh.close()
        os.unlink(LOCK_FILE)
    except Exception:
        pass


# ── التحقق من وجود قاعدة البيانات ──────────────────
def ensure_data_dir():
    from config import DB
    if not os.path.exists(DB):
        log.error(
            f"❌ قاعدة البيانات غير موجودة: {DB}\n"
            f"   انسخ store.db إلى مجلد البوت ثم أعد التشغيل"
        )
        sys.exit(1)


# ── keep_alive اختياري (Replit فقط) ─────────────────
def start_keep_alive():
    """يُشغَّل فقط إذا كنا في بيئة Replit أو تم تفعيله يدوياً."""
    if not os.getenv("REPL_ID") and not os.getenv("ENABLE_KEEPALIVE"):
        return  # VPS — لا حاجة له
    try:
        from keep_alive import keep_alive
        keep_alive()
        log.info("✅ keep_alive يعمل")
    except Exception as e:
        log.warning(f"keep_alive: {e}")


from bot import main


if __name__ == "__main__":
    lock = acquire_lock()
    try:
        ensure_data_dir()
        start_keep_alive()
        main()
    except KeyboardInterrupt:
        log.info("تم إيقاف البوت يدوياً (Ctrl+C)")
    except Exception as e:
        log.exception(f"خطأ فادح: {e}")
        sys.exit(1)
    finally:
        release_lock(lock)
