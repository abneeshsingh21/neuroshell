# Copyright (c) 2024-2026 Abneesh Singh. All rights reserved.
# Proprietary and Confidential - see LICENSE.txt
import ast, os

src = open('desktop_app.py', encoding='utf-8').read()
tree = ast.parse(src)
classes = [(n.name, n.lineno) for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
print('Classes in desktop_app.py:')
for name, line in classes:
    print(f'  Line {line}: {name}')

checks = ['FONT_FAMILY', 'ANSI_COLORS', 'FONT_MONO', 'ANSI_CODE_MAP', '_THEMES']
for c in checks:
    print(f'Has {c}: {c in src}')
