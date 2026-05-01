import jwt from 'jsonwebtoken';

export function authenticate(token: string, key: string): unknown {
  // GOOD: TypeScript with pinned algorithms list.
  return jwt.verify(token, key, {
    algorithms: ['RS256'],
    audience: 'api.example.com',
  });
}
