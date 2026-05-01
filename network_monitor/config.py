"""
Configuration et constantes pour Network Monitor Pro.
"""

# ============================================
# CONFIGURATION & CONSTANTES
# ============================================

# IPs suspectes/connues pour la détection d'intrusion
SUSPICIOUS_IP_RANGES = [
    "185.220.101.",  # Tor exit nodes (common)
    "23.129.64.",    # Tor exit nodes
    "199.249.230.",  # Known scanners
]

# Ports suspects
SUSPICIOUS_PORTS = [4444, 5555, 6666, 31337, 12345, 54321]

# Seuil d'alerte par défaut (en B/s)
DEFAULT_ALERT_THRESHOLD = 10 * 1024 * 1024  # 10 MB/s

# Configuration du serveur
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 18999
DEFAULT_TIMEOUT = 120

# Intervalles de surveillance
CONNECTION_POLL_INTERVAL = 1.5  # secondes
SCAN_POLL_INTERVAL = 20.0  # secondes
DEVICE_TTL = 45  # secondes (minimum)
HISTORY_SNAPSHOT_INTERVAL = 10  # secondes
HISTORY_CLEANUP_THRESHOLD = 360  # nombre de snapshots avant nettoyage

# Limites d'affichage
MAX_TABLE_ROWS = 500
MAX_GRAPH_SAMPLES = 180
MAX_ALERT_HISTORY = 100