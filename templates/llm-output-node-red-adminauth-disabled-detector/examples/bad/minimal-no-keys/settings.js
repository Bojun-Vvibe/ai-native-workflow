// Bare-bones settings module from a tutorial. No adminAuth key.
module.exports = {
    uiPort: 1880,
    httpAdminRoot: "/red",
    flowFile: "flows.json",
    userDir: "/data",
    functionGlobalContext: {
        os: require('os'),
    },
    editorTheme: { projects: { enabled: false } },
};
