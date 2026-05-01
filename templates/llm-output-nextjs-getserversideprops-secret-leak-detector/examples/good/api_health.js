// pages/api/health.js — API route, NOT a data-loading function.
// process.env.SECRET reference here is server-only and never serialised
// into a page payload. Detector should not flag.
export default function handler(req, res) {
  if (req.headers["x-internal-secret"] !== process.env.HEALTHCHECK_SECRET) {
    return res.status(401).json({ ok: false });
  }
  return res.status(200).json({ ok: true });
}
