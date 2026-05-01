import jwt from 'jsonwebtoken';

export function authenticate(token: string, key: string): unknown {
  // BAD: TypeScript, no options at all.
  return jwt.verify(token, key);
}
