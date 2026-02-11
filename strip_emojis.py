import os
import re

def strip_emojis(text):
    # Keep ASCII 0-127
    return re.sub(r'[^\x00-\x7F]+', '', text)

def process_directory(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                new_content = strip_emojis(content)
                if new_content != content:
                    print(f"Stripped emojis from: {path}")
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(new_content)

if __name__ == "__main__":
    process_directory('src')
    # Process files in root directory
    for file in os.listdir('.'):
        if file.endswith('.py'):
            with open(file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            new_content = strip_emojis(content)
            if new_content != content:
                print(f"Stripped emojis from: {file}")
                with open(file, 'w', encoding='utf-8') as f:
                    f.write(new_content)
