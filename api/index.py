import sys
import os

# Add parent directory to path so app.py and its local imports resolve
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
