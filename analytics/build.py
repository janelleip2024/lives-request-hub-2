"""
One command to refresh everything:
  python3 analytics/build.py            regenerate data, rerun the analysis, update app.html and index.html
  python3 analytics/build.py --inject   only re-inject analytics/regional.json (after editing app.html)

Needs: pip install pandas numpy scikit-learn statsmodels
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

if "--inject" not in sys.argv:
    for step in ("generate_data.py", "analyze.py"):
        print(f"== {step}")
        subprocess.run([sys.executable, os.path.join(HERE, step)], check=True, cwd=HERE)

data = open(os.path.join(HERE, "regional.json")).read().replace("</", "<\\/")
app_path = os.path.join(ROOT, "app.html")
app = open(app_path).read()
app, n = re.subn(r"/\*REGIONAL_DATA\*/.*?/\*END_REGIONAL_DATA\*/",
                 lambda _: f"/*REGIONAL_DATA*/const REGIONAL = {data};/*END_REGIONAL_DATA*/", app, flags=re.S)
if n != 1:
    sys.exit("REGIONAL_DATA markers not found in app.html")
open(app_path, "w").write(app)

head = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n</head>\n<body>\n')
open(os.path.join(ROOT, "index.html"), "w").write(head + app + "\n</body>\n</html>\n")
print(f"== app.html and index.html updated ({len(app) // 1024} KB)")
