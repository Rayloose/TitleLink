import requests
from pythonosc.udp_client import SimpleUDPClient
import sys
import csv
import os
from datetime import datetime
from collections import deque
from PyQt5.QtWidgets import QApplication, QLabel, QWidget
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont, QFontMetrics

url = "http://localhost:17081/params.json"

import time
import requests

HOST = '127.0.0.1'
PORT = 17081
URL = f'http://{HOST}:{PORT}/params.json'
POLL_INTERVAL = 50  # milliseconds for QTimer

# Create log folder if it doesn't exist
LOG_FOLDER = 'master_player_log'
os.makedirs(LOG_FOLDER, exist_ok=True)

# Generate timestamped filename for this session
session_timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
CSV_LOG_FILE = os.path.join(LOG_FOLDER, f'master_player_log_{session_timestamp}.csv')

osc_destination_resolume = "/composition/layers/1/clips/4/video/source/blocktextgenerator/text/params/lines" # layer 1, clip 4
osc_destination_beyond = "/beyond/cue/0/0/text" # first cue of the first page of your workspace
osc_destination = osc_destination_resolume

OSC_IP = "127.0.0.1"   # ordinateur avec Beyond
OSC_PORT = 7000        # port configuré dans Beyond
osc = SimpleUDPClient(OSC_IP, OSC_PORT)

def fetch_params():
    r = requests.get(URL, timeout=5)
    r.raise_for_status()
    return r.json()

class Track:
    def __init__(self, data):
        self.data = data.get('track')
        self.artist = self.data.get('artist')
        self.title = self.data.get('title')
        self.id = self.data.get('id')
        
        self.bpm = data.get('track-bpm')
        self.tempo = data.get('tempo')  # BPM actuel en temps réel

    def display(self):
        if self.tempo and self.bpm:
            bpm_change = ((self.tempo - self.bpm) / self.bpm) * 100
            sign = '+' if bpm_change >= 0 else ''
        return f"{self.title} - {self.artist}   ({self.tempo:.1f} BPM {sign}{bpm_change:.1f}%)"


class Player :
    def __init__(self, player_id, data):
        self.player_id = player_id
        self.data = data
        self.track = Track(data)

    def display(self):
        return f"Player {self.player_id} playing {self.track.display()}"

class PlayerWindow(QWidget):
    def __init__(self, player_id):
        super().__init__()
        self.player_id = player_id
        self.setWindowTitle(f'Player {player_id}')
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        self.resize(1875, 100)
        
        # Set window background to black (title bar and borders)
        self.setStyleSheet('QWidget { background-color: black; }')
        
        self.label = QLabel('No track loaded', self)
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.current_color = 'red'
        self.label.setStyleSheet('background-color: black; color: red; padding: 10px;')
        self.label.setGeometry(0, 0, self.width(), self.height())
        
        self.update_font()
    
    def resizeEvent(self, event):
        self.label.setGeometry(0, 0, self.width(), self.height())
        self.update_font()
        super().resizeEvent(event)
    
    def update_font(self):
        text = self.label.text()
        available_width = self.width() - 50
        available_height = int((self.height() - 50) * 1.6)

        # recherche dichotomique de la taille optimale
        min_size = 8
        max_size = 100
        best_size = min_size
        
        while min_size <= max_size:
            mid_size = (min_size + max_size) // 2
            font = QFont('Arial', mid_size, QFont.Bold)
            metrics = QFontMetrics(font)
            
            text_width = metrics.horizontalAdvance(text)
            text_height = metrics.height()
            
            if text_width <= available_width and text_height <= available_height:
                best_size = mid_size
                min_size = mid_size + 1
            else:
                max_size = mid_size - 1
        
        self.label.setFont(QFont('Arial', best_size, QFont.Bold))
    
    def update_player(self, player, is_master=False):
        player_track = player.track.display()
        if player_track:
            self.label.setText(player_track)
        else:
            self.label.setText('No track loaded')
        
        # Update color based on master status
        new_color = 'green' if is_master else 'red'
        if new_color != self.current_color:
            self.current_color = new_color
            self.label.setStyleSheet(f'background-color: black; color: {new_color}; padding: 10px;')
        
        self.update_font()

