# Outline notes

The upstream `.env.sample` for `outlinewiki/outline` ships with
`SECRET_KEY=generate_a_new_key` and `UTILS_SECRET=generate_a_new_key`.
Both MUST be replaced with `openssl rand -hex 32` output before
exposing Outline. UTILS_SECRET protects internal `utils.gc`.
