import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Provide a dummy RESEND_API_KEY for tests that mock httpx but still need
# the key-present guard in send_feedback to pass.
os.environ.setdefault("RESEND_API_KEY", "test-key")
