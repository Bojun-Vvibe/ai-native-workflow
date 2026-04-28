<?php
// 02_method_named_eval.php — user method, not the language builtin.
class Calculator {
    public function eval(int $a, int $b): int {
        return $a + $b;
    }
}

class Strategy {
    public static function eval(string $name): bool {
        return $name !== '';
    }
}

$c = new Calculator();
echo $c->eval(1, 2);
echo Strategy::eval('ok');
