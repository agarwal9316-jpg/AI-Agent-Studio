import json
data = json.load(open(r'C:/Users/Ashish/Desktop/AI Working/AI Environment/AI Management/Developed Softwares/AI-Agent-Studio/data/agent_runs.json', 'r', encoding='utf-8'))
runs = data.get('runs', [])
print("Total runs:", len(runs))
for run in runs[-10:]:
    print(f"\n--- Run ---")
    print(f"ID: {run.get('id')}")
    print(f"Status: {run.get('status')}")
    print(f"Agent: {run.get('agent_name')}")
    print(f"Model: {run.get('model')}")
    print(f"Input: {str(run.get('input'))[:200]}")
    print(f"Output: {str(run.get('output'))[:300]}")
    if run.get('error'):
        print(f"Error: {run.get('error')}")
    if run.get('steps'):
        print(f"Steps: {len(run.get('steps'))}")
        for step in run.get('steps')[-3:]:
            print(f"  Step: {step.get('tool')} - {step.get('status')} - {str(step.get('result'))[:100]}")