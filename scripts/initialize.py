from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from local_paths import ensure_directories, DIRECTORIES
ensure_directories()
for folder in DIRECTORIES:
    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile(dir=folder, prefix=".write-check-", delete=True) as handle:
        handle.write(b"CAT Monitor write check")
        handle.flush()
    print("Writable:", folder)
