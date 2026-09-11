import json
data = json.load(open(r'C:/Users/Ashish/Desktop/AI Working/AI Environment/AI Management/Developed Softwares/AI-Agent-Studio/data/agent_runs.json', 'r', encoding='utf-8'))
print(json.dumps(data[-5:], indent=2))