// chained `as any` casts in async code
export async function fetchUser(id: string): Promise<{ name: string }> {
  const res = await fetch("/u/" + id);
  const body = (await res.json()) as any;
  return { name: (body.name ?? "anon") as any };
}
