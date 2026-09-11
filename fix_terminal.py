content = open(r'C:/Users/Ashish/Desktop/AI Working/AI Environment/AI Management/Developed Softwares/AI-Agent-Studio/app/ui/app_window.py', 'r', encoding='utf-8').read()

old = '''                    box.configure(state="normal")
                    box.insert("end", line + "\\n")
                    box.see("end")
                    box.configure(state="disabled")'''

new = '''                    box.configure(state="normal")
                    # Apply color tags based on line content
                    tag = "info"
                    lower = line.lower()
                    if lower.startswith("$ ") or "command:" in lower:
                        tag = "cmd"
                    elif "stdout" in lower:
                        tag = "stdout"
                    elif "stderr" in lower:
                        tag = "stderr"
                    elif "exit code" in lower:
                        tag = "exit"
                    elif "cwd:" in lower:
                        tag = "cwd"
                    box.insert("end", line + "\\n", tag)
                    box.see("end")
                    box.configure(state="disabled")'''

if old in content:
    content = content.replace(old, new)
    open(r'C:/Users/Ashish/Desktop/AI Working/AI Environment/AI Management/Developed Softwares/AI-Agent-Studio/app/ui/app_window.py', 'w', encoding='utf-8').write(content)
    print('Done')
else:
    print('NOT FOUND')
    idx = content.find('box.insert("end", line')
    if idx > 0:
        print(repr(content[idx-200:idx+200]))