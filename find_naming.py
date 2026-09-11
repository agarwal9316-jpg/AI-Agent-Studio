import os
base = r'C:\Users\Ashish\Desktop\AI Working\AI Environment\AI Management\Developed Softwares\AI-Agent-Studio\app\ui'
results = []
for root, dirs, files in os.walk(base):
    for f in files:
        if 'naming' in f.lower():
            results.append(os.path.join(root, f))
print(results)