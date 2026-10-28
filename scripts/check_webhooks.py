# Lists your webhooks and sends a test AUTHORISATION to each active one (no Customer Area login needed).
# Usage: python scripts/check_webhooks.py            list + test
#        python scripts/check_webhooks.py delete <id> remove an old webhook (e.g. a stale ngrok URL)
import os
import sys

import Adyen
from Adyen.exceptions import AdyenAPIResponseError
from dotenv import load_dotenv

load_dotenv()

ADYEN_MERCHANT_ACCOUNT = os.getenv('ADYEN_MERCHANT_ACCOUNT')

adyen = Adyen.Adyen(xapikey=os.getenv('ADYEN_API_KEY'), platform='test')
webhooks = adyen.management.webhooks_merchant_level_api

if len(sys.argv) == 3 and sys.argv[1] == 'delete':
    webhooks.remove_webhook(ADYEN_MERCHANT_ACCOUNT, sys.argv[2])
    print('Deleted', sys.argv[2])
    sys.exit()

for webhook in webhooks.list_all_webhooks(ADYEN_MERCHANT_ACCOUNT).message.get('data', []):
    # The merchant account is shared: only touch webhooks created by setup_webhook.py
    if webhook.get('description') != 'Drop-in demo (localhost tunnel)':
        continue
    print(f"\n{webhook['id']}  active={webhook['active']}  {webhook['url']}")
    if not webhook['active']:
        continue
    try:
        # Adyen sends a real test event to the URL and reports what your server answered
        result = webhooks.test_webhook({'types': ['AUTHORISATION']}, ADYEN_MERCHANT_ACCOUNT, webhook['id']).message
        for test in result.get('data', []):
            print(f"  test → status={test.get('status')} responseCode={test.get('responseCode')} "
                  f"response={test.get('output')!r}")
    except AdyenAPIResponseError as e:
        print('  test failed:', e.message)
