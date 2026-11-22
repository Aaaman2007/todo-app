import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Set these before `app` is imported: importing it builds the module-level
# application, which must not touch the developer's real database or log a
# missing-SECRET_KEY warning during tests.
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault(
    "DATABASE", os.path.join(tempfile.mkdtemp(prefix="todo-tests-"), "import.db")
)
