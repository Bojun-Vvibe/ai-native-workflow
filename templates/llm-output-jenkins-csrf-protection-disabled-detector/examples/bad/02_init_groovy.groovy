// init.groovy.d/disable-csrf.groovy -- BAD.
// Drops CSRF crumb issuer at controller startup.
import jenkins.model.Jenkins

def j = Jenkins.instance
j.setCrumbIssuer(null)
j.save()
