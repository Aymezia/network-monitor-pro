# 🌐 Network Monitor Pro

<div align="center">

![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.8%2B-yellow.svg)
![PyQt](https://img.shields.io/badge/PyQt-6-blue.svg)

**Analyseur de Trafic Réseau Ultra-Complet**

[![Aymezia](https://img.shields.io/badge/Developed%20by-Aymezia-purple.svg)](https://Aymezia.cc)

</div>

---

## 📋 Description

Network Monitor Pro est une application de surveillance réseau complète développée en Python avec PyQt6. Elle offre une interface graphique moderne et intuitive pour analyser en temps réel le trafic réseau, surveiller les connexions actives, détecter les intrusions et gérer les alertes de sécurité.

## ✨ Fonctionnalités

### 🛡️ Surveillance en Temps Réel
- **Analyse du trafic** : Suivi des débits upload/download en temps réel
- **Connexions actives** : Visualisation de toutes les connexions réseau (TCP/UDP)
- **Processus réseau** : Identification des processus utilisant le réseau
- **Appareils détectés** : Détection des appareils sur le réseau local

### 📊 Tableau de Bord Complet
- **Cartes de métriques** : Affichage des statistiques clés
- **Graphique de trafic** : Courbes d'évolution du trafic avec effet de lueur
- **Tableaux filtrables** : Connexions, processus et appareils avec filtres avancés

### 🔔 Système d'Alertes
- **Détection d'intrusions** : Identification des IPs et ports suspects
- **Alertes de bande passante** : Notification en cas de trafic élevé
- **Surveillance des connexions** : Alerte en cas de nombre anormal de connexions

### 📈 Historique et Statistiques
- **Base de données SQLite** : Stockage de l'historique des données
- **Rapports exportables** : Export en TXT et CSV
- **Top des processus** : Identification des plus gros consommateurs

### 🗺️ Outils Avancés
- **Carte réseau** : Visualisation des appareils connectés
- **Gestion Firewall** : Guide pour bloquer les IPs suspectes
- **Analyse par service** : Classification HTTP, HTTPS, SSH, DNS, etc.

## 🚀 Installation

### Prérequis
- Python 3.8 ou supérieur
- PyQt6
- psutil

### Installation Automatique

```bash
# Cloner le dépôt
git clone https://github.com/Aymezia/network-monitor-pro.git
cd network-monitor-pro

# Installer les dépendances
pip install PyQt6 psutil
```

### Installation Manuelle

1. Téléchargez le code source
2. Installez Python 3.8+ depuis [python.org](https://www.python.org/)
3. Ouvrez un terminal et exécutez :
```bash
pip install PyQt6 psutil
```

## 📖 Utilisation

### Lancement de l'Application

```bash
# Depuis le dossier du projet
python network.py
```

### Interface Principale

1. **Barre d'outils** :
   - ▶ **Démarrer** : Lance la surveillance réseau
   - ⏹ **Arrêter** : Arrête la surveillance
   - 📊 **Exporter** : Exporte les données en TXT
   - 📄 **Export CSV** : Exporte les données en CSV
   - ⏸ **Pause** : Met en pause les tableaux
   - 🔔 **Alertes** : Affiche les alertes récentes
   - 📈 **Historique** : Affiche l'historique (24h)
   - 🏆 **Top 10** : Les processus les plus gourmands
   - 🛡️ **Firewall** : Guide de gestion du firewall
   - 🗺️ **Carte Réseau** : Visualisation des appareils
   - ℹ️ **À propos** : Informations sur l'application

2. **Tableau de Bord** :
   - Débit Descendant/Montant avec pics
   - Connexions actives (établies/en écoute)
   - Nombre de processus et d'appareils
   - Pairs connectés et alertes

3. **Onglets** :
   - 🔗 **Connexions** : Liste détaillée avec filtres
   - ⚙️ **Processus** : Statistiques par processus
   - 🖥️ **Appareils** : Appareils sur le réseau local

### Filtres Avancés

- **Protocole** : TCP, UDP ou tous
- **État** : ESTABLISHED, LISTEN, TIME_WAIT, etc.
- **Service** : HTTP, HTTPS, SSH, DNS, FTP, etc.
- **Recherche texte** : Filtrage en temps réel
- **Connexions suspectes** : Filtre dédié

## 🏗️ Architecture du Projet

```
network_monitor/
├── __init__.py          # Métadonnées et version
├── main.py              # Point d'entrée principal
├── config.py            # Configuration et constantes
├── utils.py             # Fonctions utilitaires
├── database.py          # Gestion de la base de données
├── alerts.py            # Gestionnaire d'alertes
├── widgets.py           # Composants UI personnalisés
├── tracker.py           # Moteur de surveillance réseau
└── window.py            # Fenêtre principale

network.py               # Script de lancement
```

## 🔧 Configuration

### Fichier de Configuration

Les paramètres sont définis dans `network_monitor/config.py` :

```python
# IPs suspectes pour la détection d'intrusion
SUSPICIOUS_IP_RANGES = [
    "185.220.101.",  # Tor exit nodes
    "23.129.64.",    # Tor exit nodes
    "199.249.230.",  # Known scanners
]

# Ports suspects
SUSPICIOUS_PORTS = [4444, 5555, 6666, 31337, 12345, 54321]

# Seuil d'alerte (10 MB/s par défaut)
DEFAULT_ALERT_THRESHOLD = 10 * 1024 * 1024

# Configuration du serveur
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 18999
DEFAULT_TIMEOUT = 120
```

## 🛠️ Développement

### Structure du Code

Le projet est modulaire pour faciliter la maintenance :

- **`tracker.py`** : Cœur du système, gère la surveillance réseau
- **`window.py`** : Interface graphique PyQt6
- **`widgets.py`** : Composants UI personnalisés (graphiques, cartes)
- **`database.py`** : Persistance des données avec SQLite
- **`alerts.py`** : Système de détection et notification
- **`utils.py`** : Fonctions de formatage et utilitaires
- **`config.py`** : Constantes et configuration

### Ajouter de Nouvelles Fonctionnalités

1. **Nouvelle métrique** : Modifier `tracker.py` et `window.py`
2. **Nouveau filtre** : Ajouter dans `window.py` → `_populate_connections()`
3. **Nouvelle alerte** : Modifier `alerts.py` → `check_alerts()`


## 👤 Auteur

**Aymezia**
- 🌐 Site web : [https://Aymezia.cc](https://Aymezia.cc)
- 📧 Email : contact@aymezia.cc


## 🐛 Signaler un Bug

Si vous rencontrez un bug, veuillez ouvrir une issue en incluant :
- La description du bug
- Les étapes pour reproduire
- Le comportement attendu
- Les captures d'écran si nécessaire

## 📝 Changelog

### Version 1.0.0
- ✨ Première version stable
- 🎨 Interface graphique moderne avec thème sombre
- 🛡️ Surveillance réseau complète en temps réel
- 📊 Tableau de bord avec graphiques animés
- 🔔 Système d'alertes intelligent
- 📈 Historique et export des données
- 🗺️ Carte réseau interactive

## 🙏 Remerciements

- PyQt6 pour l'excellent framework GUI
- psutil pour les utilitaires système
- La communauté open-source

---

<div align="center">

**Network Monitor Pro** - Développé avec ❤️ par [Aymezia](https://Aymezia.cc)

⭐ N'oubliez pas d'étoiler ce dépôt si vous l'aimez ! ⭐

</div>
