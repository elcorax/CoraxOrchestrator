import subprocess
import webbrowser
from pathlib import Path

PROJECT_PATH = Path(r"D:\CORAX\CoraxOrchestrator")
FILES = ["README.md", "TODO.md"]

def copy_to_clipboard(text):
    process = subprocess.Popen(['clip'], stdin=subprocess.PIPE, close_fds=True)
    process.communicate(input=text.encode('utf-8'))

def main():
    content_parts = []
    for file in FILES:
        file_path = PROJECT_PATH / file
        if file_path.exists():
            content = file_path.read_text(encoding='utf-8')
            content_parts.append(f"# [file name]: {file}\n[file content begin]\n{content}\n[file content end]")
    
    full_content = "\n\n".join(content_parts)
    
    copy_to_clipboard(full_content)
    webbrowser.open("https://chat.openai.com")
    
    print(f"✅ تم نسخ {', '.join(FILES)} ({len(full_content)//1024} KB)")
    print("🌐 تم فتح ChatGPT - اضغط Ctrl+V وأرسل")

if __name__ == "__main__":
    main()