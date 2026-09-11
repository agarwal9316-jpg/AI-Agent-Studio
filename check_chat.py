import json
chat = json.load(open(r'C:/Users/Ashish/Desktop/AI Working/AI Environment/AI Management/Developed Softwares/AI-Agent-Studio/data/chats/b7c72d69-1451-4b86-b10a-eb28b972c490.json', 'r', encoding='utf-8'))
print("Chat ID:", chat.get('id'))
print("Title:", chat.get('title'))
print("Messages:", len(chat.get('messages', [])))
for msg in chat.get('messages', [])[-10:]:
    role = msg.get('role', '')
    content = str(msg.get('content', ''))[:300]
    print(f"  {role}: {content}")
    if msg.get('images'):
        print(f"    Images: {msg.get('images')}")