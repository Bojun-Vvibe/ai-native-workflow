// Job DSL seed job that keeps script security at its default (true).
job('build-app') {
    scm {
        git('https://example.invalid/build-app.git')
    }
    steps {
        dsl {
            external('jobs/*.groovy')
            useScriptSecurity(true)
        }
    }
}
