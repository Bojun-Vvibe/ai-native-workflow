/* ESM-style settings module without adminAuth.
   The adminAuth block here is wrapped in a block comment
   so it is NOT active. */
export default {
    uiPort: 1880,
    flowFile: "flows.json",
    functionGlobalContext: {},
    /*
    adminAuth: {
        type: "credentials",
        users: [{ username: "admin", password: "x", permissions: "*" }]
    },
    */
};
