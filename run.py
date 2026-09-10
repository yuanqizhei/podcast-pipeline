import sys

# keep console logs readable on Windows (GBK codepage) CJK shells
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from webapp import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, threaded=True)
