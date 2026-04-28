<?php
// Operators that look similar but are NOT loose equality:
//   =>   array key arrow
//   <=>  spaceship (combined comparison)
//   <=   less-than-or-equal
//   >=   greater-than-or-equal
//   ===  strict equality
//   !==  strict inequality

$map = [
    "name" => "Alice",
    "age"  => 30,
];

function cmp(int $a, int $b): int {
    return $a <=> $b;  // spaceship — must NOT trigger as `<>` or `<`
}

function in_range(int $x): bool {
    return $x >= 0 && $x <= 100;
}

function exact(string $a, string $b): bool {
    return $a === $b;
}

function not_exact(string $a, string $b): bool {
    return $a !== $b;
}

# A line comment with == and != and <> — must not trigger.
/* A block comment: == and != and <> are fine here too. */

$heredoc = <<<EOT
This heredoc body discusses == and != and <> at length, but
none of these should be flagged because they live inside a
string literal.
EOT;

echo $heredoc, "\n";
