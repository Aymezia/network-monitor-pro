"""
Composants d'interface personnalisés pour Network Monitor Pro.
"""

import math

from PyQt6.QtCore import QPointF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QTableWidgetItem, QVBoxLayout, QWidget

from network_monitor.utils import calc_axis_max, format_bps


class NumericTableItem(QTableWidgetItem):
    """Élément de tableau avec tri numérique personnalisé."""
    def __init__(self, text, sort_value):
        super().__init__(text)
        self.sort_value = sort_value

    def __lt__(self, other):
        if isinstance(other, NumericTableItem):
            return self.sort_value < other.sort_value
        return super().__lt__(other)


class ThroughputGraph(QWidget):
    """Graphique de débit réseau avec rendu professionnel."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.samples = []
        self.setMinimumHeight(200)
        self.setMaximumHeight(250)
        self._pulse_phase = 0.0

    def set_series(self, samples):
        self.samples = samples
        self._pulse_phase = (self._pulse_phase + 0.15) % (2 * math.pi)
        self.update()

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Fond avec dégradé
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor(6, 12, 28))
        gradient.setColorAt(0.5, QColor(10, 18, 40))
        gradient.setColorAt(1, QColor(6, 12, 28))
        painter.fillRect(self.rect(), gradient)

        # Bordure
        pen = QPen(QColor(60, 100, 160, 60), 1)
        painter.setPen(pen)
        painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 8, 8)

        plot_area = self.rect().adjusted(60, 15, -15, -30)
        if plot_area.width() < 30 or plot_area.height() < 30:
            return

        # Grille
        grid_pen = QPen(QColor(60, 100, 160, 20), 1, Qt.PenStyle.DashLine)
        painter.setPen(grid_pen)
        for i in range(5):
            y = plot_area.top() + (plot_area.height() * i / 4)
            painter.drawLine(plot_area.left(), int(y), plot_area.right(), int(y))

        if not self.samples:
            painter.setPen(QColor(80, 120, 180, 120))
            font = painter.font()
            font.setPointSize(11)
            painter.setFont(font)
            painter.drawText(plot_area, int(Qt.AlignmentFlag.AlignCenter), "En attente du trafic...")
            return

        max_value = max(max(rx, tx) for rx, tx in self.samples)
        axis_max = calc_axis_max(max_value)

        # Étiquettes Y
        painter.setPen(QColor(120, 160, 220, 180))
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        painter.drawText(2, plot_area.top() + 4, format_bps(int(axis_max)))
        painter.drawText(2, plot_area.center().y(), format_bps(int(axis_max / 2)))
        painter.drawText(2, plot_area.bottom() - 2, "0 B/s")

        # Calcul des points
        rx_points = []
        tx_points = []
        count = len(self.samples)

        for i, (rx, tx) in enumerate(self.samples):
            x = plot_area.left() + (plot_area.width() * i / max(count - 1, 1))
            y_rx = plot_area.bottom() - (rx / axis_max) * plot_area.height()
            y_tx = plot_area.bottom() - (tx / axis_max) * plot_area.height()
            rx_points.append(QPointF(x, y_rx))
            tx_points.append(QPointF(x, y_tx))

        # Dessin des courbes
        download_color = QColor(0, 180, 255)
        upload_color = QColor(255, 130, 60)

        self._draw_curve(painter, rx_points, download_color)
        self._draw_curve(painter, tx_points, upload_color)

        # Légende
        legend_y = self.height() - 12
        painter.setPen(QPen(download_color, 2))
        painter.drawLine(10, legend_y, 25, legend_y)
        painter.setPen(QColor(150, 190, 240, 200))
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(30, legend_y + 3, "↓ Download")

        painter.setPen(QPen(upload_color, 2))
        painter.drawLine(120, legend_y, 135, legend_y)
        painter.setPen(QColor(150, 190, 240, 200))
        painter.drawText(140, legend_y + 3, "↑ Upload")

    def _draw_curve(self, painter, points, color):
        if len(points) < 2:
            return

        # Effet de lueur
        for glow_size in [8, 5, 3]:
            glow_color = QColor(color)
            glow_color.setAlpha(30 - glow_size * 3)
            if glow_color.alpha() <= 0:
                continue
            painter.setPen(QPen(glow_color, 2 + glow_size * 2, Qt.PenStyle.SolidLine,
                               Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            path = QPainterPath()
            path.moveTo(points[0])
            for i in range(1, len(points)):
                path.lineTo(points[i])
            painter.drawPath(path)

        # Ligne principale
        painter.setPen(QPen(color, 2.5, Qt.PenStyle.SolidLine,
                           Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        path = QPainterPath()
        path.moveTo(points[0])
        for i in range(1, len(points)):
            path.lineTo(points[i])
        painter.drawPath(path)

        # Point final pulsant
        if points:
            pulse = 4 + math.sin(self._pulse_phase) * 2
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(points[-1], int(pulse), int(pulse))


class MetricCard(QFrame):
    """Carte de métrique avec design moderne."""
    def __init__(self, title, value="", icon="📊", accent_color="#00B4D8", parent=None):
        super().__init__(parent)
        self.setObjectName("metricCard")
        self.setFixedHeight(100)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(12)

        # Barre d'accent colorée
        accent_bar = QFrame()
        accent_bar.setFixedWidth(4)
        accent_bar.setStyleSheet(f"background-color: {accent_color}; border-radius: 2px;")
        layout.addWidget(accent_bar)

        # Icône
        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 28px; padding: 5px;")
        layout.addWidget(icon_label)

        # Informations
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("""
            color: #8899aa;
            font-size: 11px;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        """)
        info_layout.addWidget(self.title_label)

        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(f"""
            color: {accent_color};
            font-size: 22px;
            font-weight: 700;
        """)
        info_layout.addWidget(self.value_label)

        self.meta_label = QLabel("")
        self.meta_label.setStyleSheet("color: #667788; font-size: 10px;")
        info_layout.addWidget(self.meta_label)

        info_layout.addStretch()
        layout.addLayout(info_layout)

        self.setStyleSheet("""
            #metricCard {
                background-color: #0d1525;
                border: 1px solid #1a2a4a;
                border-radius: 10px;
            }
            #metricCard:hover {
                border-color: #2a4a7a;
                background-color: #0f1a2e;
            }
        """)

    def set_value(self, value):
        self.value_label.setText(str(value))

    def set_meta(self, meta):
        self.meta_label.setText(str(meta))