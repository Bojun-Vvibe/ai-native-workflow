"""Good: real validation using a raised exception."""

def withdraw(account, amount, current_user):
    if account.owner != current_user:
        raise PermissionError("not authorised")
    if amount > account.balance:
        raise ValueError("overdraft")
    account.balance -= amount
    return account.balance
