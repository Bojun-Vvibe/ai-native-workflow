# User service draft

Here's a quick TypeScript service for you. I used `any` where the
upstream payload shape was unclear; you can tighten later.

```ts
function fetchUser(id: any): any {
  const cache: Record<string, any> = {};
  if (cache[id]) {
    return cache[id] as any;
  }
  const result: any = doFetch(id);
  cache[id] = result;
  return result;
}

function merge(a: any, b: any): any {
  return { ...a, ...b } as any;
}

const handlers: Array<any> = [];
function register(h: any) {
  handlers.push(h as any);
}
```

Note: any of the above can be tightened with proper interfaces.
