USING: kernel math ;
IN: scratch.good

! Pure call( ): the quotation is a literal value, type-checked.
: add-two ( x -- y )
    [ 2 + ] call( x -- y ) ;
