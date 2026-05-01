node {
    def branch = env.GIT_BRANCH
    sh "git checkout ${branch}".execute().text
}
