# A todo list, the wrong way

Five flavours of "use the index as the key" follow.

```jsx
function TodoList({ todos }) {
  return (
    <ul>
      {todos.map((todo, index) => (
        <li key={index}>{todo.text}</li>
      ))}
    </ul>
  );
}
```

```jsx
function Coerced({ rows }) {
  return rows.map((row, idx) => (
    <Row key={String(idx)} data={row} />
  ));
}
```

```jsx
function Templated({ items }) {
  return items.map((it, i) => (
    <Item key={`${i}`} value={it} />
  ));
}
```

```jsx
function ToString({ items }) {
  return items.map((it, idx) => (
    <Item key={idx.toString()} value={it} />
  ));
}
```

```tsx
function Renamed({ rows }: { rows: Row[] }) {
  return rows.map((row: Row, rowNum: number) => (
    <tr key={rowNum}>
      <td>{row.label}</td>
    </tr>
  ));
}
```
