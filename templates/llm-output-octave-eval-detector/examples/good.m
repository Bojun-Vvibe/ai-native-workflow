% Good samples — 0 findings expected.

% Struct field instead of `eval(['x' num2str(i) '=...'])`.
function s = good_struct_assign(n)
  s = struct();
  for i = 1:n
    s.(sprintf('f%d', i)) = i * i;
  endfor
endfunction

% Function handle instead of feval(name, ...).
function r = good_handle(fn, x)
  r = fn(x);  % fn is a @-handle, not a string
endfunction

% Cell array instead of dynamic var names.
function c = good_cell(n)
  c = cell(1, n);
  for i = 1:n
    c{i} = i;
  endfor
endfunction

% Transpose `'` after identifier — must NOT be parsed as string start.
function y = good_transpose(A)
  y = A' * A;
endfunction

% Comment that mentions eval(... should not trip:
% eval(s) is dangerous, so is feval('foo', x).

% String literal that contains the danger as data.
function show_doc()
  msg1 = 'never call eval(s) on user input';
  msg2 = "feval('os.system', x) is also bad";
  disp(msg1); disp(msg2);
endfunction

% A user function literally named `evaluate_score` — must not trip eval(.
function s = evaluate_score(x)
  s = sum(x .^ 2);
endfunction

% Method-style call `obj.eval(...)` is masked by the `[A-Za-z0-9_.]`
% lookbehind — it is a method call, not the global eval.
function y = good_method(obj, s)
  y = obj.eval(s);
endfunction

% Audited line with suppression marker.
function bad_but_audited(s)
  eval(s);  % eval-ok: trusted REPL helper
endfunction
