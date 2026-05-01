"""
Gestionnaire d'alertes pour Network Monitor Pro.
"""

import csv
import time
from collections import deque

from network_monitor.config import DEFAULT_ALERT_THRESHOLD, MAX_ALERT_HISTORY
from network_monitor.utils import format_bps, is_suspicious_ip, is_suspicious_port


class AlertManager:
    """Gère les alertes de surveillance."""
    
    def __init__(self):
        self.alert_callbacks = []
        self.alert_history = deque(maxlen=MAX_ALERT_HISTORY)
        self.thresholds = {
            "upload": DEFAULT_ALERT_THRESHOLD,
            "download": DEFAULT_ALERT_THRESHOLD,
            "connections": 100,
        }
        self.suspicious_alerts_enabled = True
        self.high_bandwidth_alerts_enabled = True
    
    def add_callback(self, callback):
        """Ajoute un callback pour les alertes."""
        self.alert_callbacks.append(callback)
    
    def check_alerts(self, connections, traffic_data):
        """Vérifie les conditions d'alerte."""
        alerts = []
        
        # Vérifier les connexions suspectes
        if self.suspicious_alerts_enabled:
            for conn in connections:
                remote_ip = conn.get("remote_ip", "")
                remote_port_str = conn.get("remote", "").split(":")[-1] if conn.get("remote") else ""
                try:
                    remote_port = int(remote_port_str)
                except (ValueError, IndexError):
                    remote_port = 0
                
                if is_suspicious_ip(remote_ip):
                    alert = {
                        "type": "suspicious_ip",
                        "severity": "high",
                        "message": f"IP suspecte détectée: {remote_ip}",
                        "details": f"Processus: {conn.get('name', 'unknown')} ({conn.get('pid', '?')})",
                    }
                    alerts.append(alert)
                
                if is_suspicious_port(remote_port):
                    alert = {
                        "type": "suspicious_port",
                        "severity": "medium",
                        "message": f"Port suspect détecté: {remote_port}",
                        "details": f"IP: {remote_ip} | Processus: {conn.get('name', 'unknown')}",
                    }
                    alerts.append(alert)
        
        # Vérifier la bande passante élevée
        if self.high_bandwidth_alerts_enabled:
            upload_bps = traffic_data.get("upload_bps", 0)
            download_bps = traffic_data.get("download_bps", 0)
            
            if upload_bps > self.thresholds["upload"]:
                alert = {
                    "type": "high_upload",
                    "severity": "warning",
                    "message": f"Upload élevé: {format_bps(upload_bps)}",
                    "details": f"Seuil: {format_bps(self.thresholds['upload'])}",
                }
                alerts.append(alert)
            
            if download_bps > self.thresholds["download"]:
                alert = {
                    "type": "high_download",
                    "severity": "warning",
                    "message": f"Download élevé: {format_bps(download_bps)}",
                    "details": f"Seuil: {format_bps(self.thresholds['download'])}",
                }
                alerts.append(alert)
        
        # Vérifier le nombre de connexions
        if len(connections) > self.thresholds["connections"]:
            alert = {
                "type": "too_many_connections",
                "severity": "info",
                "message": f"Nombre élevé de connexions: {len(connections)}",
                "details": f"Seuil: {self.thresholds['connections']}",
            }
            alerts.append(alert)
        
        # Notifier les callbacks
        for alert in alerts:
            self.alert_history.append(alert)
            for callback in self.alert_callbacks:
                try:
                    callback(alert)
                except:
                    pass
        
        return alerts
    
    def export_alerts_csv(self, filename):
        """Exporte les alertes en CSV."""
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Type", "Severity", "Message", "Details"])
            for alert in self.alert_history:
                writer.writerow([
                    datetime.fromtimestamp(time.time()).strftime("%Y-%m-%d %H:%M:%S"),
                    alert.get("type", ""),
                    alert.get("severity", ""),
                    alert.get("message", ""),
                    alert.get("details", ""),
                ])