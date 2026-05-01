"""
Point d'entrée principal pour Network Monitor Pro.
"""

import sys

from PyQt6.QtWidgets import QApplication

from network_monitor.tracker import NetworkTracker, Worker
from network_monitor.window import NetworkMonitorWindow


def main():
    """Fonction principale pour lancer l'application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Network Monitor Pro")
    app.setOrganizationName("NetSec Tools")

    # Créer le tracker et le worker
    tracker = NetworkTracker(host="0.0.0.0", port=18999, timeout=120)
    worker = Worker(tracker)

    # Créer et afficher la fenêtre
    window = NetworkMonitorWindow(tracker, worker)
    window.show()

    # Démarrer automatiquement
    worker.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()