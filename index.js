const crypto = require('crypto');
const { onRequest } = require('firebase-functions/v2/https');
const { defineSecret } = require('firebase-functions/params');
const { initializeApp } = require('firebase-admin/app');
const { getMessaging } = require('firebase-admin/messaging');

initializeApp();
const KOJA_RELAY_SECRET = defineSecret('KOJA_RELAY_SECRET');

function safeEqual(a, b) {
  if (!a || !b) return false;
  const aa = Buffer.from(String(a));
  const bb = Buffer.from(String(b));
  return aa.length === bb.length && crypto.timingSafeEqual(aa, bb);
}

exports.sendKojaPush = onRequest(
  { region: 'us-central1', timeoutSeconds: 30, memory: '256MiB', secrets: [KOJA_RELAY_SECRET] },
  async (req, res) => {
    if (req.method !== 'POST') return res.status(405).json({ error: 'POST only' });
    const supplied = req.get('X-KOJA-Relay-Secret') || '';
    if (!safeEqual(supplied, KOJA_RELAY_SECRET.value())) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    const body = req.body || {};
    const tokens = Array.isArray(body.tokens) ? body.tokens.filter(x => typeof x === 'string' && x.length > 0).slice(0, 50) : [];
    const dataIn = body.data && typeof body.data === 'object' ? body.data : {};
    const data = {};
    for (const [k, v] of Object.entries(dataIn)) data[String(k)] = String(v ?? '');
    if (!tokens.length) return res.json({ sent: 0, invalid_tokens: [] });

    const response = await getMessaging().sendEachForMulticast({
      tokens,
      data,
      android: { priority: 'high' }
    });

    const invalid_tokens = [];
    response.responses.forEach((r, i) => {
      if (!r.success) {
        const code = r.error && r.error.code ? r.error.code : '';
        if (code.includes('registration-token-not-registered') || code.includes('invalid-registration-token')) {
          invalid_tokens.push(tokens[i]);
        }
      }
    });

    return res.json({
      sent: response.successCount,
      failed: response.failureCount,
      invalid_tokens
    });
  }
);
