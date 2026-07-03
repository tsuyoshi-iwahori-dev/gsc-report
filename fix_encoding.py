# -*- coding: utf-8 -*-
import json

path = r'C:\Users\tsuyoshi-iwahori\Documents\gijiroku\kw-rankings.json'

with open(path, encoding='cp932') as f:
    data = json.load(f)

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print('変換完了')
print(data)