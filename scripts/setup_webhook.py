# Registers a standard webhook via the Management API and prints the HMAC key.
# Usage: python scripts/setup_webhook.py https://<your-ngrok-id>.ngrok-free.app
import os
import sys

import Adyen
from dotenv import load_dotenv

load_dotenv()

ADYEN_MERCHANT_ACCOUNT = os.getenv('ADYEN_MERCHANT_ACCOUNT')
if len(sys.argv) < 2:
    sys.exit('Pass your public tunnel URL, e.g. python scripts/setup_webhook.py https://abc.ngrok-free.app')
public_url = sys.argv[1]

adyen = Adyen.Adyen(xapikey=os.getenv('ADYEN_API_KEY'), platform='test')
webhooks = adyen.management.webhooks_merchant_level_api

webhook = webhooks.set_up_webhook({
    'type': 'standard',
    'url': f'{public_url}/api/webhooks/notifications',
    'active': True,
    'communicationFormat': 'json',
    'description': 'Drop-in demo (localhost tunnel)',
}, ADYEN_MERCHANT_ACCOUNT).message
print('Webhook:', webhook)

hmac_key = webhooks.generate_hmac_key(ADYEN_MERCHANT_ACCOUNT, webhook['id']).message['hmacKey']
print(f'\nAdd this to .env:\nADYEN_HMAC_KEY={hmac_key}')
