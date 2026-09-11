content = open(r'C:/Users/Ashish/Desktop/AI Working/AI Environment/AI Management/Developed Softwares/AI-Agent-Studio/app/ui/app_window.py', 'r', encoding='utf-8').read()

old = '''            # Network I/O (bytes per second)
            net_pct = 0.0
            try:
                net_io = psutil.net_io_counters()
                current_bytes = net_io.bytes_sent + net_io.bytes_recv
                if hasattr(self, "_sysmon_last_net_bytes"):
                    delta = current_bytes - self._sysmon_last_net_bytes
                    # Normalize to 0-100 scale (assuming ~10MB/s as 100%)
                    net_pct = min(100, (delta / 1024 / 1024) * 10)
                self._sysmon_last_net_bytes = current_bytes
            except Exception:
                pass'''

new = '''            # Disk usage and I/O
            disk_pct = 0.0
            disk_read_mbps = 0.0
            disk_write_mbps = 0.0
            try:
                if platform.system() == "Windows":
                    disk = psutil.disk_usage("C:\\\\")
                else:
                    disk = psutil.disk_usage("/")
                disk_pct = disk.percent

                # Disk I/O
                disk_io = psutil.disk_io_counters()
                if disk_io:
                    current_read = disk_io.read_bytes
                    current_write = disk_io.write_bytes
                    if hasattr(self, "_sysmon_last_disk_read") and hasattr(self, "_sysmon_last_disk_write"):
                        read_delta = current_read - self._sysmon_last_disk_read
                        write_delta = current_write - self._sysmon_last_disk_write
                        # Convert to MB/s (2 second interval)
                        disk_read_mbps = read_delta / 1024 / 1024 / 2
                        disk_write_mbps = write_delta / 1024 / 1024 / 2
                    self._sysmon_last_disk_read = current_read
                    self._sysmon_last_disk_write = current_write
            except Exception:
                pass

            # Network I/O (bytes per second)
            net_pct = 0.0
            net_down_mbps = 0.0
            net_up_mbps = 0.0
            try:
                net_io = psutil.net_io_counters()
                current_recv = net_io.bytes_recv
                current_sent = net_io.bytes_sent
                if hasattr(self, "_sysmon_last_net_recv") and hasattr(self, "_sysmon_last_net_sent"):
                    recv_delta = current_recv - self._sysmon_last_net_recv
                    sent_delta = current_sent - self._sysmon_last_net_sent
                    # Convert to Mbps (2 second interval, bits not bytes)
                    net_down_mbps = (recv_delta * 8) / 1024 / 1024 / 2
                    net_up_mbps = (sent_delta * 8) / 1024 / 1024 / 2
                    # Normalize to 0-100 scale (assuming ~100Mbps as 100%)
                    total_mbps = net_down_mbps + net_up_mbps
                    net_pct = min(100, total_mbps)
                self._sysmon_last_net_recv = current_recv
                self._sysmon_last_net_sent = current_sent
            except Exception:
                pass'''

if old in content:
    content = content.replace(old, new)
    open(r'C:/Users/Ashish/Desktop/AI Working/AI Environment/AI Management/Developed Softwares/AI-Agent-Studio/app/ui/app_window.py', 'w', encoding='utf-8').write(content)
    print('Done - Part 1')
else:
    print('NOT FOUND - Part 1')
    idx = content.find('Network I/O (bytes per second)')
    if idx > 0:
        print(repr(content[idx:idx+200]))