class PlayerMonitor:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.windows = {}
        self.players = {}
        self.last_titles = {}
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_all)
        
        # Track master player status
        self.master_status = {}  # pid -> is_master
        self.master_start_times = {}  # pid -> datetime when became master
        self.master_track_info = {}  # pid -> (title, artist, bpm) when became master
        
        # Initialize CSV file with headers if it doesn't exist
        self.init_csv_log()
    
    def determine_genre(self, title, artist):
        # Placeholder logic for determining genre based on title or artist
        # You can replace this with a more sophisticated genre-detection algorithm
        if 'rock' in title.lower() or 'rock' in artist.lower():
            return 'Rock'
        elif 'jazz' in title.lower() or 'jazz' in artist.lower():
            return 'Jazz'
        elif 'pop' in title.lower() or 'pop' in artist.lower():
            return 'Pop'
        elif 'classical' in title.lower() or 'mozart' in artist.lower():
            return 'Classical'
        else:
            return 'Unknown'

    def init_csv_log(self):
        try:
            with open(CSV_LOG_FILE, 'x', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Player ID', 'Title', 'Artist', 'BPM', 'Start Time', 'End Time', 'Duration (seconds)', 'Genre'])
        except FileExistsError:
            pass  # File already exists, no need to create
    
    def log_master_session(self, player_id, title, artist, bpm, start_time, end_time):
        duration = (end_time - start_time).total_seconds()
        genre = self.determine_genre(title, artist)
        with open(CSV_LOG_FILE, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                player_id,
                title,
                artist,
                bpm,
                start_time.strftime('%Y-%m-%d %H:%M:%S.%f'),
                end_time.strftime('%Y-%m-%d %H:%M:%S.%f'),
                f'{duration:.2f}',
                genre
            ])
        print(f'Logged master session: Player {player_id} - {title} by {artist} ({duration:.2f}s, Genre: {genre})')
    
    def start(self):
        print(f'Watching {URL} — Ctrl+C to stop the flow')
        
        try:
            data = fetch_params()
        except Exception as e:
            print(f'Initial fetch error: {e}')
            sys.exit(1)
        
        # initialisation des players et fenêtres
        for pid, player_data in data.get('players', {}).items():
            self.players[pid] = Player(pid, player_data)
            
            window = PlayerWindow(pid)
            window.move(100 + int(pid) * 50, 100 + int(pid) * 50)
            is_master = player_data.get('is-tempo-master', False)
            window.update_player(self.players[pid], is_master)
            window.show()
            self.windows[pid] = window

            self.last_titles[pid] = self.players[pid].track.title
            
            # Initialize master status tracking
            self.master_status[pid] = is_master
            if is_master:
                self.master_start_times[pid] = datetime.now()
                self.master_track_info[pid] = (
                    self.players[pid].track.title,
                    self.players[pid].track.artist,
                    self.players[pid].track.bpm
                )
        
        # player master
        if 'master' in data:
            self.players['master'] = Player('master', data.get('master', {}))
        
        self.timer.start(POLL_INTERVAL)
        sys.exit(self.app.exec_())
            
    def update_all(self):
        try:
            data = fetch_params()
            
            for pid, player_data in data.get('players', {}).items():
                self.players[pid] = Player(pid, player_data)
                
                if pid in self.windows:
                    is_master = player_data.get('is-tempo-master', False)
                    self.windows[pid].update_player(self.players[pid], is_master)

                    self.last_titles[pid] = self.players[pid].track.title
                    
                    # Check for master status change
                    previous_master = self.master_status.get(pid, False)
                    
                    if is_master and not previous_master:
                        # Became master
                        self.master_start_times[pid] = datetime.now()
                        self.master_track_info[pid] = (
                            self.players[pid].track.title,
                            self.players[pid].track.artist,
                            self.players[pid].track.bpm
                        )
                    elif not is_master and previous_master:
                        # Stopped being master
                        if pid in self.master_start_times and pid in self.master_track_info:
                            end_time = datetime.now()
                            title, artist, bpm = self.master_track_info[pid]
                            self.log_master_session(
                                pid,
                                title,
                                artist,
                                bpm,
                                self.master_start_times[pid],
                                end_time
                            )
                    
                    # Update master status
                    self.master_status[pid] = is_master

            # mise à jour master
            if 'master' in data:
                self.players['master'] = Player('master', data.get('master', {}))
                
        except Exception as e:
            print(f'Fetch error: {e}')

if __name__ == '__main__':
    monitor = PlayerMonitor()
    monitor.start()
