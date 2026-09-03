import gc
import logging

logger = logging.getLogger(__name__)


def reclaim_ram(context_label: str = "") -> None:
    """
    Aggressively reclaims heap and OS resident memory (RSS):
    1. Python generational garbage collection (gc.collect()).
    2. Linux glibc malloc arena compaction via malloc_trim(0).
    
    Forces the Linux C runtime to return freed memory arenas back to the kernel,
    preventing cgroup/container OOM kills (SIGKILL / signal 9) during bulk operations
    (e.g., downloading hundreds of PDFs, OCR rendering, and multimodal analysis).
    """
    try:
        collected = gc.collect()
        import ctypes
        import ctypes.util
        libc_name = ctypes.util.find_library('c') or 'libc.so.6'
        libc = ctypes.CDLL(libc_name)
        if hasattr(libc, 'malloc_trim'):
            trimmed = libc.malloc_trim(0)
            if context_label:
                logger.debug(f"🧹 [RAM RECLAIM] Executed malloc_trim(0) for '{context_label}' (gc={collected}, trim={trimmed}).")
    except Exception as e:
        logger.debug(f"RAM trim note: {e}")
