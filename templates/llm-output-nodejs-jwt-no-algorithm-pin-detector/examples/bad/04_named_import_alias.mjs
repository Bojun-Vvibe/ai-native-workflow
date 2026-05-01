import { verify as jwtVerify } from 'jsonwebtoken';

export function authenticate(token, key) {
  // BAD: aliased verify() with no algorithms allowlist.
  return jwtVerify(token, key);
}
