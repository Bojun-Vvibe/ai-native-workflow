% Bad samples for octave-eval-detector. Expected: 7 findings.

function bad_loop_assign(n)
  for i = 1:n
    eval(['x' num2str(i) ' = ' num2str(i*i) ';']);
  endfor
endfunction

function v = bad_eval_in_caller(name)
  v = evalin('caller', name);
endfunction

function r = bad_feval(fname, x)
  r = feval(fname, x);
endfunction

function bad_assignin(vname, val)
  assignin('base', vname, val);
endfunction

function bad_two_arg_eval(s)
  eval(s, 'disp("eval failed")');
endfunction

function bad_nested(s)
  y = 1 + eval(s);
  disp(y);
endfunction

function bad_chained(name, val)
  assignin('caller', name, val); evalin('caller', name);
endfunction
