# Add the parent directory (project root) to sys.path for development/testing purpose
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Start of the test script
from jawm import Process
import logging
import time

# Configure logging
logging.basicConfig(level=logging.INFO)

