import re

content = open(r'C:/Users/Ashish/Desktop/AI Working/AI Environment/AI Management/Developed Softwares/AI-Agent-Studio/app/ui/app_window.py', 'r', encoding='utf-8').read()

# Check for Terminal in _build_panel_toolbar
idx = content.find('elif mode == "Terminal"')
if idx >= 0:
    print("Found Terminal in _build_panel_toolbar:")
    print(content[idx:idx+500])
else:
    print("Terminal NOT found in _build_panel_toolbar")

# Check for panel_toolbar creation
idx2 = content.find('self.panel_toolbar = ctk.CTkFrame')
if idx2 >= 0:
    print("\nFound panel_toolbar creation:")
    print(content[idx2:idx2+200])
else:
    print("panel_toolbar creation NOT found")

# Check for _bind_terminal_log call
idx3 = content.find('self._bind_terminal_log()')
if idx3 >= 0:
    print("\nFound _bind_terminal_log() call:")
    print(content[idx3-100:idx3+100])
else:
    print("_bind_terminal_log() call NOT found")

# Check terminal_box creation
idx4 = content.find('self.terminal_box = ctk.CTkTextbox')
if idx4 >= 0:
    print("\nFound terminal_box creation:")
    print(content[idx4:idx4+200])
else:
    print("terminal_box creation NOT found")