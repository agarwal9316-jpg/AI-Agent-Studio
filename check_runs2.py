import json
data = json.load(open(r'C:/Users/Ashish/Desktop/AI Working/AI Environment/AI Management/Developed Softwares/AI-Agent-Studio/data/agent_runs.json', 'r', encoding='utf-8'))
print("Type:", type(data))
if isinstance(data, list):
    print("Length:", len(data))
    print(json.dumps(data[-5:], indent=2))
else:
    print("Keys:", data.keys())
    for k, v in list(data.items())[-5:]:
        print(f"Key: {k}")
        print(json.dumps(v, indent=2)[:500])