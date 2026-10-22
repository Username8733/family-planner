"""Prepare a local HA app build context containing only runtime files."""
import argparse
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("destination", type=Path)
args = parser.parse_args()
target = args.destination.resolve()
if target == root or root.is_relative_to(target) or target.is_relative_to(root / "dist"):
    parser.error("Choose a separate build directory.")
target.mkdir(parents=True, exist_ok=True)
for name in ["config.json", "Dockerfile", "README.md", "DOCS.md"]:
    shutil.copy2(root / "home-assistant/addon" / name, target / name)
app = target / "app"
app.mkdir(exist_ok=True)
for name in ["serve.py", "calendar_sources.py", "online_calendar.py", "requirements.txt"]:
    shutil.copy2(root / name, app / name)
shutil.copy2(root / "home-assistant/addon/run.py", app / "ha_ingress.py")
shutil.copytree(root / "dist", app / "dist", dirs_exist_ok=True)
print("Prepared Family Planner HA app:", target)
