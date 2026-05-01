"""
Fenêtre principale de Network Monitor Pro.
"""

import csv
import sys
import time
from datetime import datetime

import ipaddress
import psutil
from PyQt6.QtCore import QMarginsF, QPointF, QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QFontDatabase, QLinearGradient, QPainter, QPainterPath, QPen, QBrush
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QScrollArea,
    QSplitter,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QTabWidget,
    QStatusBar,
    QStyle,
    QStyledItemDelegate,
    QSpinBox,
    QCheckBox,
    QRadioButton,
    QButtonGroup,
    QSpacerItem,
    QSizePolicy,
)

from network_monitor.config import MAX_TABLE_ROWS
from network_monitor.utils import format_bytes, format_bps
from network_monitor.widgets import NumericTableItem, ThroughputGraph, MetricCard
from network_monitor import (
    __version__,
    __author__,
    __website__,
    __email__,
    __license__,
    __copyright__,
    __description__,
)


class NetworkMonitorWindow(QMainWindow):
    def __init__(self, tracker, worker):
        super().__init__()
        self.tracker = tracker
        self.worker = worker
        self._table_tick_counter = 0
        self._tables_paused = False
        self._last_devices = ()
        self._last_peers = ()

        self.init_ui()
        self.apply_styles()

        # Connexions
        self.process_filter.textChanged.connect(self._request_table_refresh)
        self.conn_filter.textChanged.connect(self._request_table_refresh)
        self.btn_pause.triggered.connect(self._toggle_pause)
        self.btn_export.triggered.connect(self._export_data)
        self.btn_export_csv.triggered.connect(self._export_csv)
        self.btn_alerts.triggered.connect(self._show_alerts)
        self.btn_history.triggered.connect(self._show_history)
        self.btn_top.triggered.connect(self._show_top_processes)

        # Callback pour alertes
        self.tracker.alert_manager.add_callback(self._on_alert)

        self.filter_timer = QTimer(self)
        self.filter_timer.setSingleShot(True)
        self.filter_timer.timeout.connect(self.refresh_tables)

        self.fast_timer = QTimer(self)
        self.fast_timer.timeout.connect(self.update_stats)
        self.fast_timer.start(900)

        self.table_timer = QTimer(self)
        self.table_timer.timeout.connect(self._tick_table_refresh)
        self.table_timer.start(1500)

        self.update_stats()
        self.refresh_tables()

    def init_ui(self):
        self.setWindowTitle("Network Monitor Pro - Analyseur de Trafic Réseau Ultra-Complet")
        self.setGeometry(100, 100, 1500, 1000)

        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # ===== BARRE D'OUTILS =====
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))

        self.btn_start = toolbar.addAction("▶ Démarrer")
        self.btn_start.triggered.connect(self._start_monitoring)
        self.btn_stop = toolbar.addAction("⏹ Arrêter")
        self.btn_stop.triggered.connect(self._stop_monitoring)
        toolbar.addSeparator()
        self.btn_export = toolbar.addAction("📊 Exporter")
        self.btn_export_csv = toolbar.addAction("📄 Export CSV")
        self.btn_pause = toolbar.addAction("⏸ Pause")
        self.btn_pause.setCheckable(True)
        toolbar.addSeparator()
        self.btn_alerts = toolbar.addAction("🔔 Alertes")
        self.btn_history = toolbar.addAction("📈 Historique")
        self.btn_top = toolbar.addAction("🏆 Top 10")
        self.btn_firewall = toolbar.addAction("🛡️ Firewall")
        self.btn_firewall.triggered.connect(self._show_firewall)
        self.btn_map = toolbar.addAction("🗺️ Carte Réseau")
        self.btn_map.triggered.connect(self._show_network_map)
        toolbar.addSeparator()
        self.btn_about = toolbar.addAction("ℹ️ À propos")
        self.btn_about.triggered.connect(self._show_about)

        # Filtres rapides
        toolbar.addWidget(QLabel("  Filtre: "))
        self.quick_filter = QLineEdit()
        self.quick_filter.setPlaceholderText("Recherche rapide...")
        self.quick_filter.setFixedWidth(200)
        toolbar.addWidget(self.quick_filter)

        main_layout.addWidget(toolbar)

        # ===== TABLEAU DE BORD =====
        dashboard = QFrame()
        dashboard.setObjectName("dashboard")
        dashboard_layout = QGridLayout(dashboard)
        dashboard_layout.setContentsMargins(0, 0, 0, 0)
        dashboard_layout.setSpacing(8)

        # Cartes de métriques
        self.card_download = MetricCard("Débit Descendant", "0 B/s", "↓", "#00B4D8")
        self.card_upload = MetricCard("Débit Montant", "0 B/s", "↑", "#FF823C")
        self.card_connections = MetricCard("Connexions Actives", "0", "🔗", "#38B000")
        self.card_processes = MetricCard("Processus", "0", "⚙️", "#9B5DE5")
        self.card_devices = MetricCard("Appareils Réseau", "0", "🖥️", "#F15BB5")
        self.card_peers = MetricCard("Pairs Connectés", "0", "🌐", "#00F5D4")
        self.card_alerts = MetricCard("Alertes", "0", "🔔", "#FF4444")

        dashboard_layout.addWidget(self.card_download, 0, 0)
        dashboard_layout.addWidget(self.card_upload, 0, 1)
        dashboard_layout.addWidget(self.card_connections, 0, 2)
        dashboard_layout.addWidget(self.card_processes, 1, 0)
        dashboard_layout.addWidget(self.card_devices, 1, 1)
        dashboard_layout.addWidget(self.card_peers, 1, 2)
        dashboard_layout.addWidget(self.card_alerts, 0, 3)

        main_layout.addWidget(dashboard)

        # ===== GRAPHIQUE DE DÉBIT =====
        graph_frame = QFrame()
        graph_frame.setObjectName("graphFrame")
        graph_frame.setFixedHeight(260)
        graph_layout = QVBoxLayout(graph_frame)
        graph_layout.setContentsMargins(0, 0, 0, 0)

        graph_title = QLabel("📈 ÉVOLUTION DU TRAFIC RÉSEAU EN TEMPS RÉEL")
        graph_title.setStyleSheet("color: #00B4D8; font-size: 14px; font-weight: 700; padding: 5px;")
        graph_layout.addWidget(graph_title)

        self.throughput_graph = ThroughputGraph()
        graph_layout.addWidget(self.throughput_graph)

        main_layout.addWidget(graph_frame)

        # ===== ONGLETS =====
        self.tabs = QTabWidget()
        self.tabs.setObjectName("mainTabs")
        main_layout.addWidget(self.tabs, 1)

        # Onglet Connexions
        conn_tab = QWidget()
        conn_layout = QVBoxLayout(conn_tab)
        conn_layout.setContentsMargins(0, 0, 0, 0)

        # Filtres connexions
        filter_frame = QFrame()
        filter_frame.setObjectName("filterFrame")
        filter_layout = QHBoxLayout(filter_frame)
        filter_layout.setContentsMargins(5, 5, 5, 5)

        filter_layout.addWidget(QLabel("🔍 Proto:"))
        self.proto_filter = QComboBox()
        self.proto_filter.addItems(["Tous", "TCP", "UDP"])
        filter_layout.addWidget(self.proto_filter)

        filter_layout.addWidget(QLabel("État:"))
        self.state_filter = QComboBox()
        self.state_filter.addItems(["Tous", "ESTABLISHED", "LISTEN", "TIME_WAIT", "CLOSE_WAIT"])
        filter_layout.addWidget(self.state_filter)

        filter_layout.addWidget(QLabel("Service:"))
        self.service_filter = QComboBox()
        self.service_filter.addItems(["Tous", "HTTP", "HTTPS", "SSH", "DNS", "FTP", "Autre"])
        filter_layout.addWidget(self.service_filter)

        filter_layout.addWidget(QLabel("🔎"))
        self.conn_filter = QLineEdit()
        self.conn_filter.setPlaceholderText("Filtrer les connexions...")
        self.conn_filter.setFixedWidth(250)
        filter_layout.addWidget(self.conn_filter)

        filter_layout.addStretch()

        # Checkbox pour afficher seulement les suspectes
        self.suspicious_only = QCheckBox("⚠️ Suspectes seulement")
        self.suspicious_only.setStyleSheet("color: #FF4444; font-weight: bold;")
        filter_layout.addWidget(self.suspicious_only)

        conn_layout.addWidget(filter_frame)

        # Tableau connexions
        self.conn_table = QTableWidget()
        self.conn_table.setColumnCount(10)
        self.conn_table.setHorizontalHeaderLabels([
            "⚠️", "Service", "Protocole", "PID", "Processus", "Local", "Distant", "État", "↓ Reçu", "↑ Envoyé"
        ])
        self.conn_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.conn_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.conn_table.setAlternatingRowColors(True)
        self.conn_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        conn_layout.addWidget(self.conn_table)

        self.tabs.addTab(conn_tab, "🔗 Connexions")

        # Onglet Processus
        proc_tab = QWidget()
        proc_layout = QVBoxLayout(proc_tab)
        proc_layout.setContentsMargins(0, 0, 0, 0)

        proc_filter_frame = QFrame()
        proc_filter_layout = QHBoxLayout(proc_filter_frame)
        proc_filter_layout.setContentsMargins(5, 5, 5, 5)
        self.process_filter = QLineEdit()
        self.process_filter.setPlaceholderText("🔎 Filtrer les processus...")
        proc_filter_layout.addWidget(self.process_filter)
        proc_filter_layout.addStretch()
        proc_layout.addWidget(proc_filter_frame)

        self.process_table = QTableWidget()
        self.process_table.setColumnCount(7)
        self.process_table.setHorizontalHeaderLabels([
            "PID", "Processus", "Connexions", "Établies", "↓ Download", "↑ Upload", "Total"
        ])
        self.process_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.process_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.process_table.setAlternatingRowColors(True)
        self.process_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        proc_layout.addWidget(self.process_table)

        self.tabs.addTab(proc_tab, "⚙️ Processus")

        # Onglet Appareils
        device_tab = QWidget()
        device_layout = QVBoxLayout(device_tab)
        device_layout.setContentsMargins(0, 0, 0, 0)

        self.device_table = QTableWidget()
        self.device_table.setColumnCount(4)
        self.device_table.setHorizontalHeaderLabels([
            "Adresse IP", "Type", "Dernière Activité", "Statut"
        ])
        self.device_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.device_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.device_table.setAlternatingRowColors(True)
        self.device_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        device_layout.addWidget(self.device_table)

        self.tabs.addTab(device_tab, "🖥️ Appareils")

        # ===== BARRE DE STATUT =====
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Prêt - En attente de démarrage...")

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0a0e1a;
            }
            QWidget {
                color: #e0e8f5;
                font-family: "Segoe UI", "Bahnschrift", sans-serif;
                font-size: 13px;
            }
            QToolBar {
                background-color: #0d1525;
                border: 1px solid #1a2a4a;
                border-radius: 8px;
                padding: 5px;
                spacing: 5px;
            }
            QToolBar QToolButton {
                background-color: #1a2a4a;
                border: 1px solid #2a4a7a;
                border-radius: 5px;
                padding: 5px 12px;
                color: #e0e8f5;
            }
            QToolBar QToolButton:hover {
                background-color: #2a4a7a;
                border-color: #3a6aba;
            }
            QToolBar QToolButton:pressed {
                background-color: #1a3a6a;
            }
            QLineEdit, QComboBox {
                background-color: #0d1525;
                border: 1px solid #1a2a4a;
                border-radius: 5px;
                padding: 4px 8px;
                color: #e0e8f5;
                selection-background-color: #00B4D8;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #00B4D8;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #00B4D8;
                margin-right: 5px;
            }
            QFrame#dashboard {
                background-color: #0d1525;
                border: 1px solid #1a2a4a;
                border-radius: 10px;
            }
            QFrame#graphFrame {
                background-color: #0d1525;
                border: 1px solid #1a2a4a;
                border-radius: 10px;
            }
            QFrame#filterFrame {
                background-color: #0d1525;
                border: 1px solid #1a2a4a;
                border-radius: 8px;
            }
            QTabWidget::pane {
                border: 1px solid #1a2a4a;
                border-radius: 8px;
                background-color: #0d1525;
            }
            QTabBar::tab {
                background-color: #0d1525;
                border: 1px solid #1a2a4a;
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 8px 16px;
                margin-right: 2px;
                color: #8899aa;
            }
            QTabBar::tab:selected {
                background-color: #1a2a4a;
                color: #00B4D8;
                border-color: #2a4a7a;
            }
            QTabBar::tab:hover:!selected {
                background-color: #152040;
                color: #e0e8f5;
            }
            QTableWidget {
                background-color: #0a0e1a;
                alternate-background-color: #0d1525;
                border: 1px solid #1a2a4a;
                border-radius: 5px;
                gridline-color: #1a2a4a;
            }
            QTableWidget::item {
                padding: 4px 8px;
                border-bottom: 1px solid #1a2a4a;
            }
            QTableWidget::item:selected {
                background-color: #1a3a6a;
                color: #e0e8f5;
            }
            QHeaderView::section {
                background-color: #0d1525;
                border: 1px solid #1a2a4a;
                padding: 6px 8px;
                font-weight: 600;
                color: #00B4D8;
                text-transform: uppercase;
                font-size: 11px;
                letter-spacing: 0.5px;
            }
            QStatusBar {
                background-color: #0d1525;
                border-top: 1px solid #1a2a4a;
                color: #8899aa;
            }
            QScrollBar:vertical {
                background-color: #0a0e1a;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background-color: #1a2a4a;
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #2a4a7a;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar:horizontal {
                background-color: #0a0e1a;
                height: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:horizontal {
                background-color: #1a2a4a;
                border-radius: 5px;
                min-width: 20px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #2a4a7a;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
        """)

    def update_stats(self):
        """Met à jour les statistiques en temps réel."""
        try:
            snapshot = self.tracker.get_dashboard_snapshot(include_tables=False)

            # Mettre à jour les cartes
            self.card_download.set_value(format_bps(snapshot["current_recv_bps"]))
            self.card_download.set_meta(f"Pic: {format_bps(snapshot['peak_recv_bps'])}")

            self.card_upload.set_value(format_bps(snapshot["current_send_bps"]))
            self.card_upload.set_meta(f"Pic: {format_bps(snapshot['peak_send_bps'])}")

            self.card_connections.set_value(str(snapshot["connection_count"]))
            self.card_connections.set_meta(
                f"Établies: {snapshot['established_count']} | Écoute: {snapshot['listening_count']}"
            )

            self.card_processes.set_value(str(len(snapshot["processes"])))
            self.card_processes.set_meta(f"Total connexions: {snapshot['connection_count']}")

            self.card_devices.set_value(str(snapshot["device_count"]))
            self.card_devices.set_meta(f"Interface: {snapshot['interface_ip']}")

            self.card_peers.set_value(str(snapshot["peer_count"]))
            self.card_peers.set_meta(f"Serveur: {snapshot['listening']}")

            # Mettre à jour carte alertes
            alert_count = len(self.tracker.alert_manager.alert_history)
            self.card_alerts.set_value(str(alert_count))
            self.card_alerts.set_meta("Dernière heure")

            # Mettre à jour le graphique
            if snapshot["traffic_history"]:
                self.throughput_graph.set_series(snapshot["traffic_history"])

            # Barre de statut
            total_traffic = format_bytes(snapshot["total_sent"] + snapshot["total_recv"])
            self.status_bar.showMessage(
                f"📊 Trafic total: {total_traffic} | "
                f"🔗 Connexions: {snapshot['connection_count']} | "
                f"⚙️ Processus: {len(snapshot['processes'])} | "
                f"🖥️ Appareils: {snapshot['device_count']} | "
                f"↓ {format_bps(snapshot['current_recv_bps'])} "
                f"↑ {format_bps(snapshot['current_send_bps'])} | "
                f"🔔 Alertes: {alert_count}"
            )

        except Exception as e:
            self.status_bar.showMessage(f"Erreur: {e}")

    def refresh_tables(self):
        """Rafraîchit tous les tableaux de données."""
        if self._tables_paused:
            return

        try:
            snapshot = self.tracker.get_dashboard_snapshot(include_tables=True)

            # Tableau des connexions
            self._populate_connections(snapshot["connections"])

            # Tableau des processus
            self._populate_processes(snapshot["processes"])

            # Tableau des appareils
            self._populate_devices(snapshot["devices"])

        except Exception as e:
            pass

    def _populate_connections(self, connections):
        """Remplit le tableau des connexions."""
        self.conn_table.setSortingEnabled(False)
        self.conn_table.setRowCount(0)

        # Appliquer les filtres
        proto = self.proto_filter.currentText()
        state = self.state_filter.currentText()
        service = self.service_filter.currentText()
        text_filter = self.conn_filter.text().strip().lower()
        suspicious_only = self.suspicious_only.isChecked()

        filtered = []
        for conn in connections:
            # Filtre protocole
            if proto != "Tous" and conn["protocol"] != proto:
                continue
            # Filtre état
            if state != "Tous" and conn["status"] != state:
                continue
            # Filtre service
            if service != "Tous" and conn.get("service", "Autre") != service:
                continue
            # Filtre suspect
            if suspicious_only and not conn.get("is_suspicious", False):
                continue
            # Filtre texte
            if text_filter:
                match = False
                for val in conn.values():
                    if text_filter in str(val).lower():
                        match = True
                        break
                if not match:
                    continue
            filtered.append(conn)

        # Limiter le nombre de lignes
        for conn in filtered[:MAX_TABLE_ROWS]:
            row = self.conn_table.rowCount()
            self.conn_table.insertRow(row)

            # Indicateur suspect
            is_suspicious = conn.get("is_suspicious", False)
            suspect_item = QTableWidgetItem("⚠️" if is_suspicious else "")
            if is_suspicious:
                suspect_item.setForeground(QColor("#FF4444"))
                suspect_item.setToolTip("Connexion suspecte détectée!")
            self.conn_table.setItem(row, 0, suspect_item)

            # Service (HTTP, HTTPS, etc.)
            svc = conn.get("service", "Autre")
            service_item = QTableWidgetItem(svc)
            if svc in ("HTTP", "HTTP-Proxy"):
                service_item.setForeground(QColor("#FFD166"))
            elif svc in ("HTTPS", "HTTPS-Alt"):
                service_item.setForeground(QColor("#00F5D4"))
            elif svc == "SSH":
                service_item.setForeground(QColor("#FF823C"))
            elif svc == "DNS":
                service_item.setForeground(QColor("#38B000"))
            else:
                service_item.setForeground(QColor("#8899aa"))
            self.conn_table.setItem(row, 1, service_item)

            # Protocole avec indicateur visuel
            proto_item = QTableWidgetItem(conn["protocol"])
            if conn["protocol"] == "TCP":
                proto_item.setForeground(QColor("#00B4D8"))
            else:
                proto_item.setForeground(QColor("#FF823C"))
            self.conn_table.setItem(row, 2, proto_item)

            # PID
            self.conn_table.setItem(row, 3, QTableWidgetItem(str(conn["pid"])))

            # Processus
            name_item = QTableWidgetItem(conn["name"])
            name_item.setForeground(QColor("#9B5DE5"))
            self.conn_table.setItem(row, 4, name_item)

            # Local
            self.conn_table.setItem(row, 5, QTableWidgetItem(conn["local"]))

            # Distant
            remote_item = QTableWidgetItem(conn["remote"] if conn["remote"] else "-")
            if conn["remote"]:
                remote_item.setForeground(QColor("#F15BB5"))
            self.conn_table.setItem(row, 6, remote_item)

            # État avec indicateur de couleur
            status_item = QTableWidgetItem(conn["status"])
            if conn["status"] == "ESTABLISHED":
                status_item.setForeground(QColor("#38B000"))
            elif conn["status"] == "LISTEN":
                status_item.setForeground(QColor("#FFD166"))
            elif conn["status"] in ("TIME_WAIT", "CLOSE_WAIT"):
                status_item.setForeground(QColor("#FF823C"))
            self.conn_table.setItem(row, 7, status_item)

            # Télécharger/Envoyer
            download_bps = conn.get("estimated_download_bps", 0)
            upload_bps = conn.get("estimated_upload_bps", 0)
            
            if download_bps and download_bps > 0.5:
                dl_text = format_bps(download_bps)
                dl_color = QColor("#00B4D8")
            else:
                dl_text = "< 1 B/s"
                dl_color = QColor("#556677")
            
            if upload_bps and upload_bps > 0.5:
                ul_text = format_bps(upload_bps)
                ul_color = QColor("#FF823C")
            else:
                ul_text = "< 1 B/s"
                ul_color = QColor("#556677")
            
            dl_item = QTableWidgetItem(dl_text)
            dl_item.setForeground(dl_color)
            self.conn_table.setItem(row, 8, dl_item)
            
            ul_item = QTableWidgetItem(ul_text)
            ul_item.setForeground(ul_color)
            self.conn_table.setItem(row, 9, ul_item)

        if len(filtered) > MAX_TABLE_ROWS:
            self.status_bar.showMessage(f"Affichage de {MAX_TABLE_ROWS}/{len(filtered)} connexions (filtrage actif)")

        self.conn_table.setSortingEnabled(True)

    def _populate_processes(self, processes):
        """Remplit le tableau des processus."""
        self.process_table.setSortingEnabled(False)
        self.process_table.setRowCount(0)

        text_filter = self.process_filter.text().strip().lower()
        sorted_procs = sorted(processes, key=lambda p: p.get("connections", 0), reverse=True)

        for proc in sorted_procs:
            if text_filter and text_filter not in str(proc.get("name", "")).lower():
                continue

            row = self.process_table.rowCount()
            self.process_table.insertRow(row)

            pid_item = QTableWidgetItem(str(proc["pid"]))
            pid_item.setForeground(QColor("#8899aa"))
            self.process_table.setItem(row, 0, pid_item)

            name_item = QTableWidgetItem(proc["name"])
            name_item.setForeground(QColor("#9B5DE5"))
            self.process_table.setItem(row, 1, name_item)

            conn_item = NumericTableItem(str(proc["connections"]), proc["connections"])
            conn_item.setForeground(QColor("#00B4D8"))
            self.process_table.setItem(row, 2, conn_item)

            est_item = NumericTableItem(str(proc.get("established", 0)), proc.get("established", 0))
            est_item.setForeground(QColor("#38B000"))
            self.process_table.setItem(row, 3, est_item)

            download = proc.get("download_bps")
            download_str = format_bps(download) if download is not None else "-"
            dl_item = QTableWidgetItem(download_str)
            dl_item.setForeground(QColor("#00B4D8"))
            self.process_table.setItem(row, 4, dl_item)

            upload = proc.get("upload_bps")
            upload_str = format_bps(upload) if upload is not None else "-"
            ul_item = QTableWidgetItem(upload_str)
            ul_item.setForeground(QColor("#FF823C"))
            self.process_table.setItem(row, 5, ul_item)

            total_sent = proc.get("total_sent", 0) or 0
            total_recv = proc.get("total_recv", 0) or 0
            total_str = f"↓{format_bytes(total_recv)} ↑{format_bytes(total_sent)}"
            total_item = QTableWidgetItem(total_str)
            total_item.setForeground(QColor("#FFD166"))
            self.process_table.setItem(row, 6, total_item)

        self.process_table.setSortingEnabled(True)

    def _populate_devices(self, devices):
        """Remplit le tableau des appareils."""
        self.device_table.setRowCount(0)

        for ip in devices:
            row = self.device_table.rowCount()
            self.device_table.insertRow(row)

            ip_item = QTableWidgetItem(ip)
            ip_item.setForeground(QColor("#00B4D8"))
            self.device_table.setItem(row, 0, ip_item)

            try:
                ip_obj = ipaddress.ip_address(ip)
                dev_type = "Local/LAN" if ip_obj.is_private else "Externe"
            except:
                dev_type = "Inconnu"

            type_item = QTableWidgetItem(dev_type)
            type_item.setForeground(QColor("#9B5DE5"))
            self.device_table.setItem(row, 1, type_item)

            last_seen = self.tracker._device_last_seen.get(ip, 0)
            ago = time.time() - last_seen
            if ago < 60:
                activity = f"Il y a {int(ago)}s"
            elif ago < 3600:
                activity = f"Il y a {int(ago/60)}min"
            else:
                activity = f"Il y a {int(ago/3600)}h"

            activity_item = QTableWidgetItem(activity)
            activity_item.setForeground(QColor("#8899aa"))
            self.device_table.setItem(row, 2, activity_item)

            status = "● Actif" if ago < 60 else "○ Inactif"
            status_item = QTableWidgetItem(status)
            status_item.setForeground(QColor("#38B000") if ago < 60 else QColor("#FF823C"))
            self.device_table.setItem(row, 3, status_item)

    def _request_table_refresh(self):
        """Demande un rafraîchissement des tableaux."""
        self.filter_timer.start(300)

    def _tick_table_refresh(self):
        """Rafraîchissement périodique des tableaux."""
        self._table_tick_counter += 1
        if self._table_tick_counter >= 3:
            self._table_tick_counter = 0
            self.refresh_tables()

    def _toggle_pause(self, checked):
        """Active/désactive la pause des tableaux."""
        self._tables_paused = checked
        if checked:
            self.btn_pause.setText("▶ Reprendre")
            self.status_bar.showMessage("⏸ Tableaux en pause")
        else:
            self.btn_pause.setText("⏸ Pause")
            self.refresh_tables()

    def _start_monitoring(self):
        """Démarre la surveillance réseau."""
        if not self.worker.isRunning():
            self.worker.start()
            self.status_bar.showMessage("▶ Surveillance réseau démarrée")
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)

    def _stop_monitoring(self):
        """Arrête la surveillance réseau."""
        if self.worker.isRunning():
            self.tracker.stop()
            self.worker.wait(3000)
            self.status_bar.showMessage("⏹ Surveillance réseau arrêtée")
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)

    def _on_alert(self, alert):
        """Callback pour les alertes."""
        # Afficher une notification dans la tray si configuré
        pass

    def _export_data(self):
        """Exporte les données actuelles."""
        try:
            snapshot = self.tracker.get_dashboard_snapshot(include_tables=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"network_scan_{timestamp}.txt"

            with open(filename, "w", encoding="utf-8") as f:
                f.write("=" * 80 + "\n")
                f.write("RAPPORT DE SURVEILLANCE RÉSEAU\n")
                f.write(f"Généré le: {time.strftime('%d/%m/%Y à %H:%M:%S')}\n")
                f.write("=" * 80 + "\n\n")

                f.write("📊 STATISTIQUES GÉNÉRALES\n")
                f.write("-" * 40 + "\n")
                f.write(f"Interface: {snapshot['interface_ip']} ({snapshot['interface_name']})\n")
                f.write(f"Connexions actives: {snapshot['connection_count']}\n")
                f.write(f"  - Établies: {snapshot['established_count']}\n")
                f.write(f"  - En écoute: {snapshot['listening_count']}\n")
                f.write(f"Processus réseau: {len(snapshot['processes'])}\n")
                f.write(f"Appareils détectés: {snapshot['device_count']}\n")
                f.write(f"Pairs connectés: {snapshot['peer_count']}\n")
                f.write(f"Trafic total envoyé: {format_bytes(snapshot['total_sent'])}\n")
                f.write(f"Trafic total reçu: {format_bytes(snapshot['total_recv'])}\n")
                f.write(f"Débit descendant actuel: {format_bps(snapshot['current_recv_bps'])}\n")
                f.write(f"Débit montant actuel: {format_bps(snapshot['current_send_bps'])}\n\n")

                f.write("🔗 CONNEXIONS ACTIVES\n")
                f.write("-" * 40 + "\n")
                for conn in snapshot["connections"][:50]:
                    suspicious = " [SUSPECT]" if conn.get("is_suspicious") else ""
                    f.write(f"[{conn['protocol']}] {conn['local']:25} <-> {conn['remote']:25} "
                           f"État: {conn['status']} PID: {conn['pid']} ({conn['name']}){suspicious}\n")

                f.write(f"\n⚙️ PROCESSUS RÉSEAU\n")
                f.write("-" * 40 + "\n")
                for proc in snapshot["processes"][:30]:
                    f.write(f"PID {proc['pid']:6} | {proc['name']:25} | "
                           f"Connexions: {proc['connections']} | "
                           f"Download: {format_bps(proc.get('download_bps', 0) or 0)} | "
                           f"Upload: {format_bps(proc.get('upload_bps', 0) or 0)}\n")

                f.write(f"\n🖥️ APPAREILS DÉTECTÉS\n")
                f.write("-" * 40 + "\n")
                for ip in snapshot["devices"][:30]:
                    f.write(f"  {ip}\n")

                f.write(f"\n🔔 ALERTES RÉCENTES\n")
                f.write("-" * 40 + "\n")
                for alert in list(self.tracker.alert_manager.alert_history)[-20:]:
                    f.write(f"[{alert.get('severity', 'info').upper()}] {alert.get('message', '')}\n")

            self.status_bar.showMessage(f"✅ Rapport exporté vers {filename}")
            QMessageBox.information(self, "Export réussi",
                                   f"Les données ont été exportées vers:\n{filename}")

        except Exception as e:
            QMessageBox.critical(self, "Erreur d'export",
                                f"Impossible d'exporter les données:\n{e}")

    def _export_csv(self):
        """Exporte les données en CSV."""
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename, _ = QFileDialog.getSaveFileName(self, "Exporter CSV", f"network_{timestamp}.csv", "CSV Files (*.csv)")
            if not filename:
                return

            snapshot = self.tracker.get_dashboard_snapshot(include_tables=True)

            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # En-tête
                writer.writerow(["Network Monitor Pro - Rapport"])
                writer.writerow([f"Généré le: {time.strftime('%d/%m/%Y %H:%M:%S')}"])
                writer.writerow([])
                
                # Statistiques
                writer.writerow(["Statistiques"])
                writer.writerow(["Interface", snapshot['interface_ip']])
                writer.writerow(["Connexions", snapshot['connection_count']])
                writer.writerow(["Établies", snapshot['established_count']])
                writer.writerow(["Processus", len(snapshot['processes'])])
                writer.writerow(["Download", format_bps(snapshot['current_recv_bps'])])
                writer.writerow(["Upload", format_bps(snapshot['current_send_bps'])])
                writer.writerow([])
                
                # Connexions
                writer.writerow(["Connexions"])
                writer.writerow(["Suspect", "Service", "Protocol", "PID", "Process", "Local", "Remote", "Status", "Download", "Upload"])
                for conn in snapshot["connections"][:100]:
                    writer.writerow([
                        "Yes" if conn.get("is_suspicious") else "No",
                        conn.get("service", ""),
                        conn["protocol"],
                        conn["pid"],
                        conn["name"],
                        conn["local"],
                        conn["remote"],
                        conn["status"],
                        format_bps(conn.get("estimated_download_bps", 0)),
                        format_bps(conn.get("estimated_upload_bps", 0)),
                    ])

            self.status_bar.showMessage(f"✅ Export CSV vers {filename}")
            QMessageBox.information(self, "Export CSV réussi", f"Données exportées vers:\n{filename}")

        except Exception as e:
            QMessageBox.critical(self, "Erreur d'export CSV", f"Impossible d'exporter:\n{e}")

    def _show_alerts(self):
        """Affiche la fenêtre des alertes."""
        alerts = list(self.tracker.alert_manager.alert_history)
        if not alerts:
            QMessageBox.information(self, "Alertes", "Aucune alerte récente.")
            return

        dialog = QMessageBox(self)
        dialog.setWindowTitle("🔔 Alertes Récentes")
        
        alert_text = f"Dernières {len(alerts)} alertes:\n\n"
        for i, alert in enumerate(alerts[-20:], 1):
            severity = alert.get("severity", "info").upper()
            alert_text += f"{i}. [{severity}] {alert.get('message', '')}\n"
            if alert.get('details'):
                alert_text += f"   → {alert['details']}\n"
        
        dialog.setText(alert_text)
        dialog.exec()

    def _show_history(self):
        """Affiche l'historique."""
        try:
            history = self.tracker.history_db.get_traffic_history(hours=24)
            if not history:
                QMessageBox.information(self, "Historique", "Pas assez de données historiques.")
                return

            dialog = QMessageBox(self)
            dialog.setWindowTitle("📈 Historique (24h)")
            
            text = "Historique du trafic (dernières 24h):\n\n"
            text += f"{'Heure':<20} {'Download':<15} {'Upload':<15} {'Connexions':<10}\n"
            text += "-" * 60 + "\n"
            
            for entry in history[-20:]:
                ts = datetime.fromtimestamp(entry["timestamp"]).strftime("%H:%M:%S")
                text += f"{ts:<20} {format_bps(entry['download_bps']):<15} {format_bps(entry['upload_bps']):<15} {entry['connection_count']:<10}\n"
            
            dialog.setText(text)
            dialog.exec()

        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de charger l'historique:\n{e}")

    def _show_top_processes(self):
        """Affiche le top 10 des processus."""
        try:
            top = self.tracker.history_db.get_top_processes(hours=1, limit=10)
            if not top:
                QMessageBox.information(self, "Top 10", "Pas assez de données.")
                return

            dialog = QMessageBox(self)
            dialog.setWindowTitle("🏆 Top 10 Processus (1h)")
            
            text = "Top 10 des processus les plus gourmands (dernière heure):\n\n"
            text += f"{'#':<3} {'Processus':<25} {'PID':<8} {'Total':<15} {'Connexions':<10}\n"
            text += "-" * 61 + "\n"
            
            for i, proc in enumerate(top, 1):
                total = proc["total_upload"] + proc["total_download"]
                text += f"{i:<3} {proc['name'][:24]:<25} {proc['pid']:<8} {format_bps(total):<15} {proc['connections']:<10}\n"
            
            dialog.setText(text)
            dialog.exec()

        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de charger le top 10:\n{e}")

    def _show_firewall(self):
        """Affiche l'interface de gestion du firewall."""
        dialog = QMessageBox(self)
        dialog.setWindowTitle("🛡️ Gestion du Firewall")
        
        # Récupérer les connexions suspectes
        snapshot = self.tracker.get_dashboard_snapshot(include_tables=True)
        suspicious_conns = [c for c in snapshot["connections"] if c.get("is_suspicious", False)]
        
        text = "🛡️ GESTION DU FIREWALL\n\n"
        text += "=" * 50 + "\n\n"
        
        if suspicious_conns:
            text += f"⚠️ {len(suspicious_conns)} connexion(s) suspecte(s) détectée(s):\n\n"
            for i, conn in enumerate(suspicious_conns, 1):
                text += f"{i}. {conn.get('remote_ip', 'N/A')}:{conn.get('remote', '').split(':')[-1] or 'N/A'}\n"
                text += f"   Processus: {conn.get('name', 'unknown')} (PID: {conn.get('pid', '?')})\n"
                text += f"   Service: {conn.get('service', 'unknown')}\n\n"
            
            text += "\n📋 ACTIONS DISPONIBLES:\n"
            text += "  • Bloquer une IP suspecte\n"
            text += "  • Fermer une connexion suspecte\n"
            text += "  • Ajouter à la liste blanche\n"
            text += "  • Exporter la liste noire\n\n"
            
            text += "⚠️ NOTE: Pour des raisons de sécurité, les actions de blocage\n"
            text += "nécessitent des privilèges administrateur. Utilisez les\n"
            text += "commandes Windows Firewall ou un outil dédié.\n\n"
            
            text += "📖 GUIDE RAPIDE:\n"
            text += "1. Ouvrez Windows Firewall (panneau de configuration)\n"
            text += "2. Allez dans 'Règles de trafic entrant/sortant'\n"
            text += "3. Créez une nouvelle règle pour bloquer l'IP\n"
            text += "4. Sélectionnez 'Bloquer la connexion'\n"
        else:
            text += "✅ Aucune connexion suspecte détectée!\n\n"
            text += "Le réseau semble sûr pour le moment.\n\n"
        
        text += "\n🔧 COMMANDES UTILES (à exécuter en admin):\n"
        text += "  • netsh advfirewall firewall add rule name=\"Block IP\" dir=out action=block remoteip=X.X.X.X\n"
        text += "  • netstat -ano | findstr :PORT (pour voir les connexions)\n"
        
        dialog.setText(text)
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.exec()

    def _show_network_map(self):
        """Affiche une visualisation de la carte réseau."""
        dialog = QMessageBox(self)
        dialog.setWindowTitle("🗺️ Carte Réseau Interactive")
        
        snapshot = self.tracker.get_dashboard_snapshot(include_tables=True)
        
        text = "🗺️ CARTE RÉSEAU INTERACTIVE\n\n"
        text += "=" * 50 + "\n\n"
        
        # Informations sur l'interface locale
        text += f"🖥️ VOTRE INTERFACE:\n"
        text += f"  IP Locale: {snapshot['interface_ip']}\n"
        text += f"  Interface: {snapshot['interface_name']}\n"
        text += f"  Écoute sur: {snapshot['listening']}\n\n"
        
        # Appareils locaux détectés
        text += f"📱 APPAREILS SUR LE RÉSEAU LOCAL ({snapshot['device_count']} détectés):\n"
        if snapshot['devices']:
            for i, device_ip in enumerate(snapshot['devices'][:10], 1):
                try:
                    ip_obj = ipaddress.ip_address(device_ip)
                    dev_type = "🏠 Local" if ip_obj.is_private else "🌍 Externe"
                except:
                    dev_type = "❓ Inconnu"
                text += f"  {i}. {dev_type} {device_ip}\n"
            if len(snapshot['devices']) > 10:
                text += f"  ... et {len(snapshot['devices']) - 10} autres\n"
        else:
            text += "  Aucun appareil détecté pour le moment\n"
        
        text += "\n🔗 CONNEXIONS ACTIVES PAR TYPE:\n"
        services = {}
        for conn in snapshot["connections"]:
            svc = conn.get("service", "Autre")
            services[svc] = services.get(svc, 0) + 1
        
        for svc, count in sorted(services.items(), key=lambda x: x[1], reverse=True):
            icon = {"HTTP": "🌐", "HTTPS": "🔒", "SSH": "🔑", "DNS": "📡", "FTP": "📁", 
                   "SMTP": "📧", "RDP": "🖥️", "Autre": "📶"}.get(svc, "📶")
            text += f"  {icon} {svc}: {count} connexion(s)\n"
        
        text += "\n📊 STATISTIQUES DE TRAFIC:\n"
        text += f"  ↓ Download actuel: {format_bps(snapshot['current_recv_bps'])}\n"
        text += f"  ↑ Upload actuel: {format_bps(snapshot['current_send_bps'])}\n"
        text += f"  📈 Pic download: {format_bps(snapshot['peak_recv_bps'])}\n"
        text += f"  📈 Pic upload: {format_bps(snapshot['peak_send_bps'])}\n"
        
        text += "\n\n💡 Cette vue donne un aperçu de votre réseau.\n"
        text += "Pour une carte graphique interactive, un module de visualisation\n"
        text += "avancé serait nécessaire (nécessite des bibliothèques supplémentaires).\n"
        
        dialog.setText(text)
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.exec()

    def _show_about(self):
        """Affiche la fenêtre À propos."""
        about_text = f"""
        <div style="text-align: center; font-family: 'Segoe UI', sans-serif;">
            <h2 style="color: #00B4D8; margin-bottom: 5px;">🌐 Network Monitor Pro</h2>
            <h3 style="color: #8899aa; font-size: 14px; margin-top: 0;">{__description__}</h3>
            
            <div style="background-color: #0d1525; padding: 15px; border-radius: 10px; margin: 10px 0;">
                <p style="color: #e0e8f5; margin: 5px 0;"><b>Version:</b> {__version__}</p>
                <p style="color: #e0e8f5; margin: 5px 0;"><b>Développé par:</b> {__author__}</p>
                <p style="color: #e0e8f5; margin: 5px 0;"><b>Site web:</b> <a href="{__website__}" style="color: #00B4D8;">{__website__}</a></p>
                <p style="color: #e0e8f5; margin: 5px 0;"><b>Email:</b> <a href="mailto:{__email__}" style="color: #00B4D8;">{__email__}</a></p>
                <p style="color: #e0e8f5; margin: 5px 0;"><b>Licence:</b> {__license__}</p>
            </div>
            
            <p style="color: #667788; font-size: 11px;">{__copyright__}</p>
            
            <div style="margin-top: 15px;">
                <p style="color: #8899aa; font-size: 12px;">
                    🛡️ Analyseur de trafic réseau en temps réel<br>
                    📊 Surveillance des connexions et processus<br>
                    🔔 Détection d'intrusions et alertes<br>
                    📈 Historique et statistiques avancées
                </p>
            </div>
        </div>
        """
        
        dialog = QMessageBox(self)
        dialog.setWindowTitle("ℹ️ À propos de Network Monitor Pro")
        dialog.setTextFormat(Qt.TextFormat.RichText)
        dialog.setText(about_text)
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.exec()

    def closeEvent(self, event):
        """Gère la fermeture de la fenêtre."""
        self.tracker.stop()
        if self.worker.isRunning():
            self.worker.wait(3000)
        event.accept()