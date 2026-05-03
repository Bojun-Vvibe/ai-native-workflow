# Job DSL seed job that processes user-controlled YAML and explicitly
# opts out of script security. Anyone who can edit the inputs gets
# Groovy execution as the controller.
job('build-app') {
    scm {
        git('https://example.invalid/build-app.git')
    }
    steps {
        dsl {
            external('jobs/*.groovy')
            useScriptSecurity(false)
        }
    }
}
