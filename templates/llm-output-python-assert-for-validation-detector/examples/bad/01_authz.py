"""Bad: assert used for authorization check."""

def withdraw(account, amount, current_user):
    assert account.owner == current_user, "not authorised"
    account.balance -= amount
    return account.balance
