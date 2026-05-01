"""
Moteur de suivi réseau pour Network Monitor Pro.
"""

import ipaddress
import os
import socket
import subprocess
import sys
import threading
import time
from collections import deque

import psutil
from PyQt6.QtCore import QThread

from network_monitor.config import (
    CONNECTION_POLL_INTERVAL,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    DEVICE_TTL,
    HISTORY_CLEANUP_THRESHOLD,
    HISTORY_SNAPSHOT_INTERVAL,
    MAX_GRAPH_SAMPLES,
    SCAN_POLL_INTERVAL,
)
from network_monitor.database import HistoryDatabase
from network_monitor.alerts import AlertManager
from network_monitor.utils import format_endpoint, is_suspicious_ip, is_suspicious_port


class NetworkTracker:
    """Moteur principal de suivi et d'analyse réseau."""
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=DEFAULT_TIMEOUT):
        self.host = host
        self.port = port
        self.timeout = timeout

        self.interface_ip = self._determine_interface_ip()
        self.interface_name = self._determine_interface_name(self.interface_ip)

        # Verrous
        self.lock = threading.Lock()
        self.conn_lock = threading.Lock()
        self.process_lock = threading.Lock()
        self.traffic_lock = threading.Lock()
        self.device_lock = threading.Lock()

        # Données
        self.peers = {}
        self.peer_stats = {}
        self.active_devices = set()
        self.active_connections = []
        self.process_stats = {}

        # Statistiques de trafic
        self.traffic_history = deque(maxlen=MAX_GRAPH_SAMPLES)
        self.current_send_bps = 0.0
        self.current_recv_bps = 0.0
        self.peak_send_bps = 0.0
        self.peak_recv_bps = 0.0
        self.total_sent = 0
        self.total_recv = 0

        # Historique et alertes
        self.history_db = HistoryDatabase()
        self.alert_manager = AlertManager()
        self._prev_io = {}
        self._snapshot_counter = 0

        # Cache
        self._has_process_net_counters = hasattr(psutil.Process(), "net_io_counters")
        self._process_prev_io = {}
        self._pid_name_cache = {}
        self._connection_poll_interval = CONNECTION_POLL_INTERVAL
        self._scan_poll_interval = SCAN_POLL_INTERVAL
        self._device_ttl = max(DEVICE_TTL, self.timeout)
        self._device_last_seen = {}
        self._connection_count = 0
        self._established_count = 0
        self._listening_count = 0

        # Socket serveur
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind((host, port))
        except OSError as e:
            print(f"⚠️  Impossible de se lier au port {port}: {e}")
            print("   Essayez de changer le port ou de fermer l'application déjà en cours.")
            self.sock.close()
            raise
        self.running = False

    def start(self):
        self.running = True
        threading.Thread(target=self._cleanup_loop, daemon=True).start()
        threading.Thread(target=self._traffic_monitor_loop, daemon=True).start()
        threading.Thread(target=self._scan_network, daemon=True).start()
        threading.Thread(target=self._connection_monitor_loop, daemon=True).start()
        threading.Thread(target=self._history_loop, daemon=True).start()

        while self.running:
            try:
                data, addr = self.sock.recvfrom(1024)
            except OSError:
                break

            message = data.decode("utf-8", errors="ignore").strip()
            if not message:
                continue

            self._update_peer_stats(addr, bytes_received=len(data))
            response = self._handle_message(message, addr)
            if response is not None:
                payload = response.encode("utf-8")
                try:
                    self.sock.sendto(payload, addr)
                    self._update_peer_stats(addr, bytes_sent=len(payload))
                except OSError:
                    pass

    def stop(self):
        self.running = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    def _determine_interface_ip(self):
        if self.host != "0.0.0.0":
            return self.host
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect(("8.8.8.8", 80))
                return probe.getsockname()[0]
        except OSError:
            return self.host

    def _determine_interface_name(self, interface_ip):
        if interface_ip in ("0.0.0.0", ""):
            return None
        try:
            for nic, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family == socket.AF_INET and addr.address == interface_ip:
                        return nic
        except OSError:
            pass
        return None

    def _speedtest_response(self, size):
        if size < 0:
            return "error:invalid size"
        if size > 4096:
            return "error:size too large, max 4096"
        return "speedtest:" + ("x" * size)

    def _cleanup_loop(self):
        while self.running:
            time.sleep(self.timeout / 2)
            with self.lock:
                now = time.time()
                stale = [peer for peer, last in self.peers.items() if now - last > self.timeout]
                for peer in stale:
                    del self.peers[peer]

    def _update_peer_stats(self, addr, bytes_received=0, bytes_sent=0):
        peer_id = f"{addr[0]}:{addr[1]}"
        now = time.time()
        with self.lock:
            stats = self.peer_stats.setdefault(
                peer_id,
                {"first_seen": now, "last_seen": now, "bytes_received": 0, "bytes_sent": 0},
            )
            stats["last_seen"] = now
            stats["bytes_received"] += bytes_received
            stats["bytes_sent"] += bytes_sent

    def _handle_message(self, message, addr):
        if message.startswith("announce:"):
            peer_name = message.split(":", 1)[1].strip()
            if peer_name:
                with self.lock:
                    self.peers[f"{addr[0]}:{addr[1]}"] = time.time()
            return self._peer_list()
        if message == "list":
            return self._peer_list()
        if message == "stats":
            return self._peer_stats_summary()
        if message == "info":
            return self._info()
        if message.startswith("speedtest:"):
            try:
                size = int(message.split(":", 1)[1].strip())
            except ValueError:
                return "error:invalid size"
            return self._speedtest_response(size)
        if message == "ping":
            return "pong"
        return "error:unknown command"

    def _peer_list(self):
        with self.lock:
            if not self.peers:
                return "no peers"
            return "\n".join(sorted(self.peers.keys()))

    def _peer_stats_summary(self):
        with self.lock:
            if not self.peer_stats:
                return "no peers"
            total_received = sum(stats["bytes_received"] for stats in self.peer_stats.values())
            total_sent = sum(stats["bytes_sent"] for stats in self.peer_stats.values())
            most_active_peer = max(self.peer_stats.items(), key=lambda item: item[1]["bytes_received"])[0]
            last_peer_contacted = max(self.peer_stats.items(), key=lambda item: item[1]["last_seen"])[0]
            return (
                f"server interface: {self.interface_ip}:{self.port}\n"
                f"total peers: {len(self.peer_stats)}\n"
                f"most active peer: {most_active_peer}\n"
                f"last peer contacted: {last_peer_contacted}\n"
                f"total received: {total_received} bytes\n"
                f"total sent: {total_sent} bytes"
            )

    def _info(self):
        with self.conn_lock:
            conn_count = len(self.active_connections)
        with self.device_lock:
            device_count = len(self.active_devices)
        return (
            f"server interface: {self.interface_ip}:{self.port}\n"
            f"listening address: {self.host}:{self.port}\n"
            f"timeout: {self.timeout} seconds\n"
            f"known peers: {len(self.peers)}\n"
            f"active connections: {conn_count}\n"
            f"active devices: {device_count}"
        )

    def _pick_counters(self, pernic_stats):
        if not pernic_stats:
            return None
        if self.interface_name and self.interface_name in pernic_stats:
            return pernic_stats[self.interface_name]
        if self.interface_name is None and self.interface_ip not in ("0.0.0.0", ""):
            self.interface_name = self._determine_interface_name(self.interface_ip)
            if self.interface_name and self.interface_name in pernic_stats:
                return pernic_stats[self.interface_name]
        total_sent = 0
        total_recv = 0
        for counters in pernic_stats.values():
            total_sent += counters.bytes_sent
            total_recv += counters.bytes_recv
        class AggregatedCounters:
            pass
        agg = AggregatedCounters()
        agg.bytes_sent = total_sent
        agg.bytes_recv = total_recv
        return agg

    def _traffic_monitor_loop(self):
        prev_counters = None
        prev_time = None
        while self.running:
            now = time.time()
            try:
                pernic = psutil.net_io_counters(pernic=True)
            except OSError:
                pernic = None
            counters = self._pick_counters(pernic)
            if counters is not None:
                with self.traffic_lock:
                    self.total_sent = counters.bytes_sent
                    self.total_recv = counters.bytes_recv
                if prev_counters is not None and prev_time is not None:
                    elapsed = max(0.1, now - prev_time)
                    delta_sent = max(0, counters.bytes_sent - prev_counters.bytes_sent)
                    delta_recv = max(0, counters.bytes_recv - prev_counters.bytes_recv)
                    send_bps = delta_sent / elapsed
                    recv_bps = delta_recv / elapsed
                    with self.traffic_lock:
                        self.current_send_bps = send_bps
                        self.current_recv_bps = recv_bps
                        self.peak_send_bps = max(self.peak_send_bps, send_bps)
                        self.peak_recv_bps = max(self.peak_recv_bps, recv_bps)
                        self.traffic_history.append((recv_bps, send_bps))
                prev_counters = counters
                prev_time = now
            time.sleep(1)

    def _history_loop(self):
        """Boucle pour enregistrer l'historique."""
        while self.running:
            time.sleep(HISTORY_SNAPSHOT_INTERVAL)
            try:
                with self.traffic_lock:
                    data = {
                        "upload_bps": self.current_send_bps,
                        "download_bps": self.current_recv_bps,
                        "total_sent": self.total_sent,
                        "total_recv": self.total_recv,
                    }
                with self.conn_lock:
                    data["connection_count"] = self._connection_count
                with self.process_lock:
                    data["process_count"] = len(self.process_stats)
                
                self.history_db.add_traffic_snapshot(data)
                self._snapshot_counter += 1
                
                # Nettoyer les anciennes données toutes les heures
                if self._snapshot_counter >= HISTORY_CLEANUP_THRESHOLD:
                    self.history_db.cleanup_old_data(days=7)
                    self._snapshot_counter = 0
            except:
                pass

    def _extract_ip(self, endpoint):
        ip = getattr(endpoint, "ip", None)
        if ip is None and isinstance(endpoint, (tuple, list)) and endpoint:
            ip = endpoint[0]
        return ip

    def _is_lan_ip(self, ip_str):
        if not ip_str or ip_str == self.interface_ip:
            return False
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        if ip.is_unspecified or ip.is_multicast or ip.is_loopback:
            return False
        return ip.is_private or ip.is_link_local

    def _collect_arp_ips(self):
        candidates = set()
        try:
            output = subprocess.check_output(
                ["arp", "-a"],
                stderr=subprocess.DEVNULL, text=True, timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        except (OSError, subprocess.SubprocessError):
            return candidates
        for token in output.split():
            if self._is_lan_ip(token):
                candidates.add(token)
        return candidates

    def _refresh_active_devices(self, connections, include_arp=False):
        now = time.time()
        discovered = set()
        for conn in connections:
            remote_ip = conn.get("remote_ip")
            if self._is_lan_ip(remote_ip):
                discovered.add(remote_ip)
        with self.lock:
            peer_ips = [peer.split(":", 1)[0] for peer in self.peers.keys()]
        for peer_ip in peer_ips:
            if self._is_lan_ip(peer_ip):
                discovered.add(peer_ip)
        if include_arp:
            discovered.update(self._collect_arp_ips())
        with self.device_lock:
            for ip in discovered:
                self._device_last_seen[ip] = now
            cutoff = now - self._device_ttl
            self._device_last_seen = {
                ip: seen_at for ip, seen_at in self._device_last_seen.items() if seen_at >= cutoff
            }
            self.active_devices = set(self._device_last_seen.keys())

    def _scan_network(self):
        while self.running:
            time.sleep(self._scan_poll_interval)
            self._refresh_active_devices([], include_arp=True)

    def _get_process_name(self, pid):
        if pid <= 0:
            return "system"
        now = time.time()
        cached = self._pid_name_cache.get(pid)
        if cached and now - cached["ts"] < 10:
            return cached["name"]
        try:
            name = psutil.Process(pid).name()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            name = "unknown"
        self._pid_name_cache[pid] = {"name": name, "ts": now}
        return name

    def _get_service_type(self, remote_addr, local_addr):
        """Détermine le type de service (HTTP, HTTPS, etc.) basé sur les ports."""
        try:
            remote_port = None
            local_port = None
            if isinstance(remote_addr, (tuple, list)) and len(remote_addr) >= 2:
                remote_port = remote_addr[1]
            if isinstance(local_addr, (tuple, list)) and len(local_addr) >= 2:
                local_port = local_addr[1]
            
            ports_to_check = [remote_port, local_port]
            for port in ports_to_check:
                if port == 80:
                    return "HTTP"
                elif port == 443:
                    return "HTTPS"
                elif port == 22:
                    return "SSH"
                elif port == 21:
                    return "FTP"
                elif port == 25:
                    return "SMTP"
                elif port == 53:
                    return "DNS"
                elif port == 110:
                    return "POP3"
                elif port == 143:
                    return "IMAP"
                elif port == 3306:
                    return "MySQL"
                elif port == 5432:
                    return "PostgreSQL"
                elif port == 3389:
                    return "RDP"
                elif port == 8080:
                    return "HTTP-Proxy"
                elif port == 8443:
                    return "HTTPS-Alt"
            return "Autre"
        except:
            return "Inconnu"

    def _connection_monitor_loop(self):
        while self.running:
            try:
                connections = []
                established_count = 0
                listening_count = 0
                http_count = 0
                https_count = 0
                suspicious_count = 0
                
                for conn in psutil.net_connections(kind="inet"):
                    if not conn.laddr:
                        continue
                    protocol = "TCP" if conn.type == socket.SOCK_STREAM else "UDP"
                    local = format_endpoint(conn.laddr)
                    remote = format_endpoint(conn.raddr) if conn.raddr else ""
                    status = conn.status if conn.status else ("OPEN" if protocol == "UDP" else "UNKNOWN")
                    if status == "ESTABLISHED":
                        established_count += 1
                    elif status == "LISTEN":
                        listening_count += 1
                    local_ip = self._extract_ip(conn.laddr)
                    remote_ip = self._extract_ip(conn.raddr) if conn.raddr else None
                    pid = conn.pid or 0
                    name = self._get_process_name(pid)
                    service = self._get_service_type(conn.raddr, conn.laddr)
                    if service == "HTTP":
                        http_count += 1
                    elif service == "HTTPS":
                        https_count += 1
                    
                    # Vérifier si connexion suspecte
                    is_suspicious = False
                    if remote_ip and is_suspicious_ip(remote_ip):
                        is_suspicious = True
                        suspicious_count += 1
                    if conn.raddr and is_suspicious_port(conn.raddr[1]):
                        is_suspicious = True
                        if not is_suspicious:
                            suspicious_count += 1
                    
                    connections.append({
                        "protocol": protocol,
                        "pid": pid,
                        "name": name,
                        "local": local,
                        "remote": remote,
                        "status": status,
                        "local_ip": local_ip,
                        "remote_ip": remote_ip,
                        "service": service,
                        "is_suspicious": is_suspicious,
                    })
                
                with self.conn_lock:
                    self.active_connections = connections
                    self._connection_count = len(connections)
                    self._established_count = established_count
                    self._listening_count = listening_count
                
                self._update_process_stats(connections)
                self._refresh_active_devices(connections, include_arp=False)
                
                # Vérifier les alertes
                traffic_data = {
                    "upload_bps": self.current_send_bps,
                    "download_bps": self.current_recv_bps,
                }
                alerts = self.alert_manager.check_alerts(connections, traffic_data)
                
                # Enregistrer les alertes dans la base
                for alert in alerts:
                    self.history_db.add_alert(
                        alert["type"],
                        alert["severity"],
                        alert["message"],
                        alert.get("details", ""),
                    )
                
            except (psutil.Error, OSError):
                pass
            time.sleep(self._connection_poll_interval)

    def _update_process_stats(self, connections):
        by_process = {}
        for conn in connections:
            key = (conn["pid"], conn["name"])
            entry = by_process.setdefault(
                key,
                {
                    "pid": conn["pid"],
                    "name": conn["name"],
                    "connections": 0,
                    "established": 0,
                    "upload_bps": None,
                    "download_bps": None,
                    "total_sent": None,
                    "total_recv": None,
                },
            )
            entry["connections"] += 1
            if conn["status"] == "ESTABLISHED":
                entry["established"] += 1
        
        # Obtenir les statistiques de trafic global
        try:
            current_io = psutil.net_io_counters()
            current_time = time.time()
            
            if self._prev_io:
                elapsed = max(0.1, current_time - self._prev_io['time'])
                delta_sent = max(0, current_io.bytes_sent - self._prev_io['sent'])
                delta_recv = max(0, current_io.bytes_recv - self._prev_io['recv'])
                global_upload_bps = delta_sent / elapsed
                global_download_bps = delta_recv / elapsed
            else:
                global_upload_bps = 0.0
                global_download_bps = 0.0
            
            self._prev_io = {
                'time': current_time,
                'sent': current_io.bytes_sent,
                'recv': current_io.bytes_recv,
            }
        except Exception:
            global_upload_bps = 0.0
            global_download_bps = 0.0
        
        # Répartir le trafic global entre toutes les connexions actives
        active_connections = [c for c in connections if c.get("status") == "ESTABLISHED"]
        total_active = len(active_connections) if active_connections else 1
        
        # Ajouter les estimations de bande passante à chaque connexion
        for conn in connections:
            if conn.get("status") == "ESTABLISHED":
                conn["estimated_upload_bps"] = global_upload_bps / total_active
                conn["estimated_download_bps"] = global_download_bps / total_active
            else:
                conn["estimated_upload_bps"] = 0.0
                conn["estimated_download_bps"] = 0.0
        
        # Calculer les stats par processus
        for entry in by_process.values():
            pid = entry["pid"]
            proc_conns = entry["connections"]
            if proc_conns > 0 and global_upload_bps > 0:
                entry["upload_bps"] = global_upload_bps * (proc_conns / total_active)
                entry["download_bps"] = global_download_bps * (proc_conns / total_active)
            else:
                entry["upload_bps"] = 0.0
                entry["download_bps"] = 0.0
            entry["total_sent"] = current_io.bytes_sent
            entry["total_recv"] = current_io.bytes_recv
        
        with self.process_lock:
            self.process_stats = by_process

    def get_dashboard_snapshot(self, include_tables=True):
        with self.traffic_lock:
            history = list(self.traffic_history)
            current_send_bps = self.current_send_bps
            current_recv_bps = self.current_recv_bps
            peak_send_bps = self.peak_send_bps
            peak_recv_bps = self.peak_recv_bps
            total_sent = self.total_sent
            total_recv = self.total_recv
        with self.lock:
            peer_count = len(self.peers)
        with self.conn_lock:
            connection_count = self._connection_count
            established_count = self._established_count
            listening_count = self._listening_count
            if include_tables:
                connections = list(self.active_connections)
            else:
                connections = []
        with self.device_lock:
            device_count = len(self.active_devices)
            if include_tables:
                devices = sorted(self.active_devices)
            else:
                devices = []
        if include_tables:
            with self.process_lock:
                processes = list(self.process_stats.values())
            with self.lock:
                peers = sorted(self.peers.keys())
        else:
            processes = []
            peers = []
        return {
            "interface_ip": self.interface_ip,
            "interface_name": self.interface_name or "all interfaces",
            "listening": f"{self.host}:{self.port}",
            "current_send_bps": current_send_bps,
            "current_recv_bps": current_recv_bps,
            "peak_send_bps": peak_send_bps,
            "peak_recv_bps": peak_recv_bps,
            "total_sent": total_sent,
            "total_recv": total_recv,
            "traffic_history": history,
            "connection_count": connection_count,
            "established_count": established_count,
            "listening_count": listening_count,
            "device_count": device_count,
            "connections": connections,
            "processes": processes,
            "devices": devices,
            "peers": peers,
            "peer_count": peer_count,
        }


class Worker(QThread):
    def __init__(self, tracker):
        super().__init__()
        self.tracker = tracker

    def run(self):
        self.tracker.start()