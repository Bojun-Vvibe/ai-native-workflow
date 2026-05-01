package com.example.directory;

import javax.naming.NamingEnumeration;
import javax.naming.directory.DirContext;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;
import javax.naming.ldap.LdapContext;

public class UserLookupGood {

    private final DirContext dirCtx;
    private final LdapContext ldapContext;

    public UserLookupGood(DirContext dirCtx, LdapContext ldapContext) {
        this.dirCtx = dirCtx;
        this.ldapContext = ldapContext;
    }

    // 1. Pure literal filter — no concatenation, no taint.
    public NamingEnumeration<SearchResult> findAllPersons() throws Exception {
        SearchControls c = new SearchControls();
        return dirCtx.search("ou=people,dc=example,dc=com",
                "(objectClass=person)", c);
    }

    // 2. Filter built with the OWASP Encoder, inlined into the literal
    //    so the safe-hint allowlist sees the call.
    public NamingEnumeration<SearchResult> findByUid(String uid) throws Exception {
        SearchControls c = new SearchControls();
        String filter = "(&(uid=" + Encode.forLdap(uid) + ")(objectClass=person))";
        return dirCtx.search("ou=people", filter, c);
    }

    // 3. Filter built via UnboundID Filter.create — parameterized.
    public NamingEnumeration<SearchResult> findByMail(String mail) throws Exception {
        SearchControls c = new SearchControls();
        String filter = Filter.create("(&(mail={0})(objectClass=inetOrgPerson))", mail);
        return ldapContext.search("ou=people", filter, c);
    }

    // 4. Custom escape helper whose name is in the safe-hint allowlist.
    public NamingEnumeration<SearchResult> findByCn(String cn) throws Exception {
        SearchControls c = new SearchControls();
        String filter = "(&(cn=" + escapeLDAPSearchFilter(cn) + ")(objectClass=person))";
        return dirCtx.search("ou=people", filter, c);
    }

    // 5. Suppression marker for a reviewed-safe call site.
    public NamingEnumeration<SearchResult> findByConstantPrefix(String suffix) throws Exception {
        // Suffix is constrained to [A-Za-z0-9]+ by an upstream regex.
        SearchControls c = new SearchControls();
        return dirCtx.search("ou=people",
                "(&(cn=svc-" + suffix + ")(objectClass=person))", c); // llm-allow:ldap-injection
    }

    // 6. Comment that mentions the hazardous pattern must not trigger.
    // dirCtx.search("ou=x", "(&(uid=" + uid + ")(x=y))", controls);
    public void docOnly() {}

    // 7. Non-Context receiver — must not match (`.search()` on a list, etc.).
    public int countMatches(java.util.List<String> list, String needle) {
        return list.search(needle, null);
    }

    // --- stub helpers so the file is self-contained ---
    static String escapeLDAPSearchFilter(String s) { return s; }
    static class Encode { static String forLdap(String s) { return s; } }
    static class Filter { static String create(String fmt, Object... a) { return fmt; } }
}
