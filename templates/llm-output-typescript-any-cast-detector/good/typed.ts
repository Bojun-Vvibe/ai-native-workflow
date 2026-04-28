// proper typing — no `any` casts at all
interface User {
  id: string;
  name: string;
}

export function greet(u: User): string {
  return `hello, ${u.name}`;
}

export function asUser(o: { id: string; name: string }): User {
  return { id: o.id, name: o.name };
}
