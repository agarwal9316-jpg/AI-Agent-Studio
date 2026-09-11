content = open(r'C:/Users/Ashish/Desktop/AI Working/AI Environment/AI Management/Developed Softwares/AI-Agent-Studio/app/ui/app_window.py', 'r', encoding='utf-8').read()

old = '''                graph = self._sysmon_graphs.get(key)
                if graph and graph.winfo_exists():
                    self._draw_mini_graph(graph, history, key)
                    
        except Exception:
            pass
        
        # Schedule next update (every 2 seconds)'''

new = '''                graph = self._sysmon_graphs.get(key)
                if graph and graph.winfo_exists():
                    self._draw_mini_graph(graph, history, key)

            # Update speed labels
            # Network download/upload
            if hasattr(self, "_sysmon_net_down_label") and self._sysmon_net_down_label.winfo_exists():
                self._sysmon_net_down_label.configure(text=f"\u2193 {net_down_mbps:.1f} Mbps")
            if hasattr(self, "_sysmon_net_up_label") and self._sysmon_net_up_label.winfo_exists():
                self._sysmon_net_up_label.configure(text=f"\u2191 {net_up_mbps:.1f} Mbps")

            # Disk read/write
            if hasattr(self, "_sysmon_disk_read_label") and self._sysmon_disk_read_label.winfo_exists():
                self._sysmon_disk_read_label.configure(text=f"R {disk_read_mbps:.1f} MB/s")
            if hasattr(self, "_sysmon_disk_write_label") and self._sysmon_disk_write_label.winfo_exists():
                self._sysmon_disk_write_label.configure(text=f"W {disk_write_mbps:.1f} MB/s")
                    
        except Exception:
            pass
        
        # Schedule next update (every 2 seconds)'''

if old in content:
    content = content.replace(old, new)
    open(r'C:/Users/Ashish/Desktop/AI Working/AI Environment/AI Management/Developed Softwares/AI-Agent-Studio/app/ui/app_window.py', 'w', encoding='utf-8').write(content)
    print('Done - Part 2')
else:
    print('NOT FOUND - Part 2')
    idx = content.find('graph = self._sysmon_graphs.get(key)')
    if idx > 0:
        print(repr(content[idx:idx+300]))