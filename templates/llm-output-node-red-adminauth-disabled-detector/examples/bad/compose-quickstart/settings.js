// Quickstart settings.js — adminAuth left commented out.
module.exports = {
    uiPort: process.env.PORT || 1880,
    // adminAuth: {
    //     type: "credentials",
    //     users: [{ username: "admin", password: "abc", permissions: "*" }]
    // },
    flowFile: 'flows.json',
    functionGlobalContext: {
    },
};
