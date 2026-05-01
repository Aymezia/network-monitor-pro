"""
Gestion de la base de données d'historique pour Network Monitor Pro.
"""

import sqlite3
import time


class HistoryDatabase:
    """Gère l'historique des données réseau dans SQLite."""
    
    def __init__(self, db_path="network_history.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Initialise la base de données."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Table des snapshots de trafic
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS traffic_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                upload_bps REAL,
                download_bps REAL,
                total_sent INTEGER,
                total_recv INTEGER,
                connection_count INTEGER,
                process_count INTEGER
            )
        """)
        
        # Table des connexions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                protocol TEXT,
                pid INTEGER,
                process_name TEXT,
                local_ip TEXT,
                local_port INTEGER,
                remote_ip TEXT,
                remote_port INTEGER,
                status TEXT,
                service TEXT,
                upload_bps REAL,
                download_bps REAL
            )
        """)
        
        # Table des alertes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                alert_type TEXT,
                severity TEXT,
                message TEXT,
                details TEXT
            )
        """)
        
        # Index pour les recherches
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_traffic_time ON traffic_snapshots(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conn_time ON connections(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alert_time ON alerts(timestamp)")
        
        conn.commit()
        conn.close()
    
    def add_traffic_snapshot(self, data):
        """Ajoute un snapshot de trafic."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO traffic_snapshots 
            (timestamp, upload_bps, download_bps, total_sent, total_recv, connection_count, process_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            time.time(),
            data.get("upload_bps", 0),
            data.get("download_bps", 0),
            data.get("total_sent", 0),
            data.get("total_recv", 0),
            data.get("connection_count", 0),
            data.get("process_count", 0),
        ))
        conn.commit()
        conn.close()
    
    def add_connection(self, conn_data):
        """Ajoute une connexion à l'historique."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO connections 
            (timestamp, protocol, pid, process_name, local_ip, local_port, remote_ip, remote_port, status, service, upload_bps, download_bps)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            time.time(),
            conn_data.get("protocol", ""),
            conn_data.get("pid", 0),
            conn_data.get("name", ""),
            conn_data.get("local_ip", ""),
            conn_data.get("remote", "").split(":")[-1] if conn_data.get("remote") else 0,
            conn_data.get("remote_ip", ""),
            int(conn_data.get("remote", "").split(":")[-1]) if conn_data.get("remote") else 0,
            conn_data.get("status", ""),
            conn_data.get("service", ""),
            conn_data.get("estimated_upload_bps", 0),
            conn_data.get("estimated_download_bps", 0),
        ))
        conn.commit()
        conn.close()
    
    def add_alert(self, alert_type, severity, message, details=""):
        """Ajoute une alerte."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO alerts (timestamp, alert_type, severity, message, details)
            VALUES (?, ?, ?, ?, ?)
        """, (time.time(), alert_type, severity, message, details))
        conn.commit()
        conn.close()
    
    def get_traffic_history(self, hours=24):
        """Récupère l'historique de trafic."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cutoff = time.time() - (hours * 3600)
        cursor.execute("""
            SELECT timestamp, upload_bps, download_bps, total_sent, total_recv, connection_count
            FROM traffic_snapshots
            WHERE timestamp >= ?
            ORDER BY timestamp ASC
        """, (cutoff,))
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "timestamp": row[0],
                "upload_bps": row[1],
                "download_bps": row[2],
                "total_sent": row[3],
                "total_recv": row[4],
                "connection_count": row[5],
            }
            for row in rows
        ]
    
    def get_top_processes(self, hours=1, limit=10):
        """Récupère le top des processus par consommation."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cutoff = time.time() - (hours * 3600)
        cursor.execute("""
            SELECT process_name, pid, 
                   SUM(upload_bps) as total_upload,
                   SUM(download_bps) as total_download,
                   COUNT(*) as connection_count
            FROM connections
            WHERE timestamp >= ?
            GROUP BY process_name, pid
            ORDER BY (total_upload + total_download) DESC
            LIMIT ?
        """, (cutoff, limit))
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "name": row[0],
                "pid": row[1],
                "total_upload": row[2],
                "total_download": row[3],
                "connections": row[4],
            }
            for row in rows
        ]
    
    def cleanup_old_data(self, days=7):
        """Nettoie les anciennes données."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cutoff = time.time() - (days * 86400)
        cursor.execute("DELETE FROM traffic_snapshots WHERE timestamp < ?", (cutoff,))
        cursor.execute("DELETE FROM connections WHERE timestamp < ?", (cutoff,))
        cursor.execute("DELETE FROM alerts WHERE timestamp < ?", (cutoff,))
        conn.commit()
        conn.close()