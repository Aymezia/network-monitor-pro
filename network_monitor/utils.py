"""
Fonctions utilitaires pour Network Monitor Pro.
"""

import math

from network_monitor.config import SUSPICIOUS_IP_RANGES, SUSPICIOUS_PORTS


def format_bytes(value):
    """Formate une valeur en octets avec unité appropriée."""
    size = float(max(0, value))
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def format_bps(value):
    """Formate un débit en bits/seconde."""
    return f"{format_bytes(value)}/s"


def format_endpoint(addr):
    """Formate une adresse IP:port."""
    if not addr:
        return ""
    ip = getattr(addr, "ip", None)
    port = getattr(addr, "port", None)
    if ip is None and isinstance(addr, (tuple, list)) and len(addr) >= 2:
        ip, port = addr[0], addr[1]
    if ip is None:
        return str(addr)
    return f"{ip}:{port}"


def calc_axis_max(max_value):
    """Calcule la valeur maximale de l'axe pour les graphiques."""
    if max_value <= 1:
        return 1.0
    exponent = math.floor(math.log10(max_value))
    base = 10 ** exponent
    for factor in (1, 2, 5, 10):
        candidate = factor * base
        if candidate >= max_value:
            return float(candidate)
    return float(max_value)


def is_suspicious_ip(ip_str):
    """Vérifie si une IP est suspecte."""
    if not ip_str:
        return False
    for prefix in SUSPICIOUS_IP_RANGES:
        if ip_str.startswith(prefix):
            return True
    return False


def is_suspicious_port(port):
    """Vérifie si un port est suspect."""
    return port in SUSPICIOUS_PORTS