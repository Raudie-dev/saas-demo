import os
import re

count = 0
for root, dirs, files in os.walk('.'):
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
            
            # Find all <form ... method="post" ... >
            forms = re.findall(r'<form[^>]*method=["\']post["\'][^>]*>(.*?)</form>', content, flags=re.IGNORECASE | re.DOTALL)
            for form in forms:
                if 'csrf_token' not in form:
                    print(f"Missing csrf_token inside form in {filepath}")
