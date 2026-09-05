import sys
from pathlib import Path

# Add project root directory to sys.path so 'bot' and 'web' can be imported seamlessly
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from web.app import app

# Export app for Vercel Serverless
app = app
