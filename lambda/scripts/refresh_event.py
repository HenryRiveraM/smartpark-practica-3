"""Actualizar timestamp de una plantilla de prueba antes de pegarla en Lambda."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

if __name__ == "__main__":
    event = json.loads(Path(sys.argv[1]).read_text())
    event["request"]["timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    print(json.dumps(event, ensure_ascii=False, indent=2))
