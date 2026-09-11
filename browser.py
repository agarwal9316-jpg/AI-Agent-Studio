import sys
from PyQt5.QtCore import QUrl
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import QApplication, QMainWindow, QLineEdit, QToolBar, QAction

class Browser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simple Browser")
        self.setGeometry(100, 100, 1024, 768)
        
        # Navigation bar
        nav_bar = QToolBar()
        self.addToolBar(nav_bar)
        
        # Back button
        back_btn = QAction("Back", self)
        back_btn.triggered.connect(self.back)
        nav_bar.addAction(back_btn)
        
        # Forward button
        forward_btn = QAction("Forward", self)
        forward_btn.triggered.connect(self.forward)
        nav_bar.addAction(forward_btn)
        
        # Reload button
        reload_btn = QAction("Reload", self)
        reload_btn.triggered.connect(self.reload)
        nav_bar.addAction(reload_btn)
        
        # URL bar
        self.url_bar = QLineEdit()
        self.url_bar.returnPressed.connect(self.navigate_to_url)
        nav_bar.addWidget(self.url_bar)
        
        # Browser widget
        self.browser = QWebEngineView()
        self.browser.urlChanged.connect(self.update_url)
        self.setCentralWidget(self.browser)
        
        # Home page
        self.browser.setUrl(QUrl("https://google.com"))
    
    def back(self):
        self.browser.back()
    
    def forward(self):
        self.browser.forward()
    
    def reload(self):
        self.browser.reload()
    
    def navigate_to_url(self):
        url = self.url_bar.text()
        if not url.startswith("http"):
            url = "http://" + url
        self.browser.setUrl(QUrl(url))
    
    def update_url(self, q):
        self.url_bar.setText(q.toString())

app = QApplication(sys.argv)
window = Browser()
window.show()
sys.exit(app.exec_())
