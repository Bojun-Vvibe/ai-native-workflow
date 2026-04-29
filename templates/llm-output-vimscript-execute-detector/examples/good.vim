" Good samples: no dynamic execute/eval. Should produce 0 findings.

" Plain Ex commands with literal arguments.
function! OpenScratch() abort
  edit __scratch__
  setlocal buftype=nofile
endfunction

" feedkeys is the safe alternative to `execute 'normal ' . keys`.
function! ReplayKeys(keys) abort
  call feedkeys(a:keys, 'n')
endfunction

" Direct function calls — no string-built command.
function! AddOne(x) abort
  return a:x + 1
endfunction

" Comment that mentions execute and eval should not trip the scanner:
" execute is dangerous when its argument is dynamic; eval(x) too.

" String literal that looks like the danger but is data.
let s:doc = "execute 'edit ' . fname  -- do not do this"
let s:doc2 = 'eval(expr)  -- nor this'

" A user function literally named `evaluate` — must not trip eval(.
function! evaluate_user_input(s) abort
  return len(a:s)
endfunction

" Audited dynamic execute with suppression marker.
function! AuditedExec(cmd) abort
  execute a:cmd  " exec-ok
endfunction
