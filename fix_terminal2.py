content = open(r'C:/Users/Ashish/Desktop/AI Working/AI Environment/AI Management/Developed Softwares/AI-Agent-Studio/app/ui/app_window.py', 'r', encoding='utf-8').read()

old = '''def _refresh_terminal_panel(self) -> None:
        """Refresh terminal panel from stored lines."""
        if not hasattr(self, "terminal_box") or not self.terminal_box.winfo_exists():
            return
        lines = getattr(self, "_terminal_log_lines", [])
        try:
            self.terminal_box.configure(state="normal")
            self.terminal_box.delete("1.0", "end")
            if lines:
                self.terminal_box.insert("1.0", "\\n".join(lines) + "\\n")
            else:
                self.terminal_box.insert("1.0", "No terminal activity yet…\\nRun terminal commands to see output here.")
            self.terminal_box.configure(state="disabled")
            self.terminal_box.see("end")
        except Exception:
            pass'''

new = '''def _refresh_terminal_panel(self) -> None:
        """Refresh terminal panel from stored lines."""
        if not hasattr(self, "terminal_box") or not self.terminal_box.winfo_exists():
            return
        lines = getattr(self, "_terminal_log_lines", [])
        try:
            self.terminal_box.configure(state="normal")
            self.terminal_box.delete("1.0", "end")
            if lines:
                for line in lines:
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
                    self.terminal_box.insert("end", line + "\\n", tag)
            else:
                self.terminal_box.insert("1.0", "No terminal activity yet…\\nRun terminal commands to see output here.")
            self.terminal_box.configure(state="disabled")
            self.terminal_box.see("end")
        except Exception:
            pass'''

if old in content:
    content = content.replace(old, new)
    open(r'C:/Users/Ashish/Desktop/AI Working/AI Environment/AI Management/Developed Softwares/AI-Agent-Studio/app/ui/app_window.py', 'w', encoding='utf-8').write(content)
    print('Done')
else:
    print('NOT FOUND')
    idx = content.find('def _refresh_terminal_panel')
    if idx > 0:
        print(repr(content[idx:idx+800]))