import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["FTL_DATA_DIR"] = tempfile.mkdtemp(prefix="ftl-tests-")
