STRCOM ; Mentions of XECUTE and @VAR inside strings and comments
 ; must not flag. The doubled-quote escape "" must not break masking.
 W "the keyword is XECUTE CMD but this is just text",!
 W "doubled "" quote then @VAR still inside a string",!
 ; doc: this routine deliberately avoids XECUTE and @-indirection
 Q
