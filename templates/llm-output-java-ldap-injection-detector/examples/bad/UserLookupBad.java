package com.example.directory;

import javax.naming.NamingEnumeration;
import javax.naming.directory.DirContext;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;
import javax.naming.ldap.LdapContext;

public class UserLookupBad {

    private final DirContext dirCtx;
    private final LdapContext ldapContext;

    public UserLookupBad(DirContext dirCtx, LdapContext ldapContext) {
        this.dirCtx = dirCtx;
        this.ldapContext = ldapContext;
    }

    // 1. Inline `+` concatenation into the filter argument.
    public NamingEnumeration<SearchResult> findByUid(String uid) throws Exception {
        SearchControls c = new SearchControls();
        return dirCtx.search("ou=people,dc=example,dc=com",
                "(&(uid=" + uid + ")(objectClass=person))", c);
    }

    // 2. String.format with a `(...)` filter and a %s placeholder.
    public NamingEnumeration<SearchResult> findByMail(String mail) throws Exception {
        SearchControls c = new SearchControls();
        String filter = String.format("(&(mail=%s)(objectClass=inetOrgPerson))", mail);
        return ldapContext.search("ou=people", filter, c);
    }

    // 3. Tainted-ident: filter built earlier and passed in.
    public NamingEnumeration<SearchResult> findByCn(String cn) throws Exception {
        SearchControls c = new SearchControls();
        String filter = "(&(cn=" + cn + ")(objectClass=person))";
        return dirCtx.search("ou=people", filter, c);
    }

    // 4. Different receiver name (custom Ctx alias) — should still match.
    public NamingEnumeration<SearchResult> findBySn(String sn, LdapContext myLdapContext) throws Exception {
        SearchControls c = new SearchControls();
        return myLdapContext.search("ou=people",
                "(sn=" + sn + ")", c);
    }

    // 5. Auth bypass classic: filter literal with `(&(uid=` glued to attacker input.
    public boolean authenticate(String username, String password) throws Exception {
        SearchControls c = new SearchControls();
        NamingEnumeration<SearchResult> results = dirCtx.search(
                "dc=example,dc=com",
                "(&(uid=" + username + ")(userPassword=" + password + "))",
                c);
        return results.hasMore();
    }

    // 6. String.format on ldapContext.
    public NamingEnumeration<SearchResult> findByGroup(String group) throws Exception {
        SearchControls c = new SearchControls();
        return ldapContext.search("ou=groups",
                String.format("(&(cn=%s)(objectClass=groupOfNames))", group), c);
    }
}
