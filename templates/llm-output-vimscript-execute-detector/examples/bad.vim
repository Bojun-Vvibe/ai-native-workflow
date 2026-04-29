" Bad samples: dynamic :execute and eval() — should be flagged.
" 6 expected findings.

function! Open(fname) abort
  execute 'edit ' . a:fname
endfunction

function! RunKeys(keys) abort
  exe "normal! " . a:keys
endfunction

function! RunCmd(cmd) abort
  :exec a:cmd
endfunction

function! Compute(expr) abort
  let v = eval(a:expr)
  return v
endfunction

function! ChainedExec(cmd) abort
  let x = 1 | execute 'echo ' . a:cmd
endfunction

function! NestedEval(s) abort
  call setline(1, eval(s:s))
endfunction
