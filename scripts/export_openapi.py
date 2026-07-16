import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import django

django.setup()

from DjangoApiStarter.api import api

print(json.dumps(api.get_openapi_schema(), indent=2, sort_keys=True))
