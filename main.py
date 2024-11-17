import sys
import os
import asyncio
import json
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QLineEdit, QTextEdit, QPushButton, 
                            QSpinBox, QTabWidget, QFileDialog, QMessageBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from gpt_crawler_core import GPTCrawler, logger
import logging

class CrawlerThread(QThread):
    output_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.crawler = GPTCrawler()

    def run(self):
        try:
            # Create custom handler to redirect logs to GUI
            class QTextEditHandler(logging.Handler):
                def __init__(self, signal):
                    super().__init__()
                    self.signal = signal

                def emit(self, record):
                    msg = self.format(record)
                    self.signal.emit(msg)

            # Add handler to logger
            handler = QTextEditHandler(self.output_signal)
            handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            logger.addHandler(handler)

            # Run crawler
            asyncio.run(self.crawler.crawl(**self.config))
        except Exception as e:
            self.output_signal.emit(f"Error: {str(e)}")
            import traceback
            self.output_signal.emit(f"Traceback: {traceback.format_exc()}")
        finally:
            logger.removeHandler(handler)
            self.finished_signal.emit()

    def stop(self):
        if self.crawler:
            self.crawler.stop()

class CrawlerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Web Crawler Dashboard")
        self.setMinimumSize(1000, 700)
        
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        # Create tabs
        tabs = QTabWidget()
        layout.addWidget(tabs)
        
        # Configuration tab
        config_tab = QWidget()
        config_layout = QVBoxLayout(config_tab)
        
        # URL Configuration
        self.start_url = QLineEdit()
        self.start_url.setPlaceholderText("Enter starting URL (e.g., https://example.com/docs/section1)")
        config_layout.addWidget(QLabel("Start URL:"))
        config_layout.addWidget(self.start_url)
        
        self.url_pattern = QLineEdit()
        self.url_pattern.setPlaceholderText("Enter URL pattern (e.g., https://example.com/docs/)")
        config_layout.addWidget(QLabel("URL Pattern (pages to crawl must start with this):"))
        config_layout.addWidget(self.url_pattern)
        
        # Output File Configuration
        output_layout = QHBoxLayout()
        self.output_path = QLineEdit()
        default_output_path = os.path.join(os.path.expanduser("~"), "Desktop", "crawler_output.json")
        self.output_path.setText(default_output_path)
        output_button = QPushButton("Browse")
        output_button.clicked.connect(self.browse_output_path)
        output_layout.addWidget(QLabel("Output File:"))
        output_layout.addWidget(self.output_path)
        output_layout.addWidget(output_button)
        config_layout.addLayout(output_layout)
        
        # Advanced Settings
        config_layout.addWidget(QLabel("Advanced Settings:"))
        
        # Selector Settings
        self.selector = QLineEdit()
        self.selector.setPlaceholderText("CSS Selector (e.g., 'main')")
        config_layout.addWidget(QLabel("CSS Selector:"))
        config_layout.addWidget(self.selector)
        
        # Max Pages
        max_pages_layout = QHBoxLayout()
        self.max_pages = QSpinBox()
        self.max_pages.setRange(1, 1000)
        self.max_pages.setValue(10)
        max_pages_layout.addWidget(QLabel("Max Pages:"))
        max_pages_layout.addWidget(self.max_pages)
        max_pages_layout.addStretch()
        config_layout.addLayout(max_pages_layout)
        
        # Remove Selectors
        self.remove_selectors = QTextEdit()
        self.remove_selectors.setPlaceholderText("Enter selectors to remove (one per line)")
        self.remove_selectors.setMaximumHeight(100)
        config_layout.addWidget(QLabel("Remove Selectors:"))
        config_layout.addWidget(self.remove_selectors)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Crawler")
        self.start_button.clicked.connect(self.start_crawler)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_crawler)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        config_layout.addLayout(button_layout)
        
        # Output tab
        output_tab = QWidget()
        output_layout = QVBoxLayout(output_tab)
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        output_layout.addWidget(self.output_text)
        
        # Add tabs
        tabs.addTab(config_tab, "Configuration")
        tabs.addTab(output_tab, "Output")
        
        self.crawler_thread = None
        self.load_settings()

    def browse_output_path(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Select Output File Location",
            "",
            "JSON Files (*.json);;All Files (*.*)"
        )
        if file_path:
            if not file_path.endswith('.json'):
                file_path += '.json'
            self.output_path.setText(file_path)
            self.save_settings()

    def load_settings(self):
        try:
            if os.path.exists('settings.json'):
                with open('settings.json', 'r') as f:
                    settings = json.load(f)
                    self.output_path.setText(settings.get('output_path', '') or 
                        os.path.join(os.path.expanduser("~"), "Desktop", "crawler_output.json"))
                    self.url_pattern.setText(settings.get('url_pattern', ''))
                    self.start_url.setText(settings.get('last_start_url', ''))
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load settings: {str(e)}")

    def save_settings(self):
        try:
            settings = {
                'output_path': self.output_path.text(),
                'url_pattern': self.url_pattern.text(),
                'last_start_url': self.start_url.text()
            }
            with open('settings.json', 'w') as f:
                json.dump(settings, f)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save settings: {str(e)}")

    def start_crawler(self):
        if not self.start_url.text():
            QMessageBox.warning(self, "Error", "Please enter a starting URL")
            return

        # Prepare crawler configuration
        config = {
            "start_url": self.start_url.text(),
            "url_pattern": self.url_pattern.text(),
            "selector": self.selector.text(),
            "max_pages": self.max_pages.value(),
            "remove_selectors": [s for s in self.remove_selectors.toPlainText().split('\n') if s],
            "output_file": self.output_path.text()
        }

        # Start crawler thread
        self.crawler_thread = CrawlerThread(config)
        self.crawler_thread.output_signal.connect(self.update_output)
        self.crawler_thread.finished_signal.connect(self.crawler_finished)
        self.crawler_thread.start()
        
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

    def update_output(self, text):
        self.output_text.append(text)

    def crawler_finished(self):
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        QMessageBox.information(self, "Complete", "Crawler process has finished!")

    def stop_crawler(self):
        if self.crawler_thread:
            self.crawler_thread.stop()
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.output_text.append("Crawler stopped by user")

def main():
    app = QApplication(sys.argv)
    window = CrawlerGUI()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main() 