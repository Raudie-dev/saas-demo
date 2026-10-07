import os

count = 0
for root, dirs, files in os.walk('.'):
    # skip venv
    if 'venv' in root or '.git' in root or '__pycache__' in root:
        continue
    for file in files:
        if file.endswith('.html'):
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception:
                continue
            
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if 'method="post"' in line.lower() or "method='post'" in line.lower():
                    count += 1
print(f"Total forms found: {count}")
