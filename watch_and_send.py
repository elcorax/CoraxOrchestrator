import time
import hashlib
import subprocess
import webbrowser
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

PROJECT_PATH = Path(r"D:\CORAX\CoraxOrchestrator")
FILES_TO_WATCH = ["README.md", "TODO.md"]

class CoraxFileHandler(FileSystemEventHandler):
    def __init__(self):
        self.last_hashes = {}
        self.load_hashes()
    
    def load_hashes(self):
        for file in FILES_TO_WATCH:
            path = PROJECT_PATH / file
            if path.exists():
                self.last_hashes[file] = hashlib.md5(path.read_bytes()).hexdigest()
    
    def copy_to_clipboard(self, text):
        process = subprocess.Popen(['clip'], stdin=subprocess.PIPE, close_fds=True)
        process.communicate(input=text.encode('utf-8'))
    
    def on_modified(self, event):
        if event.src_path.endswith(tuple(FILES_TO_WATCH)):
            file_name = Path(event.src_path).name
            print(f"\n📁 تم تعديل: {file_name}")
            
            content = Path(event.src_path).read_text(encoding='utf-8')
            new_hash = hashlib.md5(content.encode()).hexdigest()
            
            if self.last_hashes.get(file_name) == new_hash:
                return
            
            self.last_hashes[file_name] = new_hash
            
            full_text = []
            for file in FILES_TO_WATCH:
                file_path = PROJECT_PATH / file
                if file_path.exists():
                    full_text.append(f"# [file name]: {file}\n[file content begin]\n{file_path.read_text(encoding='utf-8')}\n[file content end]")
            
            final_text = "\n\n".join(full_text)
            
            self.copy_to_clipboard(final_text)
            print(f"✅ تم نسخ المحتوى إلى الحافظة ({(len(final_text)//1024)} KB)")
            
            webbrowser.open("https://chat.openai.com")
            print("🌐 تم فتح ChatGPT - فقط اضغط Ctrl+V ثم Enter")

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 مراقب Corax Orchestrator")
    print(f"📂 المسار: {PROJECT_PATH}")
    print(f"📄 ملفات المراقبة: {FILES_TO_WATCH}")
    print("🟢 جاهز... عدل أي ملف وسيتم نسخه تلقائياً!")
    print("اضغط Ctrl+C لإيقاف المراقب")
    print("=" * 50)
    
    event_handler = CoraxFileHandler()
    observer = Observer()
    observer.schedule(event_handler, str(PROJECT_PATH), recursive=False)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 تم إيقاف المراقب")
        observer.stop()
    observer.join()