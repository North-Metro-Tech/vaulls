import os
from dotenv import load_dotenv

load_dotenv()

VAULLS_PAY_TO = os.getenv("VAULLS_PAY_TO", "")
FACILITATOR_URL = os.getenv("VAULLS_FACILITATOR_URL", "https://x402.org/facilitator")

TOOL_PRICING = {
    "POST /tools/max-demand": {
        "price": "$0.05",
        "description": "AS3000 maximum demand calculation",
    },
}
