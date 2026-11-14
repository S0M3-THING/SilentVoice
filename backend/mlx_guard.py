"""One lock for everything that runs on the Mac's GPU through MLX.

The own-voice model and the word-check model both use MLX (Apple's Metal GPU library),
which isn't safe to use from two threads at once. Without this, loading one while the
other runs could crash the server.
"""

import threading

MLX_LOCK = threading.RLock()
