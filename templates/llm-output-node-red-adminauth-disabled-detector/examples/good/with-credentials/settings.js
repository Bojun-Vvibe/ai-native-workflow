// Settings with active adminAuth (credentials strategy).
module.exports = {
    uiPort: 1880,
    flowFile: "flows.json",
    functionGlobalContext: {},
    adminAuth: {
        type: "credentials",
        users: [
            {
                username: "admin",
                password: "$2b$08$abcdefghijklmnopqrstuv1234567890ABCDEFGHIJKLMNOPQRSTUV",
                permissions: "*"
            }
        ]
    },
};
