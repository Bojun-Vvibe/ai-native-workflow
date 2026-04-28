# A todo list, the right way

Stable ids throughout. The word `index` appears in prose but never as
a key.

```jsx
function TodoList({ todos }) {
  return (
    <ul>
      {todos.map((todo) => (
        <li key={todo.id}>{todo.text}</li>
      ))}
    </ul>
  );
}
```

```tsx
type Row = { uuid: string; label: string };

function Table({ rows }: { rows: Row[] }) {
  return (
    <table>
      <tbody>
        {rows.map((row) => (
          <tr key={row.uuid}>
            <td>{row.label}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

```jsx
// Even when the second .map param exists, we use a stable id.
function Items({ items }) {
  return items.map((it, _ignored) => (
    <Item key={it.slug} value={it} />
  ));
}
```
