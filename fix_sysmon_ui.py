content = open(r'C:/Users/Ashish/Desktop/AI Working/AI Environment/AI Management/Developed Softwares/AI-Agent-Studio/app/ui/app_window.py', 'r', encoding='utf-8').read()

old = '''            pct_label.pack(side="right", padx=(4, 0))
            self._sysmon_labels[key] = pct_label
            
            graph_frame = ctk.CTkFrame(
                mframe,
                height=18,
                fg_color=_UI["top_bg"],
                corner_radius=3,
                border_width=0,
            )
            graph_frame.pack(fill="x", pady=(2, 0))
            graph_frame.pack_propagate(False)
            self._sysmon_graphs[key] = graph_frame'''

new = '''            pct_label.pack(side="right", padx=(4, 0))
            self._sysmon_labels[key] = pct_label

            # Speed label row for NET and DISK
            if key in ("net", "disk"):
                speed_row = ctk.CTkFrame(mframe, fg_color="transparent")
                speed_row.pack(fill="x", pady=(2, 0))
                if key == "net":
                    # Download / Upload labels
                    self._sysmon_net_down_label = ctk.CTkLabel(
                        speed_row,
                        text="\u2193 0.0 Mbps",
                        font=ctk.CTkFont(size=9),
                        text_color=("#10b981", "#34d399"),
                    )
                    self._sysmon_net_down_label.pack(side="left", padx=(2, 8))
                    self._sysmon_net_up_label = ctk.CTkLabel(
                        speed_row,
                        text="\u2191 0.0 Mbps",
                        font=ctk.CTkFont(size=9),
                        text_color=("#ef4444", "#f87171"),
                    )
                    self._sysmon_net_up_label.pack(side="left")
                elif key == "disk":
                    # Read / Write labels
                    self._sysmon_disk_read_label = ctk.CTkLabel(
                        speed_row,
                        text="R 0.0 MB/s",
                        font=ctk.CTkFont(size=9),
                        text_color=("#3b82f6", "#60a5fa"),
                    )
                    self._sysmon_disk_read_label.pack(side="left", padx=(2, 8))
                    self._sysmon_disk_write_label = ctk.CTkLabel(
                        speed_row,
                        text="W 0.0 MB/s",
                        font=ctk.CTkFont(size=9),
                        text_color=("#f59e0b", "#fbbf24"),
                    )
                    self._sysmon_disk_write_label.pack(side="left")

            graph_frame = ctk.CTkFrame(
                mframe,
                height=18,
                fg_color=_UI["top_bg"],
                corner_radius=3,
                border_width=0,
            )
            graph_frame.pack(fill="x", pady=(2, 0))
            graph_frame.pack_propagate(False)
            self._sysmon_graphs[key] = graph_frame'''

if old in content:
    content = content.replace(old, new)
    open(r'C:/Users/Ashish/Desktop/AI Working/AI Environment/AI Management/Developed Softwares/AI-Agent-Studio/app/ui/app_window.py', 'w', encoding='utf-8').write(content)
    print('Done - UI updated')
else:
    print('NOT FOUND - UI')
    idx = content.find('self._sysmon_labels[key] = pct_label')
    if idx > 0:
        print(repr(content[idx:idx+300]))