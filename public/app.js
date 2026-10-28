const { AdyenCheckout, Dropin } = window.AdyenWeb;

const params = new URLSearchParams(location.search);
const country = params.get('country') ?? 'AU';
document.getElementById('country').value = country;

const showResult = (resultCode) => (document.getElementById('result').textContent = `Result: ${resultCode}`);

// The session carries amount, country, locale and payment methods. Drop-in does the rest.
const createCheckout = (clientKey, session) =>
  AdyenCheckout({
    clientKey,
    session,
    environment: 'test',
    onPaymentCompleted: (result) => showResult(result.resultCode),
    onPaymentFailed: (result) => showResult(result?.resultCode ?? 'Failed'),
  });

async function start() {
  // Shopper came back from a redirect payment method (e.g. iDEAL): let the session finish it.
  if (params.get('redirectResult')) {
    const { clientKey } = await fetch('/api/config').then((r) => r.json());
    const checkout = await createCheckout(clientKey, { id: params.get('sessionId') });
    checkout.submitDetails({ details: { redirectResult: params.get('redirectResult') } });
    history.replaceState(null, '', `/?country=${country}`);
    return;
  }

  const { clientKey, amount, reference, session } = await fetch('/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ country }),
  }).then((r) => r.json());
  currentReference = reference;
  // Adyen amounts are in minor units: AUD 4999 = A$49.99, JPY 5000 = ¥5,000 (no decimals)
  const format = new Intl.NumberFormat(undefined, { style: 'currency', currency: amount.currency });
  const total = amount.value / 10 ** format.resolvedOptions().maximumFractionDigits;
  document.getElementById('amount').textContent =
    `Order total: ${format.format(total)} (sent to Adyen as ${amount.value} ${amount.currency} minor units)`;

  new Dropin(await createCheckout(clientKey, session)).mount('#dropin-container');
}

document.getElementById('country').addEventListener('change', (e) => {
  location.href = `/?country=${e.target.value}`;
});

// Every page load opens a new session with a new reference. Only show the current checkout
// and orders Adyen has sent a webhook for, so abandoned checkouts don't clutter the table.
let currentReference;

async function refreshOrders() {
  const orders = await fetch('/api/orders').then((r) => r.json());
  document.getElementById('orders').innerHTML = orders
    .filter((o) => o.webhookStatus || o.reference === currentReference)
    .map((o) => `<tr><td>${o.reference}</td><td>${o.amount}</td><td>${o.webhookStatus ?? 'waiting…'}</td></tr>`)
    .join('');
}
setInterval(refreshOrders, 2000);

start();
