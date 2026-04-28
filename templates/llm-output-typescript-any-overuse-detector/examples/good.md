# User service draft

Here's a typed TypeScript service. Note: any of the following interfaces
can be extended later.

```ts
interface User {
  id: string;
  name: string;
}

function fetchUser(id: string): User {
  const cache: Record<string, User> = {};
  if (cache[id]) {
    return cache[id];
  }
  const result: User = doFetch(id);
  cache[id] = result;
  return result;
}

function merge<T extends object, U extends object>(a: T, b: U): T & U {
  return { ...a, ...b };
}

const handlers: Array<(u: User) => void> = [];
function register(h: (u: User) => void): void {
  handlers.push(h);
}
```

The word "any" appears in this prose but never as a type annotation.
