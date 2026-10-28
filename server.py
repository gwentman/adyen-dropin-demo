import json
import os
import time
import uuid

import Adyen
import requests
from Adyen.exceptions import AdyenAPIResponseError
from Adyen.util import is_valid_hmac_notification
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

load_dotenv()

ADYEN_API_KEY = os.getenv('ADYEN_API_KEY')
ADYEN_CLIENT_KEY = os.getenv('ADYEN_CLIENT_KEY')
ADYEN_MERCHANT_ACCOUNT = os.getenv('ADYEN_MERCHANT_ACCOUNT')
ADYEN_HMAC_KEY = os.getenv('ADYEN_HMAC_KEY')
PORT = int(os.getenv('PORT', '8080'))

adyen = Adyen.Adyen(xapikey=ADYEN_API_KEY, platform='test', http_timeout=10)

# Amounts are in minor units: AUD/EUR have 2 decimals, JPY has 0.
MARKETS = {
    'AU': {'currency': 'AUD', 'value': 4999, 'locale': 'en-AU'},
    'NL': {'currency': 'EUR', 'value': 4999, 'locale': 'nl-NL'},
    'JP': {'currency': 'JPY', 'value': 5000, 'locale': 'ja-JP'},
}

# In-memory "database" — fine for a demo, use a real DB in production.
orders = {}                 # reference -> order (dicts keep insertion order)
processed_webhooks = set()  # dedupe keys

app = Flask(__name__, static_folder='public', static_url_path='')


def call_with_retries(api_call, body, attempts=3):
    # One Idempotency-Key for every attempt: if a timed-out request actually reached Adyen,
    # the retry returns that same result instead of creating a duplicate.
    idempotency_key = str(uuid.uuid4())
    for attempt in range(1, attempts + 1):
        try:
            return api_call(body, idempotency_key=idempotency_key).message
        except (requests.RequestException, AdyenAPIResponseError) as e:
            # Retry only network errors and 5xx. A 4xx means the request itself is wrong.
            retryable = isinstance(e, requests.RequestException) or (e.status_code or 0) >= 500
            if not retryable or attempt == attempts:
                raise
            print(f'attempt {attempt} failed ({e}), retrying with same Idempotency-Key {idempotency_key}')
            time.sleep(2 ** attempt)  # back off: 2s, 4s


@app.get('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')


@app.get('/api/config')
def config():
    return jsonify(clientKey=ADYEN_CLIENT_KEY)


# Sessions flow: one call. Frontend Drop-in then talks to Adyen directly (payments, 3DS, redirects).
@app.post('/api/sessions')
def sessions():
    country = request.json.get('country') or 'AU'
    market = MARKETS.get(country, MARKETS['AU'])
    currency, value = market['currency'], market['value']
    reference = f'ORDER-{int(time.time() * 1000)}'

    orders[reference] = {'reference': reference, 'amount': f'{value} {currency}', 'webhookStatus': None}

    body = {
        'merchantAccount': ADYEN_MERCHANT_ACCOUNT,
        'amount': {'currency': currency, 'value': value},
        'reference': reference,
        'countryCode': country,
        'shopperLocale': market['locale'],
        'channel': 'Web',
        'returnUrl': f'http://localhost:{PORT}/?country={country}',
        'authenticationData': {'threeDSRequestData': {'nativeThreeDS': 'preferred'}},
    }
    print('\n→ /sessions', json.dumps(body, indent=2))
    try:
        session = call_with_retries(adyen.checkout.payments_api.sessions, body)
    except AdyenAPIResponseError as e:  # library raises on 4xx/5xx
        print('← error', e.message)
        return jsonify(error=e.message), e.status_code
    except requests.RequestException as e:
        print('← network error', e)
        return jsonify(error='Could not reach Adyen'), 502
    print('← /sessions', json.dumps(session, indent=2))

    return jsonify(clientKey=ADYEN_CLIENT_KEY, amount=session['amount'], reference=reference,
                   session={'id': session['id'], 'sessionData': session['sessionData']})


# Webhooks: the source of truth for the final payment status.
@app.post('/api/webhooks/notifications')
def webhooks():
    for wrapper in request.json.get('notificationItems', []):
        item = wrapper['NotificationRequestItem']
        if ADYEN_HMAC_KEY and not is_valid_hmac_notification(item, ADYEN_HMAC_KEY):
            print('✗ Invalid HMAC, ignoring webhook', item.get('pspReference'))
            continue

        # Adyen delivers at-least-once: the same event can arrive twice.
        key = f"{item['pspReference']}:{item['eventCode']}:{item['success']}"
        if key in processed_webhooks:
            print('↺ Duplicate webhook ignored', key)
            continue
        processed_webhooks.add(key)

        print(f"\n⚡ Webhook {item['eventCode']} success={item['success']} "
              f"ref={item.get('merchantReference')} psp={item['pspReference']}")
        order = orders.get(item.get('merchantReference'))
        if not order:
            continue  # e.g. events from other test traffic on this shared account

        if item['eventCode'] == 'AUTHORISATION':
            order['webhookStatus'] = 'Authorised' if item['success'] == 'true' else f"Refused ({item.get('reason')})"
    # Acknowledge fast; in production, queue the work and process async.
    return '[accepted]'


@app.get('/api/orders')
def list_orders():
    return jsonify(list(reversed(orders.values())))


if __name__ == '__main__':
    print(f'Demo running at http://localhost:{PORT}')
    if not ADYEN_HMAC_KEY:
        print('⚠ ADYEN_HMAC_KEY not set: webhook signatures are NOT verified')
    app.run(port=PORT)
