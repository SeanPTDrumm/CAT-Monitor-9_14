"""Run locally with a timestamped log; inherit console for Ctrl+C."""
from pathlib import Path
import datetime
import subprocess
import sys
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "app"))
from local_paths import ensure_directories, LOG_DIR
ensure_directories()
stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
log = LOG_DIR / ("streamlit-" + stamp + ".log")
print("CAT Monitor: http://localhost:8501")
print("Keep this window open. Press Ctrl+C to stop.")
print("Log:", log, flush=True)
with log.open("w", encoding="utf-8") as output:
    process = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(root / "app/app.py"),
        "--server.address=127.0.0.1", "--server.port=8501", "--server.headless=false",
        "--browser.serverAddress=localhost", "--browser.gatherUsageStats=false"], cwd=root, stdout=output, stderr=subprocess.STDOUT)
    try:
        code = process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
        code = 0
if code:
    print(log.read_text(encoding="utf-8"))
sys.exit(code)
