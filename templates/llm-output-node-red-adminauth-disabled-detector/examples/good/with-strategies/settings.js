// Settings using OAuth/Passport strategy via adminAuth.
module.exports = {
    uiPort: 1880,
    httpAdminRoot: "/admin",
    flowFile: "flows.json",
    functionGlobalContext: {},
    adminAuth: {
        type: "strategy",
        strategy: {
            name: "oauth2",
            label: "Sign in with provider",
            icon: "fa-cloud",
            strategy: require("passport-oauth2").Strategy,
            options: {
                authorizationURL: process.env.OAUTH_AUTH_URL,
                tokenURL: process.env.OAUTH_TOKEN_URL,
                clientID: process.env.OAUTH_CLIENT_ID,
                clientSecret: process.env.OAUTH_CLIENT_SECRET,
                callbackURL: process.env.OAUTH_CALLBACK_URL,
                verify: function(token, profile, done) { done(null, profile); }
            }
        },
        users: function(user) { return Promise.resolve({ username: user, permissions: "*" }); }
    },
};
