import subprocess
import sys

result = subprocess.run(
    [sys.executable, "C:/Users/Ashish/Desktop/AI Working/AI Environment/AI Management/Developed Softwares/AI-Agent-Studio/entry.py"],
    capture_output=True,
    text=True,
    timeout=15
)
print("STDOUT:")
print(result.stdout)
print("STDERR:")
print(result.stderr)
print("Return code:", result.returncode)