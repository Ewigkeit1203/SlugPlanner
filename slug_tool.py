import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from agent import run_tool

if __name__ == '__main__':
    user_input = sys.argv[1] if len(sys.argv) > 1 else "15 units, easy professors"
    print(run_tool(user_input))