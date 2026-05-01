// Plain reads -- no writes against attacker-controlled keys, no recursion.
function getName(user) {
  return user && user.profile && user.profile.name;
}
export { getName };
